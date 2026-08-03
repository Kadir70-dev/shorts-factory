"""
Small, dependency-free image maths: separable blur, upscale, colour ramps.

scipy is deliberately NOT a dependency here (it is not installed in the venv and
pulling it in for two convolutions is not worth it), so the blur is a triple box
pass built on cumulative sums. Three boxes approximate a Gaussian closely enough
for glow/bloom work and run in O(n) regardless of radius, which matters because
the bloom radius at 4K is large.

The render is deliberately split by sharpness:
  * the hearth plate is native 4K, because logs, bark and ash must stay crisp;
  * flame / smoke / light fields are simulated small and upscaled, because they
    are genuinely soft — this is the standard compositing trick and it is what
    makes CPU-only 4K60 feasible at all (a 3x linear downscale is ~9x less work).
"""
from __future__ import annotations

import numpy as np


def box_blur_1d(a: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """Edge-clamped box blur along one axis via cumulative sums."""
    if radius < 1:
        return a
    a = np.moveaxis(a, axis, -1)
    n = a.shape[-1]
    radius = min(radius, max(1, n - 1))

    pad = np.concatenate(
        [
            np.repeat(a[..., :1], radius + 1, axis=-1),
            a,
            np.repeat(a[..., -1:], radius, axis=-1),
        ],
        axis=-1,
    )
    c = np.cumsum(pad, axis=-1, dtype=np.float32)
    win = 2 * radius + 1
    out = (c[..., win:] - c[..., :-win]) / np.float32(win)
    return np.moveaxis(out, -1, axis)


def blur(a: np.ndarray, radius: int, passes: int = 3) -> np.ndarray:
    """Separable approximate Gaussian over the SPATIAL axes (0 and 1).

    Axes are pinned to 0/1 rather than -2/-1 so this behaves identically on a
    2-D field and on an (H, W, 3) image. Using negative axes silently blurred
    across the colour channels of RGB inputs instead of down the height.
    """
    if radius < 1:
        return a
    out = a
    for _ in range(passes):
        out = box_blur_1d(out, radius, 0)
        out = box_blur_1d(out, radius, 1)
    return out


def resize_bilinear(a: np.ndarray, h: int, w: int, wrap: bool = False) -> np.ndarray:
    """Bilinear (quintic-faded) resample to (h, w).

    `repeat`+blur was not good enough for texture synthesis — box blur leaves
    faceted squares at low octaves, which read as compression blocks on the
    finished plate. A real interpolated resample removes them outright.

    `wrap=True` makes the result tile, which is what texture octaves need.
    """
    ih, iw = a.shape[:2]
    y = (np.arange(h, dtype=np.float32) + 0.5) * (ih / h) - 0.5
    x = (np.arange(w, dtype=np.float32) + 0.5) * (iw / w) - 0.5
    y0 = np.floor(y).astype(np.int64)
    x0 = np.floor(x).astype(np.int64)
    ty = smootherstep((y - y0).astype(np.float32))[:, None]
    tx = smootherstep((x - x0).astype(np.float32))[None, :]

    if wrap:
        y0c, y1c, x0c, x1c = y0 % ih, (y0 + 1) % ih, x0 % iw, (x0 + 1) % iw
    else:
        y0c = np.clip(y0, 0, ih - 1)
        y1c = np.clip(y0 + 1, 0, ih - 1)
        x0c = np.clip(x0, 0, iw - 1)
        x1c = np.clip(x0 + 1, 0, iw - 1)

    r0, r1 = a[y0c], a[y1c]
    top = r0[:, x0c] * (1.0 - tx) + r0[:, x1c] * tx
    bot = r1[:, x0c] * (1.0 - tx) + r1[:, x1c] * tx
    return (top * (1.0 - ty) + bot * ty).astype(np.float32)


def smootherstep(t: np.ndarray) -> np.ndarray:
    """Local copy of the quintic fade so imaging has no import cycle."""
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def upscale(a: np.ndarray, factor: int, smooth: int = 1,
            final_pass: bool = True) -> np.ndarray:
    """Nearest-neighbour ×factor with the smoothing done mostly BEFORE the expand.

    Order matters enormously at 4K. Expanding first and then running a
    multi-pass blur means every pass touches 8.3M pixels; pre-smoothing at
    simulation resolution costs factor^2 less for the same visual result,
    leaving only ONE cheap separable pass at full resolution to remove the
    pixel-doubling staircase. On the 4K frame this is the difference between
    ~4 full-res blur passes and ~1.
    """
    if factor == 1:
        return a
    if smooth:
        a = blur(a, max(1, smooth), passes=1)
    out = np.repeat(np.repeat(a, factor, axis=0), factor, axis=1)
    if not final_pass:
        # Caller has pre-smoothed enough at simulation resolution that the
        # residual staircase is invisible. Skipping the full-res pass saves two
        # cumsum sweeps over a 100 MB array, which is worth real minutes per
        # thousand frames on the 3-channel emission layer.
        return out
    r = max(1, factor // 2 + 1)
    out = box_blur_1d(out, r, 0)
    return box_blur_1d(out, r, 1)


def ramp(x: np.ndarray, stops: list[tuple[float, tuple[float, float, float]]]) -> np.ndarray:
    """Piecewise-linear colour ramp. `x` is (H, W); returns (H, W, 3) float32.

    Used for the blackbody-ish fire gradient. Interpolating in linear light (the
    caller keeps everything linear until the final encode) is what stops the
    red->yellow transition going through a muddy brown.
    """
    pos = np.array([s[0] for s in stops], dtype=np.float32)
    col = np.array([s[1] for s in stops], dtype=np.float32)       # (S, 3)

    xc = np.clip(x, pos[0], pos[-1])
    idx = np.clip(np.searchsorted(pos, xc, side="right") - 1, 0, len(pos) - 2)

    p0 = pos[idx]
    span = np.maximum(pos[idx + 1] - p0, 1e-6)
    t = ((xc - p0) / span)[..., None]
    return (col[idx] * (1.0 - t) + col[idx + 1] * t).astype(np.float32)


_SRGB_LUT: np.ndarray | None = None


def _srgb_lut() -> np.ndarray:
    """4096-entry sRGB encode table, built once."""
    global _SRGB_LUT
    if _SRGB_LUT is None:
        t = np.linspace(0.0, 1.0, 4096, dtype=np.float32)
        srgb = np.where(t <= 0.0031308, t * 12.92,
                        1.055 * np.power(t, 1 / 2.4) - 0.055)
        _SRGB_LUT = (srgb * 255.0 + 0.5).astype(np.uint8)
    return _SRGB_LUT


def to_srgb_u8(linear: np.ndarray) -> np.ndarray:
    """Linear float RGB -> gamma-encoded uint8, with a filmic-ish shoulder.

    The shoulder matters: fire cores blow past 1.0 constantly, and a hard clip
    turns every bright tongue into a flat white blob with a hard edge, which is
    exactly the "AI artifact" look the brief rules out. Reinhard-style
    compression keeps highlight detail inside the flame.

    The gamma curve goes through a lookup table rather than np.power. Profiling
    the 4K frame put `np.power` over 25M elements at 1.2 s — by far the single
    most expensive operation in the whole compositor. A 12-bit LUT is visually
    identical (the output is 8-bit anyway) and turns it into a gather.
    """
    x = np.maximum(linear, 0.0)
    x /= (1.0 + x * 0.55)                       # gentle highlight rolloff
    x *= 1.18                                   # restore mid contrast
    np.clip(x, 0.0, 1.0, out=x)
    x *= 4095.0
    return _srgb_lut()[x.astype(np.uint16)]


def vignette(height: int, width: int, strength: float = 0.35, softness: float = 1.1) -> np.ndarray:
    """Radial falloff (H, W). Sells the 'dark cabin, single light source' read."""
    yy = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
    xx = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
    r = np.sqrt(xx * xx + yy * yy * 1.15) / softness
    return (1.0 - strength * np.clip(r, 0.0, 1.0) ** 2).astype(np.float32)


def write_png(path, rgb_u8: np.ndarray) -> None:
    """Minimal zlib PNG writer, used for proof frames and the thumbnail.

    Pillow is not in the venv and this pipeline hands finished frames straight to
    ffmpeg over a pipe, so a ~15-line encoder is cheaper than a new dependency.
    """
    import struct
    import zlib

    h, w, _ = rgb_u8.shape
    raw = bytearray()
    for y in range(h):
        raw.append(0)                       # filter type 0 (None)
        raw.extend(rgb_u8[y].tobytes())

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        fh.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        fh.write(chunk(b"IEND", b""))
