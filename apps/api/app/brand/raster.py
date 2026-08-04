"""
Dependency-free 2D rasteriser (numpy) + ffmpeg encoders.

Why this exists: the pipeline needs branded graphics and animated charts, but the
target box has no Pillow, no cairo and no working manim. numpy is already a
dependency and ffmpeg is the render backbone — that is enough to draw everything
we need, and it keeps `pip install` out of the critical path forever.

Antialiasing uses signed-distance fields evaluated ONLY inside each shape's
bounding box. Full-canvas SDF at 1080x1920 would be ~2M float ops per shape per
frame (far too slow for a 150-frame chart); the bbox restriction makes a typical
chart frame a couple of hundred thousand ops instead.

Text is NOT drawn here. ffmpeg's `drawtext` already has proper font shaping,
hinting and outlines, so text is composited by `overlays.py` as a filter pass over
these rasters. That split keeps us free of a font-rasterising dependency.
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import numpy as np

Color = tuple[int, int, int]


# --------------------------------------------------------------------------- #
# Canvas
# --------------------------------------------------------------------------- #
class Canvas:
    """Straight-alpha RGBA canvas. Premultiplication is avoided so a caller can
    read back partial coverage without surprises; `to_rgba()` emits the uint8
    buffer ffmpeg wants."""

    def __init__(self, width: int, height: int, bg: Color | None = None,
                 bg_alpha: float = 1.0):
        self.w, self.h = int(width), int(height)
        self.rgb = np.zeros((self.h, self.w, 3), dtype=np.float32)
        self.a = np.zeros((self.h, self.w), dtype=np.float32)
        if bg is not None:
            self.rgb[:] = np.array(bg, dtype=np.float32)
            self.a[:] = float(bg_alpha)

    # -- compositing -------------------------------------------------------- #
    def _blend(self, x0: int, y0: int, cov: np.ndarray, color: Color,
               alpha: float) -> None:
        """Source-over one coverage tile at (x0, y0)."""
        h, w = cov.shape
        if h <= 0 or w <= 0:
            return
        sa = np.clip(cov * alpha, 0.0, 1.0)
        if not sa.any():
            return
        dst_rgb = self.rgb[y0:y0 + h, x0:x0 + w]
        dst_a = self.a[y0:y0 + h, x0:x0 + w]
        src = np.array(color, dtype=np.float32)
        out_a = sa + dst_a * (1.0 - sa)
        safe = np.maximum(out_a, 1e-6)[..., None]
        self.rgb[y0:y0 + h, x0:x0 + w] = (
            src * sa[..., None] + dst_rgb * dst_a[..., None] * (1.0 - sa[..., None])
        ) / safe
        self.a[y0:y0 + h, x0:x0 + w] = out_a

    def _grid(self, x0: int, y0: int, x1: int, y1: int):
        """Clipped pixel-centre coordinate grid for a bbox, or None if off-canvas."""
        x0, y0 = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
        x1, y1 = min(self.w, int(np.ceil(x1))), min(self.h, int(np.ceil(y1)))
        if x1 <= x0 or y1 <= y0:
            return None
        ys = np.arange(y0, y1, dtype=np.float32) + 0.5
        xs = np.arange(x0, x1, dtype=np.float32) + 0.5
        return x0, y0, xs[None, :], ys[:, None]

    @staticmethod
    def _cov(sdf: np.ndarray) -> np.ndarray:
        """Distance field → antialiased coverage (1px transition band)."""
        return np.clip(0.5 - sdf, 0.0, 1.0)

    # -- primitives --------------------------------------------------------- #
    def rect(self, x: float, y: float, w: float, h: float, color: Color,
             alpha: float = 1.0, radius: float = 0.0) -> None:
        """Filled (optionally rounded) rectangle."""
        if w <= 0 or h <= 0:
            return
        r = float(min(radius, w / 2, h / 2))
        g = self._grid(x - 1, y - 1, x + w + 1, y + h + 1)
        if g is None:
            return
        x0, y0, xs, ys = g
        cx, cy = x + w / 2, y + h / 2
        dx = np.abs(xs - cx) - (w / 2 - r)
        dy = np.abs(ys - cy) - (h / 2 - r)
        dx = np.maximum(dx, 0.0) + np.zeros_like(dy)
        dy = np.maximum(dy, 0.0) + np.zeros_like(dx)
        outside = np.sqrt(dx * dx + dy * dy) - r
        # inside term keeps the field signed for non-rounded rects
        inside = np.maximum(np.abs(xs - cx) - w / 2, np.abs(ys - cy) - h / 2)
        sdf = np.where(outside > 0, outside, inside)
        self._blend(x0, y0, self._cov(sdf), color, alpha)

    def circle(self, cx: float, cy: float, r: float, color: Color,
               alpha: float = 1.0) -> None:
        if r <= 0:
            return
        g = self._grid(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1)
        if g is None:
            return
        x0, y0, xs, ys = g
        sdf = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) - r
        self._blend(x0, y0, self._cov(sdf), color, alpha)

    def ring(self, cx: float, cy: float, r: float, width: float, color: Color,
             alpha: float = 1.0, start: float = 0.0, sweep: float = 1.0) -> None:
        """Annulus arc. `start`/`sweep` are turns (0..1), 0 = 12 o'clock, CW —
        the donut/progress primitive."""
        outer = r + width / 2
        g = self._grid(cx - outer - 1, cy - outer - 1, cx + outer + 1, cy + outer + 1)
        if g is None:
            return
        x0, y0, xs, ys = g
        dx, dy = xs - cx, ys - cy
        band = np.abs(np.sqrt(dx * dx + dy * dy) - r) - width / 2
        cov = self._cov(band)
        if sweep < 1.0:
            # angle in turns clockwise from 12 o'clock
            ang = (np.arctan2(dx + np.zeros_like(dy), -(dy + np.zeros_like(dx)))
                   / (2 * np.pi)) % 1.0
            rel = (ang - start) % 1.0
            cov = cov * (rel <= max(sweep, 1e-6))
        self._blend(x0, y0, cov, color, alpha)

    def segment(self, x1: float, y1: float, x2: float, y2: float, width: float,
                color: Color, alpha: float = 1.0, round_caps: bool = True) -> None:
        """Thick line segment (capsule SDF)."""
        hw = width / 2
        g = self._grid(min(x1, x2) - hw - 1, min(y1, y2) - hw - 1,
                       max(x1, x2) + hw + 1, max(y1, y2) + hw + 1)
        if g is None:
            return
        x0, y0, xs, ys = g
        px = xs - x1 + np.zeros((ys.shape[0], 1), dtype=np.float32)
        py = ys - y1 + np.zeros((1, xs.shape[1]), dtype=np.float32)
        bx, by = x2 - x1, y2 - y1
        bb = bx * bx + by * by
        if bb < 1e-9:
            if round_caps:
                self.circle(x1, y1, hw, color, alpha)
            return
        t = np.clip((px * bx + py * by) / bb, 0.0, 1.0)
        sdf = np.sqrt((px - t * bx) ** 2 + (py - t * by) ** 2) - hw
        self._blend(x0, y0, self._cov(sdf), color, alpha)

    def polyline(self, pts: list[tuple[float, float]], width: float, color: Color,
                 alpha: float = 1.0) -> None:
        for i in range(len(pts) - 1):
            self.segment(*pts[i], *pts[i + 1], width, color, alpha)
        for p in pts[1:-1]:                    # round the joints
            self.circle(p[0], p[1], width / 2, color, alpha)

    def area_under(self, pts: list[tuple[float, float]], baseline_y: float,
                   color: Color, alpha: float = 0.22) -> None:
        """Soft fill between a polyline and a baseline — the 'financial chart'
        gradient body under a trend line."""
        if len(pts) < 2:
            return
        xs_all = [p[0] for p in pts]
        top = min(p[1] for p in pts)
        g = self._grid(min(xs_all), top, max(xs_all), baseline_y)
        if g is None:
            return
        x0, y0, xs, ys = g
        curve = np.interp(xs[0], np.array(xs_all, dtype=np.float32),
                          np.array([p[1] for p in pts], dtype=np.float32))
        cov = np.clip(ys - curve[None, :], 0.0, 1.0) * (ys <= baseline_y)
        # vertical falloff so the fill fades toward the baseline
        span = max(1.0, baseline_y - top)
        fade = np.clip(1.0 - (ys - top) / span, 0.15, 1.0)
        self._blend(x0, y0, cov * fade, color, alpha)

    def vgradient(self, x: float, y: float, w: float, h: float, top: Color,
                  bottom: Color, alpha_top: float = 1.0,
                  alpha_bottom: float = 1.0) -> None:
        g = self._grid(x, y, x + w, y + h)
        if g is None:
            return
        x0, y0, xs, ys = g
        t = np.clip((ys - y) / max(h, 1e-6), 0.0, 1.0)
        ones = np.ones((1, xs.shape[1]), dtype=np.float32)
        tt = t * ones
        cov = alpha_top + (alpha_bottom - alpha_top) * tt
        # blend per channel by walking the gradient as a stack of source colours
        src = (np.array(top, dtype=np.float32)[None, None, :] * (1 - tt)[..., None]
               + np.array(bottom, dtype=np.float32)[None, None, :] * tt[..., None])
        sa = np.clip(cov, 0.0, 1.0)
        h_, w_ = sa.shape
        dst_rgb = self.rgb[y0:y0 + h_, x0:x0 + w_]
        dst_a = self.a[y0:y0 + h_, x0:x0 + w_]
        out_a = sa + dst_a * (1.0 - sa)
        safe = np.maximum(out_a, 1e-6)[..., None]
        self.rgb[y0:y0 + h_, x0:x0 + w_] = (
            src * sa[..., None] + dst_rgb * dst_a[..., None] * (1.0 - sa[..., None])
        ) / safe
        self.a[y0:y0 + h_, x0:x0 + w_] = out_a

    # -- output ------------------------------------------------------------- #
    def to_rgba(self) -> np.ndarray:
        out = np.empty((self.h, self.w, 4), dtype=np.uint8)
        out[..., :3] = np.clip(self.rgb, 0, 255).astype(np.uint8)
        out[..., 3] = np.clip(self.a * 255.0, 0, 255).astype(np.uint8)
        return out

    def copy(self) -> "Canvas":
        c = Canvas(self.w, self.h)
        c.rgb = self.rgb.copy()
        c.a = self.a.copy()
        return c


# --------------------------------------------------------------------------- #
# Encoders
# --------------------------------------------------------------------------- #
def write_png(canvas: Canvas, out: Path) -> Path:
    """Encode one RGBA canvas to PNG through ffmpeg's rawvideo demuxer."""
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{canvas.w}x{canvas.h}", "-i", "pipe:0",
         "-frames:v", "1", "-y", str(out)],
        input=canvas.to_rgba().tobytes(), capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"png encode failed: {proc.stderr.decode()[:300]}")
    return out


# Drawing a frame is pure numpy — a synchronous CPU burn with no await in it.
# Run unbounded and concurrent chart beats simply oversubscribe the cores and
# finish no sooner; 2 keeps both a generator and an encoder busy without pushing
# a 4 GB box into swap, which is the failure mode that actually hurts.
_CPU_RENDER = asyncio.Semaphore(2)


async def write_video(frames, width: int, height: int, fps: int, out: Path,
                      alpha: bool = False, vf: str | None = None) -> Path:
    """Stream an iterable of RGBA canvases/arrays straight into ffmpeg.

    `alpha=True` produces a QuickTime RLE MOV with a real alpha channel (used for
    graphics that composite over footage); otherwise a plain yuv420p H.264 MP4 for
    full-frame chart scenes.

    `vf` applies a filter chain in the SAME pass — the chart engine uses it to
    composite drawtext labels, which avoids a second full re-encode per chart beat
    across thousands of shorts.

    Frames are pulled on a worker thread. The generator is numpy all the way
    down, so iterating it inline stalled the whole event loop for the length of
    the chart — every other pipeline stage froze while a chart drew.
    """
    async with _CPU_RENDER:
        return await _write_video(frames, width, height, fps, out, alpha, vf)


async def _write_video(frames, width: int, height: int, fps: int, out: Path,
                       alpha: bool, vf: str | None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    if alpha:
        codec = ["-c:v", "qtrle", "-pix_fmt", "argb"]
    else:
        codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                 "-preset", "veryfast"]
    filt = ["-vf", vf] if vf else []
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "pipe:0", *filt, *codec, "-r", str(fps),
        "-y", str(out),
        stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    def _next_buffer(iterator):
        """One frame, drawn and serialised on the worker thread."""
        frame = next(iterator, None)
        if frame is None:
            return None
        return (frame.to_rgba().tobytes() if isinstance(frame, Canvas)
                else frame.tobytes())

    try:
        iterator = iter(frames)
        while True:
            buf = await asyncio.to_thread(_next_buffer, iterator)
            if buf is None:
                break
            proc.stdin.write(buf)
            await proc.stdin.drain()
        proc.stdin.close()
    except (BrokenPipeError, ConnectionResetError):
        pass
    _, err = await proc.communicate()
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"video encode failed: {err.decode()[:400]}")
    return out


# --------------------------------------------------------------------------- #
# Easing — shared by every animation so motion feels like one hand made it
# --------------------------------------------------------------------------- #
def ease_out_cubic(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_out_expo(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1.0 if t >= 1.0 else 1.0 - 2 ** (-10 * t)


def ease_in_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
