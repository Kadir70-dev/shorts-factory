"""
The static 4K hearth plate: firebox wall, ash bed and burning logs.

This is rendered ONCE per job, not per frame, which is what buys us native 4K
detail on the things the eye actually checks for sharpness — bark ridges, log
silhouettes, ash texture, mortar lines. Everything that moves (flame, smoke,
embers, light) is simulated small and composited on top; see imaging.py.

The plate is returned in LINEAR light and carries more than colour, because the
compositor has to relight it every frame from a flickering source:

  albedo     surface colour, unlit
  respond    how strongly a pixel faces the fire (cylindrical normals on logs,
             upward-facing bias on the ash bed) -> drives the dynamic lighting
  ao         contact shadow / crevice darkening, baked
  ember_mask where coals and bark cracks can glow through from underneath

Everything is procedural and seeded, so the output is an original asset with no
third-party texture, footage or model anywhere in its provenance.

Realism notes that cost nothing but matter a lot:
  * log radius varies along the axis, so silhouettes are never perfect capsules
    (perfect capsules are the single clearest "this is CG" tell);
  * cylinder curvature is baked into albedo, not just AO, so logs read as round
    even before the fire relights them;
  * the firebox is genuinely dark — almost everything you see in the final frame
    is light the fire is putting out, which is what makes the flicker convincing.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .imaging import blur, resize_bilinear


# --------------------------------------------------------------------------- #
# texture helpers
# --------------------------------------------------------------------------- #
def fbm2(h: int, w: int, rng: np.random.Generator, octaves: int = 7,
         base: int = 4, gain: float = 0.5) -> np.ndarray:
    """Static, tiling 2-D fBm. Values ~[0, 1].

    Each octave is a small random lattice bilinearly resampled to full size.
    (An earlier repeat+box-blur version left visible square facets — see
    imaging.resize_bilinear.)
    """
    out = np.zeros((h, w), dtype=np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        n = base * (2 ** o)
        if n > max(h, w):
            break
        small = rng.random((max(2, n * h // w), n), dtype=np.float32)
        out += amp * resize_bilinear(small, h, w, wrap=True)
        norm += amp
        amp *= gain
    return out / norm


def sample_tex(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Wrapped nearest-neighbour texture fetch. `tex` is smooth by construction,
    so skipping bilinear filtering here is invisible and saves three gathers."""
    th, tw = tex.shape
    iu = (u * tw).astype(np.int64) % tw
    iv = (v * th).astype(np.int64) % th
    return tex[iv, iu]


@dataclass
class HearthPlate:
    albedo: np.ndarray      # (H, W, 3) linear
    respond: np.ndarray     # (H, W) 0..1.4 light response
    ao: np.ndarray          # (H, W) 0..1
    ember_mask: np.ndarray  # (H, W) 0..1
    log_mask: np.ndarray    # (H, W) 0..1


# --------------------------------------------------------------------------- #
# scene layout
# --------------------------------------------------------------------------- #
# (cx, cy, angle_deg, half_len, radius, char) in world units (1 unit = H/2 px)
_LOGS = [
    (-0.05, 0.505, -5.0, 1.00, 0.190, 0.82),
    (0.36, 0.472, 7.0, 0.76, 0.162, 0.68),
    (-0.60, 0.395, 20.0, 0.52, 0.132, 0.88),
    (0.04, 0.297, -4.0, 0.80, 0.152, 0.50),
]


def _world_coords(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Aspect-correct world grid: 1 unit == H/2 px on both axes, y downward."""
    y = (np.arange(h, dtype=np.float32) - h / 2.0) / (h / 2.0)
    x = (np.arange(w, dtype=np.float32) - w / 2.0) / (h / 2.0)
    return x[None, :], y[:, None]


def build_plate(width: int, height: int, seed: int = 7) -> HearthPlate:
    rng = np.random.default_rng(seed)
    xw, yw = _world_coords(height, width)
    v = (np.arange(height, dtype=np.float32) / height)[:, None]
    u = (np.arange(width, dtype=np.float32) / width)[None, :]

    # Wall/ash textures are generated at PLATE resolution and indexed directly.
    # Tiling a small texture across the frame (the obvious cheap option) made the
    # repeat plainly visible as a checkerboard in the ash — fbm has too much
    # low-frequency structure to hide a 7x repeat. Only the bark stays a small
    # tile, because logs need sampling in rotated coordinates and each log covers
    # well under one tile.
    grain = fbm2(height, width, rng, octaves=9, base=3)
    soot = fbm2(height, width, rng, octaves=7, base=2)
    fine = fbm2(height, width, rng, octaves=6, base=24)
    bark_tex = fbm2(1024, 1024, rng, octaves=8, base=3)

    ao = np.ones((height, width), dtype=np.float32)
    ember = np.zeros((height, width), dtype=np.float32)
    logs = np.zeros((height, width), dtype=np.float32)

    # ---------------------------------------------------------------- back wall
    # Sooty firebrick, small courses, staggered joints. Base albedo is very low:
    # a firebox interior is near-black, and everything the viewer ends up seeing
    # is fire light bouncing off it.
    brick_h, brick_w = 0.052, 0.150
    # per-course horizontal jitter so joints are not machine-perfect
    row = np.floor(v / brick_h)
    jitter = sample_tex(bark_tex, row * 0.021, row * 0.017) * 0.35
    bu = (u / brick_w + (row % 2.0) * 0.5 + jitter) % 1.0
    bv = (v / brick_h) % 1.0
    mortar = np.clip(
        np.minimum(bu, 1.0 - bu) / 0.055, 0.0, 1.0
    ) * np.clip(np.minimum(bv, 1.0 - bv) / 0.13, 0.0, 1.0)

    g = grain
    gf = fine
    brick_col = np.stack(
        [0.062 + 0.045 * g + 0.012 * gf,
         0.034 + 0.021 * g + 0.007 * gf,
         0.024 + 0.012 * g + 0.004 * gf], axis=-1
    )
    mortar_col = np.stack(
        [0.040 + 0.020 * g, 0.034 + 0.016 * g, 0.030 + 0.013 * g], axis=-1
    )
    wall = mortar_col + (brick_col - mortar_col) * mortar[..., None]

    # heavy soot deposit rising up the back wall, blotchy not linear
    sootiness = np.clip(1.25 - v * 2.05, 0.05, 1.0) * (0.55 + 0.62 * soot)
    wall *= np.clip(sootiness, 0.03, 1.0)[..., None]

    albedo = wall
    respond = 0.92 * np.clip(1.12 - v * 0.90, 0.0, 1.0)
    ao *= 0.50 + 0.50 * np.clip(v * 1.7, 0.0, 1.0)

    # ------------------------------------------------------------------ ash bed
    floor_v = 0.740
    edge = np.clip((v - floor_v) / 0.045, 0.0, 1.0)
    ash_g = grain
    ash_f = fine
    ash_col = np.stack(
        [0.052 + 0.048 * ash_g + 0.022 * ash_f,
         0.043 + 0.036 * ash_g + 0.016 * ash_f,
         0.040 + 0.030 * ash_g + 0.013 * ash_f], axis=-1
    )
    heap = np.clip(1.0 - (np.abs(xw) / 1.50) ** 2, 0.0, 1.0)
    ash_col *= (0.26 + 0.44 * heap)[..., None]

    albedo = albedo * (1.0 - edge[..., None]) + ash_col * edge[..., None]
    respond = respond * (1.0 - edge) + edge * (0.60 + 0.32 * heap)
    ao *= 1.0 - 0.38 * edge * (1.0 - heap)

    # Live coals in the ash: clustered, biased to the centre of the heap.
    coal = 0.5 * soot + 0.5 * grain
    coal_field = np.clip((coal - 0.56) / 0.22, 0.0, 1.0) ** 2.6
    ember += edge * coal_field * heap * 1.05

    # ---------------------------------------------------------------------- logs
    for (cx, cy, ang, half, rad, char) in _LOGS:
        a = np.deg2rad(ang)
        ca, sa = float(np.cos(a)), float(np.sin(a))
        dx, dy = xw - cx, yw - cy
        axial = dx * ca + dy * sa
        perp = -dx * sa + dy * ca

        # Irregular radius along the axis — the single biggest anti-CG win.
        wob = sample_tex(bark_tex, axial * 0.30 + cx * 2.0, np.full_like(perp, cy * 3.0))
        rad_l = rad * (0.86 + 0.30 * wob)

        # Round the ends into a capsule. A hard axial cut is what made the pile
        # read as stacked planks rather than as split firewood.
        end_t = np.clip((np.abs(axial) - half * 0.82) / (half * 0.18), 0.0, 1.0)
        rad_l = np.maximum(rad_l * np.sqrt(np.maximum(1.0 - end_t * end_t, 0.0)), 1e-5)

        inside = (np.abs(axial) <= half) & (np.abs(perp) <= rad_l)
        if not inside.any():
            continue

        s = np.clip(perp / rad_l, -1.0, 1.0)
        depth = np.sqrt(np.maximum(1.0 - s * s, 0.0))      # cylinder normal z
        mask = inside.astype(np.float32)
        mask *= np.clip((rad_l - np.abs(perp)) / (rad * 0.055), 0.0, 1.0)
        mask *= np.clip((half - np.abs(axial)) / (half * 0.02), 0.0, 1.0)

        # Bark: hard streaks stretched along the axis, plus deep splitting ridges.
        bu_l = axial * 0.34 + cx * 1.7
        bv_l = perp * 5.0 + cy * 2.3
        bark = sample_tex(bark_tex, bu_l, bv_l)
        ridge = sample_tex(bark_tex, bu_l * 2.0 + 0.31, bv_l * 0.70)
        knot = sample_tex(grain, bu_l * 0.9, bv_l * 0.9)
        # Low contrast on purpose: high-contrast bark across the log thickness
        # broke every log into thin bright bands and the pile read as wicker.
        bark_d = np.clip(0.80 + 0.27 * bark - 0.14 * ridge + 0.08 * knot, 0.30, 1.35)

        char_amt = np.clip(char * (0.50 + 0.80 * (0.5 - s * 0.5)), 0.0, 1.0)
        raw = np.stack([0.092 * bark_d, 0.046 * bark_d, 0.020 * bark_d], axis=-1)
        charred = np.stack(
            [0.020 + 0.024 * bark, 0.015 + 0.015 * bark, 0.014 + 0.011 * bark], axis=-1
        )
        log_col = raw * (1.0 - char_amt[..., None]) + charred * char_amt[..., None]

        # Bake curvature into albedo so logs read as round pre-lighting.
        curve = (0.10 + 0.90 * depth ** 1.65)[..., None]
        log_col = log_col * curve

        shadow = blur(mask, max(2, height // 150), passes=2)
        ao *= 1.0 - 0.40 * np.clip(shadow - mask, 0.0, 1.0)

        m3 = mask[..., None]
        albedo = albedo * (1.0 - m3) + log_col * m3
        logs = np.maximum(logs, mask)

        # Cylindrical light response: the fire is above, so upper faces catch it.
        facing = np.clip(depth * 0.72 - s * 0.78, 0.0, 1.0)
        respond = respond * (1.0 - mask) + mask * np.clip(0.09 + 1.05 * facing, 0.0, 1.40)
        ao = ao * (1.0 - mask) + mask * (0.34 + 0.66 * depth) * (1.0 - 0.22 * char_amt)

        # Glowing cracks: deep char in the ridge valleys.
        cracks = np.clip((0.360 - ridge) / 0.180, 0.0, 1.0) ** 3.2 * char_amt
        ember = np.maximum(ember, mask * cracks * 0.75)

    # Contact shadow where the pile meets the ash.
    contact = blur(logs, max(2, height // 170), passes=2)
    ao *= 1.0 - 0.32 * np.clip(contact - logs, 0.0, 1.0) * np.clip((v - 0.52) * 3.0, 0.0, 1.0)

    albedo = albedo * ao[..., None]

    return HearthPlate(
        albedo=np.ascontiguousarray(albedo, dtype=np.float32),
        respond=np.clip(respond, 0.0, 1.4).astype(np.float32),
        ao=ao.astype(np.float32),
        ember_mask=np.clip(ember, 0.0, 1.0).astype(np.float32),
        log_mask=logs.astype(np.float32),
    )
