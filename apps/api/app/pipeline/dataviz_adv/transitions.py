"""Chart transitions: camera moves, line->bar morph, focus pulses.  Footage<->chart blur ramps live in compose.py."""
from __future__ import annotations

import math
from typing import Callable, Optional

from PIL import Image, ImageDraw

from .core import rrect, ChartTheme, DataError, source_block, W, H, clamp, eio5, eo3, glass_panel, lerp, new_layer, put, text_tile


class CameraTrack:
    """(t, zoom, cx, cy) keyframes; cx/cy are fractions of the frame.  Smooth, never faster than the keyframes imply."""

    def __init__(self, keys: list[tuple[float, float, float, float]]):
        self.keys = sorted(keys)

    def at(self, t: float) -> tuple[float, float, float]:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1:]
        for a, b in zip(ks, ks[1:]):
            if t <= b[0]:
                u = eio5((t - a[0]) / max(1e-9, b[0] - a[0]))
                return (math.exp(lerp(math.log(a[1]), math.log(b[1]), u)), lerp(a[2], b[2], u), lerp(a[3], b[3], u))
        return ks[-1][1:]


def apply_camera(layer: Image.Image, zoom: float, cx: float = 0.5, cy: float = 0.5) -> Image.Image:
    """Zoom the whole graphics layer about (cx, cy); the crop never leaves the frame."""
    if abs(zoom - 1.0) < 1e-4:
        return layer
    w, h = layer.size
    cw, ch = w / zoom, h / zoom
    x0 = clamp(cx * w - cw / 2, 0, w - cw)
    y0 = clamp(cy * h - ch / 2, 0, h - ch)
    return layer.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((w, h), Image.BICUBIC)


class MorphLineBars:
    """Same data, two encodings: a line over categories that grows into bars (p: 0 = line, 1 = bars)."""

    def __init__(self, th: ChartTheme, labels: list[str], values: list[float], *, rect=(120, 620, 960, 1120), title: str = "",
                 fmt: Callable[[float], str] = lambda v: f"{v:.0f}", source: str = "", t0: float = 1.2, dur: float = 1.0,
                 panel=(48, 225, 1032, 1300)):
        if len(labels) != len(values) or len(values) < 2:
            raise DataError("MorphLineBars needs matching labels/values (>= 2)")
        if not source.strip():
            raise DataError("MorphLineBars needs a source")
        self.th, self.labels, self.values, self.rect, self.title, self.fmt = th, labels, values, rect, title, fmt
        self.source, self.t0, self.dur, self.panel = source, t0, dur, panel

    def progress(self, t: float) -> float:
        return eio5((t - self.t0) / self.dur)

    def draw(self, L: Image.Image, t: float) -> None:
        th = self.th
        a_in = eo3(t / 0.35)
        glass_panel(L, self.panel, th, a_in)
        put(L, text_tile(self.title.upper(), th.body, 46, th.dim, None, 0, 4, spacing=2.4), self.panel[0] + 36, self.panel[1] + 19,
            alpha=a_in, tag="title", size=46)
        rx0, ry0, rx1, ry1 = self.rect
        n = len(self.values)
        vmax = max(self.values) * 1.15
        p = self.progress(t)
        d = ImageDraw.Draw(L)
        draw_on = eio5(t / 1.0)                                   # the line draws on first
        xs = [rx0 + (rx1 - rx0) * (i + 0.5) / n for i in range(n)]
        ys = [ry1 - v / vmax * (ry1 - ry0) for v in self.values]
        bw = (rx1 - rx0) / n * 0.62
        cols = list(th.categories)
        for i in range(n):
            if p > 0:
                top = lerp(ry1, ys[i], p)
                rrect(d, [xs[i] - bw / 2, top, xs[i] + bw / 2, ry1], 16, fill=cols[i % len(cols)] + (int(235 * a_in),))
        la = (1 - p)
        if la > 0.01 and draw_on > 0:
            m = min(n - 1, draw_on * (n - 1))
            pts = [(xs[i], ys[i]) for i in range(int(m) + 1)]
            if int(m) < n - 1:
                f = m - int(m)
                pts.append((lerp(xs[int(m)], xs[int(m) + 1], f), lerp(ys[int(m)], ys[int(m) + 1], f)))
            if len(pts) >= 2:
                d.line(pts, fill=th.secondary + (int(255 * la),), width=12, joint="curve")
            for (x, y) in pts[:n]:
                d.ellipse([x - 12, y - 12, x + 12, y + 12], fill=th.ink + (int(255 * la),))
        d.line([(rx0, ry1), (rx1, ry1)], fill=(255, 255, 255, int(90 * a_in)), width=3)
        for i in range(n):
            put(L, text_tile(self.labels[i].upper(), th.body, 36, th.dim, None, 0, 3, spacing=1), xs[i], ry1 + 18, anchor="ct", alpha=a_in,
                tag="cat", size=36)
            if p > 0.55:
                put(L, text_tile(self.fmt(self.values[i]), th.display, 44, th.ink, None, 0, 5), xs[i], lerp(ry1, ys[i], p) - 14, anchor="mb",
                    alpha=clamp((p - 0.55) / 0.3), tag="val", size=44)
        source_block(L, th, self.source, self.panel[0] + 34, self.panel[3] - 58, self.panel[2] - self.panel[0] - 68, a_in)


def focus_pulse(L: Image.Image, th: ChartTheme, x: float, y: float, t: float, t0: float, dur: float = 0.9) -> None:
    """Expanding ring that draws the eye to a data point (controlled, one-shot)."""
    u = (t - t0) / dur
    if not (0 <= u <= 1):
        return
    r = 18 + 70 * eo3(u)
    ImageDraw.Draw(L).ellipse([x - r, y - r, x + r, y + r], outline=th.gold + (int(220 * (1 - u)),), width=5)
