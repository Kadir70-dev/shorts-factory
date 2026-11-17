"""Data-storytelling components: counters, percentage comparison, before/after, split-screen, kinetic headlines."""
from __future__ import annotations

from typing import Callable, Optional

from PIL import Image, ImageDraw

from .core import (rrect, ChartTheme, DataError, W, clamp, eback, eio, eo3, glass_panel, lerp, new_layer, put, text_tile, vgrad)
from .line import LineChart


# --------------------------------------------------------------------------- #
# furniture
# --------------------------------------------------------------------------- #
_SHADE: dict[tuple, Image.Image] = {}


def shade_layer(w: int = 1080, h: int = 1920) -> Image.Image:
    """Top + bottom legibility gradients for type over footage."""
    k = (w, h)
    if k not in _SHADE:
        s = new_layer(w, h)
        s.alpha_composite(vgrad(w, int(h * 0.40), 0.72, 0.0), (0, 0))
        s.alpha_composite(vgrad(w, int(h * 0.43), 0.0, 0.70), (0, h - int(h * 0.43)))
        _SHADE[k] = s
    return _SHADE[k].copy()


def source_line(L: Image.Image, th: ChartTheme, text: str, t: float, t0: float = 0.3, y: int = 1395) -> None:
    put(L, text_tile(text.upper(), th.body, 34, th.ink, None, 0, 5, spacing=1.2), W / 2, y, alpha=eo3((t - t0) / 0.4) * 0.95,
        anchor="cm", tag="source", size=34)


# --------------------------------------------------------------------------- #
# kinetic headline
# --------------------------------------------------------------------------- #
def headline(L: Image.Image, th: ChartTheme, lines: list[tuple[str, tuple, float]], t: float, *, size: int = 118, x: int = 64,
             y0: int = 250, align: str = "left", step: float = 0.09) -> None:
    """lines = [(text, colour, t_in)]; words pop in `step` seconds apart."""
    from .core import font
    f = font(th.display, size)
    y = y0
    for text, col, t_in in lines:
        words = text.split(" ")
        widths = [f.getlength(w) for w in words]
        space = f.getlength(" ")
        total = sum(widths) + space * (len(words) - 1)
        cx = x if align == "left" else (W - total) / 2
        if total > W - 2 * 40:
            raise DataError(f"headline line too wide for the frame: {text!r} ({total:.0f}px at size {size})")
        for k, w in enumerate(words):
            tt = (t - t_in - k * step) / 0.28
            if tt > 0:
                tile = text_tile(w, th.display, size, col, th.primary, 18, 8)
                put(L, tile, cx + widths[k] / 2, y + size * 0.62, alpha=eo3(tt * 1.6), scale=lerp(1.35, 1.0, eback(tt)), anchor="cm",
                    tag="headline", size=size)
            cx += widths[k] + space
        y += size * 1.02 + 6


# --------------------------------------------------------------------------- #
# counters / stats
# --------------------------------------------------------------------------- #
def counter_value(start: float, end: float, t: float, t_in: float = 0.12, dur: float = 0.9) -> float:
    return lerp(start, end, eio((t - t_in) / dur))


def stat(L: Image.Image, th: ChartTheme, t: float, target: float, *, prefix: str = "", suffix: str = "", label: str = "", sub: str = "",
         direction: Optional[str] = "up", y: int = 400, start: float = 0.0, decimals: int = 0, t_in: float = 0.12, dur: float = 0.85,
         size: int = 270) -> None:
    """Big counting number with a direction triangle (red = up/bad for consumers, green = down)."""
    val = counter_value(start, target, t, t_in, dur)
    txt = f"{prefix}{val:.{decimals}f}{suffix}"
    tile = text_tile(txt, th.display, size, th.gold, th.gold, 26, 8)
    fit = min(1.0, 0.78 * W / max(1, tile.width - 2 * tile.info["ink_pad"]))      # long strings ("+30.6%") shrink to fit the frame
    pop = lerp(1.22, 1.0, eback((t - t_in) / 0.35)) * fit
    cx = W / 2 + 28
    put(L, tile, cx, y + size * 0.55, alpha=eo3((t - t_in) / 0.2), scale=pop, anchor="cm", tag="stat", size=int(size * fit))
    if direction:
        c = th.negative if direction == "up" else th.positive
        tri = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        pts = [(48, 8), (92, 88), (4, 88)] if direction == "up" else [(4, 8), (92, 8), (48, 88)]
        ImageDraw.Draw(tri).polygon(pts, fill=c + (255,))
        tw = (tile.width - 2 * tile.info["ink_pad"]) * pop
        put(L, tri, cx - tw / 2 - 52, y + size * 0.55, alpha=eo3((t - t_in - 0.1) / 0.25), anchor="cm")
    put(L, text_tile(label.upper(), th.body, 80, th.ink, None, 0, 7, spacing=5), W / 2, y + size * 1.38, alpha=eo3((t - t_in - 0.25) / 0.3),
        anchor="cm", tag="statlabel", size=80)
    if sub:
        put(L, text_tile(sub.upper(), th.body, 44, th.ink, None, 0, 6, spacing=3), W / 2, y + size * 1.66, alpha=eo3((t - t_in - 0.4) / 0.3),
            anchor="cm", tag="statsub", size=44)


def before_after(L: Image.Image, th: ChartTheme, t: float, *, before: float, after: float, before_label: str, after_label: str,
                 fmt: Callable[[float], str] = lambda v: f"{v:.1f}%", y: int = 330, t_in: float = 0.15,
                 higher_is_worse: bool = True, t_second: float = 1.2) -> None:
    """Two numbers and the move between them; the second lands on a beat."""
    col_after, arrow = th.direction((after - before) if higher_is_worse else (before - after), 0.0)
    a1 = eo3((t - t_in) / 0.3)
    put(L, text_tile(fmt(before), th.display, 168, th.ink, None, 0, 8), 262, y + 110, anchor="cm", alpha=a1, tag="ba_before", size=168)
    put(L, text_tile(before_label.upper(), th.body, 52, th.dim, None, 0, 5, spacing=3), 262, y + 262, anchor="cm", alpha=a1, tag="ba_lbl", size=52)
    d = ImageDraw.Draw(L)
    a_arrow = eo3((t - t_second + 0.25) / 0.3)
    if a_arrow > 0:
        xs, xe = 470, lerp(470, 590, eio((t - t_second + 0.25) / 0.4))
        d.line([(xs, y + 110), (xe, y + 110)], fill=th.gold + (int(255 * a_arrow),), width=14)
        d.polygon([(xe + 34, y + 110), (xe - 8, y + 80), (xe - 8, y + 140)], fill=th.gold + (int(255 * a_arrow),))
    a2 = eo3((t - t_second) / 0.3)
    val = lerp(before, after, eio((t - t_second) / 0.7))
    put(L, text_tile(fmt(val), th.display, 168, col_after, col_after, 24, 8), 818, y + 110, anchor="cm", alpha=a2,
        scale=lerp(1.2, 1.0, eback((t - t_second) / 0.35)), tag="ba_after", size=168)
    put(L, text_tile(after_label.upper(), th.body, 52, th.ink, None, 0, 5, spacing=3), 818, y + 262, anchor="cm", alpha=a2, tag="ba_lbl", size=52)


def percent_compare(L: Image.Image, th: ChartTheme, t: float, items: list[tuple[str, float, tuple]], *, rect=(90, 700, 990, 1150),
                    fmt: Callable[[float], str] = lambda v: f"+{v:.0f}%", t_in: float = 0.2, stagger: float = 0.18) -> None:
    """Horizontal comparison bars that grow in sequence (same scale, zero-based)."""
    if not items:
        raise DataError("percent_compare needs items")
    rx0, ry0, rx1, ry1 = rect
    vmax = max(v for _, v, _ in items) * 1.12
    rh = (ry1 - ry0) / len(items)
    d = ImageDraw.Draw(L)
    for i, (name, v, col) in enumerate(items):
        p = eio((t - t_in - i * stagger) / 0.7)
        y = ry0 + i * rh
        put(L, text_tile(name.upper(), th.body, 46, th.ink, None, 0, 5, spacing=2), rx0, y - 6, alpha=clamp(p * 3), tag="pc_name", size=46)
        w = (rx1 - rx0 - 190) * v / vmax * p
        rrect(d, [rx0, y + rh * 0.45, rx0 + max(30, w), y + rh * 0.45 + rh * 0.34], max(1, int(min(14, max(30, w) / 2 - 1))), fill=col + (255,))
        put(L, text_tile(fmt(v * p), th.display, 50, th.ink, None, 0, 5), rx0 + max(10, w) + 16, y + rh * 0.78, anchor="lm", alpha=clamp(p * 3),
            tag="pc_val", size=50)


def split_screen(L: Image.Image, th: ChartTheme, top: LineChart, bottom: LineChart, t: float, *, top_label: str, bottom_label: str,
                 intro: bool = True) -> None:
    """Two synchronised charts stacked: e.g. the RATE (speed) above the LEVEL (distance)."""
    top.draw(L, t, intro)
    bottom.draw(L, t, intro)
    a = eo3(t / 0.35) if intro else 1.0
    for lab, chart in ((top_label, top), (bottom_label, bottom)):
        if chart.panel:
            put(L, text_tile(lab.upper(), th.display, 54, th.gold, th.gold, 14, 6), chart.panel[2] - 36, chart.panel[1] + 24, anchor="rt",
                alpha=a, tag="split_label", size=54)
