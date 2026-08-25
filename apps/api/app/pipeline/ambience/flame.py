"""
Flame, smoke and fire-light simulation — the only per-frame heavy work.

Model (a temperature field, not a fluid solve — a real Navier-Stokes solve is
both far too slow on 4 cores AND cannot be made exactly periodic, which would
cost us the whole stream-copy strategy):

    temp = clip( (turbulence - threshold(x, y)) / softness )

`threshold` rises with height and with distance from the fuel bed, so tongues
naturally narrow, break up and extinguish as they climb — which is what makes
the silhouette read as fire rather than as animated noise. The turbulence is
`PeriodicFBM`, stretched hard along y so every structure is an elongated tongue,
and scrolled upward by an integer number of lattice periods per loop.

Three things sell the realism disproportionately:

  * horizontal sway that grows with height (flames lick, they don't just rise);
  * per-tongue independent phases, so the fire is several competing flames over
    one fuel bed rather than a single pulsing mass;
  * a blue-ish reaction zone at the very base, which is physically what burning
    wood gas looks like and which almost no procedural fire bothers with.

Everything here is a pure function of `loop_phase`, so it is exactly periodic.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .imaging import blur, ramp
from .noise import PeriodicFBM, loop_phase


# Blackbody-ish emission ramp for wood flame, in LINEAR light and deliberately
# over-unity at the core so the tone-mapper's shoulder has something to roll off.
FIRE_RAMP: list[tuple[float, tuple[float, float, float]]] = [
    (0.00, (0.000, 0.000, 0.000)),
    (0.12, (0.115, 0.012, 0.002)),   # first dull red
    (0.30, (0.520, 0.088, 0.008)),   # deep ember red
    (0.50, (1.120, 0.300, 0.026)),   # orange
    (0.70, (1.850, 0.720, 0.105)),   # bright orange-amber
    (0.86, (2.450, 1.330, 0.330)),   # yellow
    (1.00, (2.950, 2.150, 1.020)),   # near-white core
]

SMOKE_TINT = np.array([0.085, 0.074, 0.070], dtype=np.float32)


@dataclass
class FlameFrame:
    emission: np.ndarray    # (h, w, 3) linear, additive
    smoke: np.ndarray       # (h, w) 0..1 alpha
    light: np.ndarray       # (h, w) 0..1 broad light field for relighting
    intensity: float        # scalar 0..1, overall output this frame


class FlameSim:
    """Exactly-periodic fire field at simulation resolution."""

    def __init__(
        self,
        width: int,
        height: int,
        frames: int,
        *,
        seed: int = 11,
        fuel_y: float = 0.205,
        flame_top: float = -0.74,
        half_width: float = 1.02,
    ) -> None:
        self.w, self.h, self.frames = int(width), int(height), int(frames)
        self.fuel_y = fuel_y
        self.span = fuel_y - flame_top

        # --- world grid (matches hearth._world_coords exactly) --------------
        y = (np.arange(self.h, dtype=np.float32) - self.h / 2.0) / (self.h / 2.0)
        x = (np.arange(self.w, dtype=np.float32) - self.w / 2.0) / (self.h / 2.0)
        self.xw = x[None, :]
        self.yw = y[:, None]

        # normalised height above the fuel bed, 0 at the logs -> 1 at flame top
        self.hy = np.clip((fuel_y - self.yw) / self.span, 0.0, 1.0).astype(np.float32)
        # Smooth, not binary. A hard `yw < fuel_y` step drew a dead-straight
        # horizontal seam across the base of the fire — the single most obvious
        # artifact in the whole frame.
        self.above = np.clip((fuel_y + 0.10 - self.yw) / 0.20, 0.0, 1.0).astype(np.float32)

        # --- turbulence: stretched vertically into tongues -------------------
        self.turb = PeriodicFBM(
            self.w, self.h, frames, octaves=5,
            base_x=7.0, base_y=2.6, base_z=4,
            lacunarity=2.05, gain=0.52, y_scroll_periods=1, seed=seed,
        )
        # slow, large-scale sway; low octave count keeps it a drift not a jitter
        self.sway = PeriodicFBM(
            max(48, self.w // 12), max(28, self.h // 12), frames, octaves=2,
            base_x=2.0, base_y=1.6, base_z=3,
            gain=0.55, y_scroll_periods=1, seed=seed + 101,
        )
        # independent breathing of the fuel bed -> tongues rise and fall apart
        self.bed = PeriodicFBM(
            max(48, self.w // 12), 4, frames, octaves=2,
            base_x=3.0, base_y=1.0, base_z=3,
            gain=0.5, y_scroll_periods=0, seed=seed + 202,
        )
        # smoke is a separate, slower, larger-scale field that outlives the flame
        self.smoke_n = PeriodicFBM(
            max(64, self.w // 3), max(36, self.h // 3), frames, octaves=4,
            base_x=3.2, base_y=1.8, base_z=3,
            gain=0.55, y_scroll_periods=2, seed=seed + 303,
        )

        self.half_width = half_width
        self._sway_shape = (self.sway.height, self.sway.width)

    # ------------------------------------------------------------------ helpers
    def _resample(self, small: np.ndarray) -> np.ndarray:
        """Cheap nearest expand of a low-res control field to sim resolution."""
        yi = (np.arange(self.h) * small.shape[0] // self.h)
        xi = (np.arange(self.w) * small.shape[1] // self.w)
        return small[yi][:, xi]

    # --------------------------------------------------------------------- step
    def step(self, frame: int) -> FlameFrame:
        ph = loop_phase(frame, self.frames)

        # Sway: horizontal displacement that grows with height, so the base stays
        # anchored on the logs while the tips lick sideways.
        sway = self._resample(self.sway.field(frame)) - 0.5
        sway *= (0.34 * self.hy ** 1.35)

        # Fuel bed breathing: a per-column supply term. Columns flare at their
        # own pace, which is what stops the fire pulsing as one object.
        bed = self._resample(self.bed.field(frame))
        bed = 0.72 + 0.62 * bed

        n = self.turb.field(frame)

        # Advect the turbulence sideways by the sway. Rolling per-row is too slow
        # in numpy, so we fold the displacement into the threshold instead: a
        # sheared read of x via a gather on the already-computed field.
        shift = np.clip(sway * self.w * 0.45, -self.w * 0.25, self.w * 0.25).astype(np.int32)
        cols = (np.arange(self.w, dtype=np.int32)[None, :] + shift) % self.w
        n = np.take_along_axis(n, cols, axis=1)

        # Horizontal profile: narrows with height, with soft shoulders.
        hw = self.half_width * (1.0 - 0.52 * self.hy)
        radial = np.clip(np.abs(self.xw - 0.06 * sway) / np.maximum(hw, 1e-3), 0.0, 2.0)

        # Threshold rises with height and toward the edges -> tongues taper,
        # detach and die out near the top. `n` is normalised to mean 0.5 /
        # std 0.25, so these numbers sit meaningfully inside its actual range:
        # ~0.34 at the base passes most of the field, ~1.05 at the tip passes
        # almost none, and the sweep between them is where tongues form.
        thresh = (
            0.30
            + 0.52 * self.hy ** 0.85
            + 0.34 * radial ** 2.6
            - 0.09 * (bed - 0.72)
        )
        # The softness (denominator) is wide on purpose. A narrow band made most
        # of the base saturate at 1.0, which rendered the fire as a flat white
        # slab; a wide band keeps the base a GRADIENT, so the colour ramp gets to
        # do its job and tongues have interior structure instead of a hard edge.
        temp = np.clip((n - thresh) / 0.42, 0.0, 1.0) * self.above

        # Fade the very bottom into the log line so flames emerge from the wood
        # rather than being cut off by a hard edge.
        temp *= np.clip((self.fuel_y + 0.13 - self.yw) / 0.26, 0.0, 1.0)
        temp = temp ** 1.35

        # ------------------------------------------------------------ emission
        emission = ramp(temp, FIRE_RAMP)

        # Physically-motivated blue reaction zone right at the base.
        base_zone = np.clip((0.085 - self.hy) / 0.085, 0.0, 1.0) * temp
        emission[..., 2] += 0.115 * base_zone ** 2.0
        emission[..., 1] += 0.045 * base_zone ** 2.0

        # Bloom: fire is the light source, so it must bleed into its surroundings.
        lum = temp
        glow_r = max(2, self.w // 90)
        emission += blur(lum, glow_r, passes=3)[..., None] * np.array(
            [0.62, 0.24, 0.055], dtype=np.float32
        )

        # ---------------------------------------------------------------- smoke
        # Only above the flame tips, and only where the flame is NOT bright.
        # Simulated at 1/3 of sim resolution — smoke has no fine detail, and the
        # blur below erases the nearest-neighbour expansion entirely.
        s = self._resample(self.smoke_n.field(frame))
        smoke = np.clip((s - 0.60) / 0.30, 0.0, 1.0)
        smoke *= np.clip((self.hy - 0.38) / 0.30, 0.0, 1.0)
        smoke *= np.clip(1.0 - temp * 2.2, 0.0, 1.0)
        smoke *= np.clip(1.0 - radial * 0.55, 0.0, 1.0)
        smoke = blur(smoke, max(2, self.w // 110), passes=2) * 0.20

        # ---------------------------------------------------------------- light
        # A broad, heavily blurred version of the emission drives the relighting
        # of the hearth. Because it derives from `temp`, the cabin lighting
        # flickers in exact sympathy with the flames — no separate LFO needed.
        light = blur(lum, max(3, self.w // 16), passes=3)
        light += 0.55 * blur(lum, max(6, self.w // 8), passes=2)
        peak = float(light.max()) or 1.0
        light = np.clip(light / peak, 0.0, 1.0)

        return FlameFrame(
            emission=emission,
            smoke=smoke.astype(np.float32),
            light=light.astype(np.float32),
            intensity=float(np.clip(lum.mean() * 7.0, 0.0, 1.0)),
        )
