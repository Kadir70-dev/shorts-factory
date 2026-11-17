"""Cinematic line chart: animated draw-on, a camera (data-space window) that follows the story, dynamic axes
that re-tick as the window moves, a value pill that rides the head, callouts and a direction-coloured readout."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .core import (rrect, ChartTheme, Series, source_block, Timeline, View, ViewTrack, W, clamp, eo3, glass_panel, lerp, mix, month_label,
                   nice_ticks, put, text_tile)


@dataclass
class Callout:
    idx: int
    text: str
    sub: str = ""
    color: Optional[tuple] = None
    t_show: float = 0.0


def x_tick_labels(series: Series, v0: float, v1: float, max_labels: int = 5) -> list[tuple[float, str]]:
    lo, hi = max(0, int(math.ceil(v0))), min(len(series.periods) - 1, int(math.floor(v1)))
    if hi < lo:
        return []
    span = v1 - v0
    out: list[tuple[float, str]] = []
    for i in range(lo, hi + 1):
        mo = int(series.periods[i][5:7])
        yr = series.periods[i][:4]
        if span > 40:
            if mo == 1:
                out.append((i, yr))
        elif span > 14:
            if mo in (1, 4, 7, 10):
                out.append((i, month_label(series.periods[i])))
        else:
            out.append((i, month_label(series.periods[i])[:3] if span <= 10 else month_label(series.periods[i])))
    while len(out) > max_labels:                       # thin evenly, never exceed the label budget
        out = out[::2]
    return out


class LineChart:
    def __init__(self, th: ChartTheme, series: Series, timeline: Timeline, *, rect=(150, 700, 985, 1130),
                 view: Optional[ViewTrack] = None, title: str = "", y_fmt: Callable[[float], str] = lambda v: f"{v:.0f}",
                 pill_fmt: Optional[Callable[[float], str]] = None, big_fmt: Optional[Callable[[float], tuple[str, str]]] = None,
                 callouts: Optional[list[Callout]] = None, cols: Optional[tuple] = None, source: Optional[str] = None,
                 panel: Optional[tuple[int, int, int, int]] = (48, 225, 1032, 1300), y_floor: Optional[float] = None,
                 y_pad: float = 0.12, tick_size: int = 34, show_big: bool = True, line_w: int = 12):
        self.th, self.s = th, series.validate()
        self.tl, self.rect, self.title, self.y_fmt = timeline, rect, title, y_fmt
        self.pill_fmt = pill_fmt or y_fmt
        self.big_fmt, self.callouts = big_fmt, callouts or []
        self.cols = cols or (th.secondary, th.primary)
        self.source, self.panel, self.tick_size, self.show_big, self.line_w = (series.source if source is None else source), panel, tick_size, show_big, line_w
        vals = [v for v in series.values if v is not None]
        lo, hi = min(vals), max(vals)
        if y_floor is not None:
            lo = min(lo, y_floor)
        pad = (hi - lo) * y_pad or 1.0
        self.full = View(0, len(series.periods) - 1, (y_floor if y_floor is not None else lo - pad), hi + pad)
        self.views = view or ViewTrack([(0.0, self.full)])

    # -- geometry ---------------------------------------------------------- #
    def map(self, v: View):
        rx0, ry0, rx1, ry1 = self.rect
        return (lambda x: rx0 + (x - v.x0) / (v.x1 - v.x0) * (rx1 - rx0),
                lambda y: ry1 - (y - v.y0) / (v.y1 - v.y0) * (ry1 - ry0))

    def head(self, t: float) -> float:
        return clamp(self.tl.at(t), 0, len(self.s.periods) - 1)

    # -- one frame ---------------------------------------------------------- #
    def draw(self, L: Image.Image, t: float, intro: bool = True) -> None:
        th, s = self.th, self.s
        rx0, ry0, rx1, ry1 = self.rect
        a_panel = eo3(t / 0.35) if intro else 1.0
        if self.panel:
            glass_panel(L, self.panel, th, a_panel)
            if self.title:
                put(L, text_tile(self.title.upper(), th.body, 46, th.dim, None, 0, 4, spacing=2.4), self.panel[0] + 36,
                    self.panel[1] + 19, alpha=a_panel, tag="title", size=46)
        v = self.views.at(t)
        X, Y = self.map(v)
        h = self.head(t)
        d = ImageDraw.Draw(L)

        for yv in nice_ticks(v.y0, v.y1, 4):                       # dynamic y grid + labels
            y = Y(yv)
            if ry0 - 4 <= y <= ry1 + 4:
                for x in range(int(rx0), int(rx1), 24):
                    d.line([(x, y), (x + 11, y)], fill=(255, 255, 255, int(44 * a_panel)), width=2)
                put(L, text_tile(self.y_fmt(yv), th.body, self.tick_size, th.dim, None, 0, 0), rx0 - 14, y, anchor="rm",
                    alpha=a_panel, tag="ytick", size=self.tick_size)
        for xi, lab in x_tick_labels(s, v.x0, v.x1):                 # dynamic x labels
            x = X(xi)
            if rx0 - 2 <= x <= rx1 + 2:
                tl = text_tile(lab.upper(), th.body, self.tick_size, th.dim, None, 0, 1, spacing=1)
                half = (tl.width - 2 * tl.info["ink_pad"]) / 2
                put(L, tl, min(max(x, rx0 + half - 6), rx1 + 40 - half), ry1 + 16, anchor="ct", alpha=a_panel, tag="xtick",
                    size=self.tick_size)

        pts = [(i, s.values[i]) for i in s.valid_idx if i <= h]
        if pts and any(i > h for i in s.valid_idx) and pts[-1][0] < h:
            pts.append((h, s.at(h)))
        if len(pts) >= 2:
            self._draw_line(L, pts, X, Y)
            self._head(L, X(pts[-1][0]), Y(pts[-1][1]), pts[-1][1], t)
        for c in self.callouts:
            self._callout(L, c, X, Y, t)
        if self.show_big and self.big_fmt and len(pts) >= 2:
            self._big(L, pts[-1][1], h, t)
        if self.source and self.panel:
            source_block(L, th, self.source, self.panel[0] + 34, self.panel[3] - 58, self.panel[2] - self.panel[0] - 68, a_panel)

    # -- pieces ------------------------------------------------------------- #
    def _draw_line(self, L, pts, X, Y) -> None:
        rx0, ry0, rx1, ry1 = self.rect
        m = 40
        pw, ph = int(rx1 - rx0 + 2 * m), int(ry1 - ry0 + 2 * m)
        plot = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        glow = Image.new("RGBA", (pw // 4 + 1, ph // 4 + 1), (0, 0, 0, 0))
        pd, gd = ImageDraw.Draw(plot), ImageDraw.Draw(glow)
        sx = lambda i: X(i) - rx0 + m
        sy = lambda y: Y(y) - ry0 + m
        poly = [(sx(i), sy(val)) for i, val in pts]
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).polygon(poly + [(poly[-1][0], m + (ry1 - ry0)), (poly[0][0], m + (ry1 - ry0))], fill=255)
        c0, c1 = self.cols
        grad = np.zeros((ph, pw, 4), np.uint8)
        a = np.linspace(0.30, 0.0, ph, dtype=np.float32)[:, None] * np.ones((1, pw), np.float32)
        xs = np.clip((np.arange(pw) - m) / max(1, rx1 - rx0), 0, 1)
        for ch in range(3):
            grad[..., ch] = (c0[ch] + (c1[ch] - c0[ch]) * xs)[None, :]
        grad[..., 3] = (a * 255).astype(np.uint8)
        area = Image.fromarray(grad, "RGBA")
        area.putalpha(ImageChops.multiply(area.getchannel("A"), mask))
        plot.alpha_composite(area)
        for (i0, v0), (i1, v1) in zip(pts, pts[1:]):
            x0, y0, x1, y1 = sx(i0), sy(v0), sx(i1), sy(v1)
            if max(x0, x1) < -20 or min(x0, x1) > pw + 20:
                continue
            col = mix(c0, c1, clamp(((x0 + x1) / 2 - m) / max(1, rx1 - rx0)))
            gap = (i1 - i0) > 1.0001 and self.s.values[int(i0) + 1] is None
            if gap:
                n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 26))
                for k in range(0, n, 2):
                    pd.line([(lerp(x0, x1, k / n), lerp(y0, y1, k / n)),
                             (lerp(x0, x1, min(1, (k + 1) / n)), lerp(y0, y1, min(1, (k + 1) / n)))],
                            fill=col + (210,), width=max(4, self.line_w - 4))
            else:
                gd.line([(x0 / 4, y0 / 4), (x1 / 4, y1 / 4)], fill=col + (255,), width=6)
                pd.line([(x0, y0), (x1, y1)], fill=col + (255,), width=self.line_w)
                pd.ellipse([x1 - self.line_w / 2, y1 - self.line_w / 2, x1 + self.line_w / 2, y1 + self.line_w / 2], fill=col + (255,))
        glow = glow.filter(ImageFilter.GaussianBlur(5)).resize((pw, ph), Image.BILINEAR)
        under = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        under.alpha_composite(glow)
        under.alpha_composite(plot)
        clip = Image.new("L", (pw, ph), 0)                     # nothing may spill outside the plot window when zoomed
        ImageDraw.Draw(clip).rectangle([m - 12, m - 30, pw - m + 12, ph - m + 4], fill=255)
        under.putalpha(ImageChops.multiply(under.getchannel("A"), clip))
        L.alpha_composite(under, (int(rx0 - m), int(ry0 - m)))

    def _head(self, L, hx: float, hy: float, val: float, t: float) -> None:
        th = self.th
        rx0, ry0, rx1, ry1 = self.rect
        if not (rx0 - 10 <= hx <= rx1 + 14 and ry0 - 30 <= hy <= ry1 + 10):
            return
        d = ImageDraw.Draw(L)
        r = 19 * (1 + 0.22 * math.sin(t * 7.5))
        d.ellipse([hx - r * 1.9, hy - r * 1.9, hx + r * 1.9, hy + r * 1.9], fill=th.secondary + (52,))
        d.ellipse([hx - 15, hy - 15, hx + 15, hy + 15], fill=(255, 255, 255, 255))
        d.ellipse([hx - 8, hy - 8, hx + 8, hy + 8], fill=mix(self.cols[0], self.cols[1], clamp((hx - rx0) / max(1, rx1 - rx0))) + (255,))
        pill = text_tile(self.pill_fmt(val), th.display, 42, th.bg, None, 0, 0)
        pad = pill.info["ink_pad"]
        pw, ph = pill.width - 2 * pad, pill.height - 2 * pad
        lo_x = (self.panel[0] + 24) if self.panel else 20
        hi_x = ((self.panel[2] if self.panel else W) - 24) - pw - 36
        px = min(max(hx - pw / 2 - 18, lo_x), hi_x)
        py = max(hy - ph - 54, ry0 - 70)
        rrect(d, [px, py, px + pw + 36, py + ph + 16], 18, fill=th.ink + (240,))
        put(L, pill, px + 18 - pad, py + 8 - pad, tag="pill", size=42)

    def _callout(self, L, c: Callout, X, Y, t: float) -> None:
        th, s = self.th, self.s
        a = eo3((t - c.t_show) / 0.35)
        if a <= 0 or s.values[c.idx] is None:
            return
        rx0, ry0, rx1, ry1 = self.rect
        x, y = X(c.idx), Y(s.values[c.idx])
        if not (rx0 - 6 <= x <= rx1 + 6 and ry0 - 20 <= y <= ry1 + 6):
            return
        col = c.color or th.gold
        d = ImageDraw.Draw(L)
        for yy in range(int(ry0 - 6), int(y - 16), 18):
            d.line([(x, yy), (x, yy + 9)], fill=col + (int(210 * a),), width=3)
        lab = text_tile(c.text, th.display, 40, col, None, 0, 4)
        pad = lab.info["ink_pad"]
        lw = lab.width - 2 * pad
        tx = min(max(x - lw / 2, rx0 - 20), rx1 + 10 - lw)
        put(L, lab, tx - pad, ry0 - 92 - pad - 8 * (1 - a), alpha=a, tag="callout", size=40)
        if c.sub:
            put(L, text_tile(c.sub.upper(), th.body, 34, th.dim, None, 0, 3, spacing=1.2), tx, ry0 - 40, alpha=a,
                tag="callout_sub", size=34)
        d.ellipse([x - 14, y - 14, x + 14, y + 14], outline=col + (int(255 * a),), width=5)

    def _big(self, L, val: float, h: float, t: float) -> None:
        th, s = self.th, self.s
        prev = s.at(max(0, h - 3))
        col, arrow = th.direction(val - prev, 0.015 * (self.full.y1 - self.full.y0))
        txt, lab = self.big_fmt(val)
        x0 = (self.panel[0] if self.panel else 60) + 40
        y0 = (self.panel[1] if self.panel else 230) + 80
        put(L, text_tile(txt, th.display, 176, col, col, 22, 8), x0 - 10, y0, alpha=eo3((t - 0.1) / 0.3), tag="big", size=176)
        put(L, text_tile(lab.upper(), th.body, 46, th.ink, None, 0, 4, spacing=2.5), x0, y0 + 205, alpha=eo3((t - 0.25) / 0.3),
            tag="biglabel", size=46)
        if arrow:
            tri = Image.new("RGBA", (84, 84), (0, 0, 0, 0))
            ImageDraw.Draw(tri).polygon([(42, 6), (80, 76), (4, 76)] if arrow == "up" else [(4, 8), (80, 8), (42, 78)], fill=col + (255,))
            put(L, tri, (self.panel[2] if self.panel else W - 60) - 50, y0 + 75, alpha=eo3((t - 0.3) / 0.3), anchor="rm")
