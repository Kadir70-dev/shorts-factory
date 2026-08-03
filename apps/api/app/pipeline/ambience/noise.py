"""
Tileable, exactly-periodic 3-D value noise (the loop's core invariant).

The whole long-form ambience idea rests on ONE guarantee: a T-second clip whose
last frame flows into its first with no discontinuity, so ffmpeg can stream-copy
it 60x into a 2-hour master and the viewer never sees a seam.

Perfect periodicity is therefore not a polish item, it is the invariant, and it
is enforced BY CONSTRUCTION rather than by crossfading the ends together:

  * the value lattice wraps on all three axes (modular gather), so walking the
    z axis over exactly one lattice period returns to the starting slice;
  * every octave shares that same z period, so their sum is periodic too;
  * the upward "rise" of flame/smoke is a y-scroll of an INTEGER number of
    lattice periods per loop, so advection wraps at the same instant.

Nothing dissolves or blends. Frame N is frame 0 to the bit, up to encoder
quantisation. That is what lets `encode.py` use `-c copy`.

Sampling cost is kept low by separating the interpolation: the x-axis lerp is
done on the (small) lattice first, giving an (Ly, W) strip, and only the y-axis
lerp touches full output resolution. Two z-slices per frame, so a 5-octave field
costs ~20 * H * W float ops — fast enough for CPU-only rendering.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def smootherstep(t: np.ndarray) -> np.ndarray:
    """Quintic fade 6t^5-15t^4+10t^3. C2-continuous, so no lattice creasing."""
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


@dataclass(frozen=True)
class Octave:
    """One frequency band of the fBm. `lattice` wraps on every axis."""
    lattice: np.ndarray      # (Lz, Ly, Lx) float32
    amplitude: float
    x_periods: float         # lattice periods spanned across the output width
    y_periods: float         # ... across the output height
    y_scroll_periods: int    # INTEGER periods scrolled per loop -> stays periodic


class PeriodicFBM:
    """Fractal Brownian motion that is exactly periodic over `frames`.

    The z axis of every lattice is traversed exactly once per loop, so
    ``field(0)`` and ``field(frames)`` are identical by construction.

    Anisotropy matters for fire: real flames are vertically stretched, so we let
    callers request far fewer lattice periods down y than across x, which
    elongates every structure into a tongue rather than a blob.
    """

    def __init__(
        self,
        width: int,
        height: int,
        frames: int,
        *,
        octaves: int = 5,
        base_x: float = 6.0,
        base_y: float = 3.0,
        base_z: int = 4,
        lacunarity: float = 2.0,
        gain: float = 0.5,
        y_scroll_periods: int = 1,
        z_growth: float = 1.7,
        seed: int = 0,
    ) -> None:
        self.width = int(width)
        self.height = int(height)
        self.frames = int(frames)
        rng = np.random.default_rng(seed)

        self._octaves: list[Octave] = []
        amp = 1.0
        norm = 0.0
        for o in range(octaves):
            fx = base_x * (lacunarity ** o)
            fy = base_y * (lacunarity ** o)
            # z resolution grows more slowly than x/y: fine spatial detail that
            # also churned fast would read as boiling noise, not as fire.
            lz = max(2, int(round(base_z * (z_growth ** o))))
            lx = max(2, int(round(fx)))
            ly = max(2, int(round(fy)))
            self._octaves.append(
                Octave(
                    lattice=rng.random((lz, ly, lx), dtype=np.float32),
                    amplitude=amp,
                    x_periods=float(lx),
                    y_periods=float(ly),
                    # Higher octaves are smaller eddies riding the same updraft;
                    # scaling the scroll with the octave keeps their apparent
                    # rise speed consistent while staying an exact integer.
                    y_scroll_periods=int(y_scroll_periods * (2 ** o)),
                )
            )
            norm += amp
            amp *= gain

        self._norm = float(norm)
        self._x_cache: dict[int, tuple] = {}

        # Contrast normalisation. Summing octaves is a central-limit machine: the
        # raw fBm clusters tightly around 0.5 with a std of only ~0.09, so any
        # downstream threshold either passes everything or nothing and the flame
        # saturates into one solid blob. Measuring the distribution once and
        # rescaling to a known std makes thresholds mean what they look like.
        probe = self._raw(0)
        self._mean = float(probe.mean())
        self._gain = 0.25 / max(float(probe.std()), 1e-6)

    # ---------------------------------------------------------------- x setup
    def _x_terms(self, idx: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Per-octave x gather indices + weights. Fixed for the whole render."""
        cached = self._x_cache.get(idx)
        if cached is not None:
            return cached
        oc = self._octaves[idx]
        lx = oc.lattice.shape[2]
        u = (np.arange(self.width, dtype=np.float32) / self.width) * oc.x_periods
        x0 = np.floor(u).astype(np.int64)
        tx = smootherstep((u - x0).astype(np.float32))
        terms = (x0 % lx, (x0 + 1) % lx, (1.0 - tx), tx)
        self._x_cache[idx] = terms
        return terms

    # ------------------------------------------------------------------ eval
    def _slice(self, oc: Octave, idx: int, z: int, y_off: float) -> np.ndarray:
        """Bilinear sample of one z-slice onto the output grid."""
        lat = oc.lattice[z % oc.lattice.shape[0]]          # (Ly, Lx)
        ly = lat.shape[0]
        x0, x1, wx0, wx1 = self._x_terms(idx)

        # Collapse x on the small lattice first -> (Ly, W). Cheap.
        strip = lat[:, x0] * wx0 + lat[:, x1] * wx1

        v = (np.arange(self.height, dtype=np.float32) / self.height) * oc.y_periods + y_off
        y0 = np.floor(v).astype(np.int64)
        ty = smootherstep((v - y0).astype(np.float32))[:, None]

        return strip[y0 % ly] * (1.0 - ty) + strip[(y0 + 1) % ly] * ty

    def field(self, frame: int) -> np.ndarray:
        """Contrast-normalised fBm for `frame`: mean 0.5, std 0.25, unclipped."""
        return 0.5 + (self._raw(frame) - self._mean) * self._gain

    def _raw(self, frame: int) -> np.ndarray:
        """fBm for `frame`, shape (height, width), before contrast normalisation."""
        phase = (frame % self.frames) / self.frames          # exact wrap at N
        out = np.zeros((self.height, self.width), dtype=np.float32)

        for idx, oc in enumerate(self._octaves):
            lz = oc.lattice.shape[0]
            w = phase * lz
            z0 = int(np.floor(w))
            tz = smootherstep(np.float32(w - z0))
            # y advances an integer number of lattice periods per loop, so the
            # scroll wraps exactly when the z traversal does.
            y_off = -phase * oc.y_scroll_periods * oc.y_periods

            a = self._slice(oc, idx, z0, y_off)
            b = self._slice(oc, idx, z0 + 1, y_off)
            out += oc.amplitude * (a * (1.0 - tz) + b * tz)

        out /= self._norm
        return out


def loop_phase(frame: int, frames: int) -> float:
    """Normalised loop position in [0, 1). The one clock everything shares."""
    return (frame % frames) / float(frames)
