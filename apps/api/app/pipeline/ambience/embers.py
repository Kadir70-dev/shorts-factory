"""
Rising ember particles, drawn at native 4K.

Embers are the one moving element that must stay SHARP — they are tiny bright
points, and running them through the flame layer's 3x upscale would smear them
into little orange smudges. They are sparse enough (a few hundred stamps of
~24 px) that drawing them at full resolution costs almost nothing.

Periodicity is again by construction rather than by fading the ends together.
Every particle owns a fixed phase offset and its entire state is a function of

    a = (loop_phase + phase_j) mod 1

so after exactly one loop each particle is back precisely where it started. Each
particle's alpha envelope is zero at both a=0 and a=life_j, so nothing ever pops
into or out of existence at the loop seam.

Colour follows cooling: a fresh ember leaves the fire yellow-hot and decays
through orange to a dull red before it goes out.
"""
from __future__ import annotations

import numpy as np

from .noise import loop_phase


def _stamp(radius: int) -> np.ndarray:
    """Normalised round falloff used as the ember sprite."""
    d = np.arange(-radius, radius + 1, dtype=np.float32)
    r2 = (d[:, None] ** 2 + d[None, :] ** 2) / float(radius * radius)
    s = np.clip(1.0 - r2, 0.0, 1.0) ** 1.8
    core = np.clip(1.0 - r2 * 5.0, 0.0, 1.0) ** 2.0     # hot centre
    return (s * 0.55 + core * 0.85).astype(np.float32)


class EmberField:
    """Exactly-periodic ember particle system."""

    def __init__(
        self,
        width: int,
        height: int,
        frames: int,
        *,
        count: int = 190,
        seed: int = 23,
        fuel_y: float = 0.19,
    ) -> None:
        self.w, self.h, self.frames = int(width), int(height), int(frames)
        rng = np.random.default_rng(seed)
        n = int(count)

        self.phase = rng.random(n).astype(np.float32)
        # spawn clustered over the fuel bed, denser toward the middle
        self.x0 = (rng.normal(0.0, 0.30, n).astype(np.float32)
                   + rng.uniform(-0.22, 0.22, n).astype(np.float32))
        self.y0 = np.float32(fuel_y) + rng.uniform(-0.09, 0.05, n).astype(np.float32)

        # Short-lived sparks vs long-lived floaters: the mix is what stops the
        # field looking like a uniform particle emitter.
        self.life = np.where(
            rng.random(n) < 0.35,
            rng.uniform(0.16, 0.34, n),
            rng.uniform(0.42, 0.92, n),
        ).astype(np.float32)

        self.rise = rng.uniform(0.30, 0.95, n).astype(np.float32)
        self.drift = rng.normal(0.0, 0.30, n).astype(np.float32)
        self.wobble_a = rng.uniform(0.010, 0.075, n).astype(np.float32)
        self.wobble_f = rng.integers(1, 5, n).astype(np.float32)     # integer -> periodic
        self.wobble_p = rng.random(n).astype(np.float32) * np.float32(2 * np.pi)
        self.bright = rng.uniform(0.12, 0.62, n).astype(np.float32) ** 1.9

        sizes = rng.integers(1, 4, n)
        self.size = sizes.astype(np.int32)
        px = max(1, height // 1080)                    # scale sprite with output
        self._stamps = {int(s): _stamp(int(s) * px + 1) for s in np.unique(sizes)}

    def draw(self, frame: int, target: np.ndarray) -> None:
        """Additively composite this frame's embers into a linear (H, W, 3) buffer."""
        ph = loop_phase(frame, self.frames)
        a = (ph + self.phase) % 1.0
        alive = a < self.life
        if not alive.any():
            return

        idx = np.nonzero(alive)[0]
        t = a[idx] / self.life[idx]                   # 0..1 through the lifetime

        # Rise decelerates as the ember cools and loses buoyancy.
        climb = (1.0 - (1.0 - t) ** 1.7) * self.rise[idx]
        yw = self.y0[idx] - climb * 0.95
        xw = (
            self.x0[idx]
            + self.drift[idx] * t * 0.75
            + self.wobble_a[idx] * np.sin(self.wobble_f[idx] * 2 * np.pi * t + self.wobble_p[idx])
        )

        # Envelope: quick ignite, long cooling fade, exactly zero at both ends.
        alpha = np.clip(t / 0.10, 0.0, 1.0) * (1.0 - t) ** 1.5
        alpha *= self.bright[idx]

        # Cooling colour: yellow-hot -> orange -> dull red.
        cool = t
        r = 2.30 - 0.55 * cool
        g = 1.05 * (1.0 - cool) ** 1.25 + 0.10
        b = 0.30 * (1.0 - cool) ** 3.0

        # world -> pixel
        px = (xw * (self.h / 2.0) + self.w / 2.0).astype(np.int32)
        py = (yw * (self.h / 2.0) + self.h / 2.0).astype(np.int32)

        H, W = self.h, self.w
        for k in range(len(idx)):
            st = self._stamps[int(self.size[idx[k]])]
            rr = st.shape[0] // 2
            cx, cy = int(px[k]), int(py[k])
            x0, x1 = cx - rr, cx + rr + 1
            y0, y1 = cy - rr, cy + rr + 1
            if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
                continue
            sx0, sy0 = max(0, -x0), max(0, -y0)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(W, x1), min(H, y1)
            sub = st[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)] * alpha[k]
            tgt = target[y0:y1, x0:x1]
            tgt[..., 0] += sub * r[k]
            tgt[..., 1] += sub * g[k]
            tgt[..., 2] += sub * b[k]
