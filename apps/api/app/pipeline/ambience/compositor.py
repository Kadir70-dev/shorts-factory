"""
Per-frame compositor: relight the 4K hearth plate from the flame, then stack.

Layer order matches the physics of the shot:

    1. hearth plate, RELIT by this frame's fire-light field (ambient is almost
       nothing — the fire is the only light source in the room)
    2. coal / bark-crack glow rising through the ember mask
    3. smoke (multiplicative haze + a little scattered fire light)
    4. flame emission (additive)
    5. sharp 4K ember particles (additive)
    6. vignette, subtle grain, tone-map to sRGB uint8

The dynamic lighting is the piece that makes it feel like a real room instead of
a fire sprite on a photo: `respond` (baked cylinder/ash normals) times `light`
(a heavily blurred version of this frame's own flame) means every flicker of the
flame rolls across the logs and the back wall in exact sympathy. Nothing is on
an LFO; the light IS the fire.

Soft layers arrive at simulation resolution and are upscaled here; only the
plate and the embers are native 4K. Buffers are reused across frames because the
render box has 3 GB of RAM total.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .embers import EmberField
from .flame import FlameSim
from .hearth import HearthPlate, build_plate
from .imaging import blur, to_srgb_u8, upscale, vignette
from .noise import loop_phase

# Warm colour of the light the fire throws into the room (linear RGB).
FIRE_LIGHT = np.array([1.00, 0.455, 0.150], dtype=np.float32)
# What little light is NOT from the fire: cold moonlight through a window.
AMBIENT = np.array([0.0125, 0.0148, 0.0210], dtype=np.float32)


@dataclass
class SceneConfig:
    width: int = 3840
    height: int = 2160
    fps: int = 60
    loop_seconds: float = 90.0
    sim_divisor: int = 3          # flame/smoke sim runs at 1/3 linear resolution
    seed: int = 7
    ember_count: int = 190
    grain: float = 0.0022

    @property
    def frames(self) -> int:
        return int(round(self.loop_seconds * self.fps))

    @property
    def sim_size(self) -> tuple[int, int]:
        return self.width // self.sim_divisor, self.height // self.sim_divisor


class Compositor:
    def __init__(self, cfg: SceneConfig, plate: HearthPlate | None = None) -> None:
        self.cfg = cfg
        sw, sh = cfg.sim_size

        self.plate = plate if plate is not None else build_plate(cfg.width, cfg.height, cfg.seed)
        self.flame = FlameSim(sw, sh, cfg.frames, seed=cfg.seed + 4)
        self.embers = EmberField(
            cfg.width, cfg.height, cfg.frames,
            count=cfg.ember_count, seed=cfg.seed + 9,
        )

        self.vig = vignette(cfg.height, cfg.width, strength=0.42, softness=1.16)[..., None]
        self._rng = np.random.default_rng(cfg.seed + 77)

        # ---- precomputed static products -----------------------------------
        # The relight is albedo * (AMBIENT + FIRE_LIGHT * respond * light * k).
        # Only `light` changes per frame, so everything else is folded once here.
        # This removes several 100 MB temporaries from every single frame, which
        # on a 3 GB box is the difference between running at memory bandwidth and
        # thrashing the allocator.
        self._amb = (self.plate.albedo * AMBIENT).astype(np.float32)
        self._base = (
            self.plate.albedo * self.plate.respond[..., None] * FIRE_LIGHT * 3.85
        ).astype(np.float32)
        self._coal_rgb = (
            self.plate.ember_mask[..., None]
            * np.array([0.52, 0.118, 0.017], dtype=np.float32)
        ).astype(np.float32)

        # Free the parts of the plate that are now baked into the products
        # above. At 4K each of these is ~100 MB and nothing reads them again.
        self.plate.albedo = np.empty((0, 0, 3), dtype=np.float32)
        self.plate.ao = np.empty((0, 0), dtype=np.float32)
        self.plate.log_mask = np.empty((0, 0), dtype=np.float32)

        # Ember glow gets its own slow flicker so coals breathe independently of
        # the flame above them — real coals pulse much more slowly than flames.
        self._coal_phase = self._rng.random(6).astype(np.float32) * np.float32(2 * np.pi)
        self._coal_freq = np.arange(1, 7, dtype=np.float32)      # integer -> periodic

    # ------------------------------------------------------------------ frame
    def frame(self, i: int) -> np.ndarray:
        cfg = self.cfg
        f = self.flame.step(i)
        k = cfg.sim_divisor

        light = upscale(f.light, k, smooth=2)
        light = light[: cfg.height, : cfg.width]

        # 1. relight the plate ------------------------------------------------
        # In-place throughout: `rgb` is allocated once and every stage below
        # writes into it rather than building a new 100 MB array.
        rgb = self._base * light[..., None]
        rgb += self._amb

        # 2. coals and bark cracks glowing from within ------------------------
        ph = loop_phase(i, cfg.frames)
        pulse = 0.68 + 0.32 * float(
            np.mean(np.sin(self._coal_freq * 2 * np.pi * ph + self._coal_phase))
            * 1.6
        )
        coal = light * (0.55 * pulse)
        coal += 0.30 * pulse
        rgb += self._coal_rgb * coal[..., None]

        # 3. smoke: hazes what is behind it and picks up scattered fire light --
        smoke = upscale(f.smoke, k, smooth=2, final_pass=False)[: cfg.height, : cfg.width][..., None]
        rgb *= (1.0 - smoke * 0.72)
        rgb += smoke * (
            np.array([0.115, 0.082, 0.070], dtype=np.float32)
            + (FIRE_LIGHT * 0.16) * light[..., None]
        )

        # 4. flame emission ---------------------------------------------------
        rgb += upscale(f.emission, k, smooth=3, final_pass=False)[: cfg.height, : cfg.width]

        # 5. sharp embers -----------------------------------------------------
        self.embers.draw(i, rgb)

        # 6. finish -----------------------------------------------------------
        rgb *= self.vig

        # A whisper of grain. Two jobs: it hides banding in the huge dark
        # gradients (which x264 would otherwise turn into visible contours), and
        # it removes the last of the "rendered" cleanliness.
        #
        # It is scaled by local luminance on purpose. Flat linear-light grain
        # looked fine in the mids but exploded into visible black-sky speckle
        # once the sRGB curve stretched the shadows, so the amplitude has to
        # follow the signal rather than sit on top of it.
        if cfg.grain > 0:
            # Generated at quarter resolution and expanded: grain this fine is
            # indistinguishable at 4K and the 2M-sample draw was costing more
            # than the composite stage it protects.
            noise = self._rng.standard_normal(
                (cfg.height // 4, cfg.width // 4), dtype=np.float32
            )
            noise = np.repeat(np.repeat(noise, 4, axis=0), 4, axis=1)
            lum = rgb[..., 0]
            np.sqrt(np.clip(lum, 0.0, 4.0), out=(amp := np.empty_like(lum)))
            amp += 0.10
            amp *= cfg.grain
            amp *= noise[: cfg.height, : cfg.width]
            rgb += amp[..., None]

        return to_srgb_u8(rgb)

    # ----------------------------------------------------------------- helpers
    def light_curve(self) -> np.ndarray:
        """Per-frame flame intensity. Used by QA to prove the loop is periodic."""
        return np.array([self.flame.step(i).intensity for i in range(self.cfg.frames)])


def bloom_pass(rgb: np.ndarray, radius: int, amount: float) -> np.ndarray:
    """Optional wide bloom over the finished linear frame (used for the thumbnail,
    where a heavier, more 'photographic' glow is wanted than in motion)."""
    lum = rgb.max(axis=-1)
    hi = np.clip(lum - 0.75, 0.0, None)
    return rgb + blur(hi, radius, passes=3)[..., None] * np.array(
        [amount, amount * 0.42, amount * 0.14], dtype=np.float32
    )
