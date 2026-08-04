"""
Branded animated data visualisation — the replacement for "number + random clip".

The audit's sharpest point: every important figure was being paired with generic
stock footage, and the one chart path that existed (Manim) shipped HARD-CODED
placeholder values — `[2.1, 2.4, 2.9, 3.1, 3.4]` no matter what the video was
about. A confident-looking chart of numbers nobody asserted is worse than no
chart at all, so that path is gone.

What replaces it: six chart forms rendered locally from numbers the Director
actually authored (`Scene.data`), in the channel's own palette and type system.
No Manim, no LaTeX, no network, no GPU — numpy geometry piped into ffmpeg, with
type composited by drawtext in the same pass.

Honesty rules baked in:
  * A chart is only produced when real values exist. `DataViz.valid()` gates it
    and `from_scene()` refuses to invent numbers — a beat with no figure gets no
    chart, never a decorative one.
  * The source attribution renders WITH the chart, not as a separate overlay that
    can drift away from it.
  * Axes start at a sensible baseline and the y-range is derived from the data, so
    the animation can't exaggerate a change the numbers don't support.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..brand import text as tx
from ..brand.raster import (Canvas, ease_in_out, ease_out_cubic, ease_out_expo,
                            write_video)
from ..brand.theme import BrandTheme
from ..schemas.scene import DataPoint, DataViz, Scene
from .util import visual_cache_path, visual_cache_store

# Bump when the drawing code changes shape: it namespaces every cache entry, so
# old frames can never be served for new geometry.
_CACHE_VERSION = 1

# Chart forms the engine can render, in the order the auto-picker prefers them.
KINDS = ["counter", "bar_compare", "line_trend", "delta", "donut", "meter"]


# --------------------------------------------------------------------------- #
# Number formatting
# --------------------------------------------------------------------------- #
def format_value(v: float, viz: DataViz) -> str:
    """Render a value the way a finance graphic would: abbreviated magnitudes,
    thousands separators, and the caller's own prefix/suffix preserved."""
    n = abs(v)
    if viz.abbreviate and n >= 1000:
        for scale, tag in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if n >= scale:
                # At least one decimal on the mantissa: `decimals` describes the
                # UNABBREVIATED figure, so honouring decimals=0 here would render
                # $274,600 as "$275K" and throw away the precision the chart is
                # supposed to be communicating. Trailing zeros are stripped, so a
                # round value still reads "$3M".
                places = max(1, viz.decimals)
                body = f"{v / scale:.{places}f}".rstrip("0").rstrip(".")
                return f"{viz.prefix}{body}{tag}{viz.suffix}"
    if viz.decimals == 0:
        body = f"{v:,.0f}"
    else:
        body = f"{v:,.{viz.decimals}f}"
    return f"{viz.prefix}{body}{viz.suffix}"


# The `\b` after the magnitude is load-bearing: without it the single-letter
# alternative matches the "b" of "bps", turning "25 bps" into 25 billion.
_NUM_RE = re.compile(
    r"(?P<prefix>[$€£]?)\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<mag>trillion|billion|million|thousand|[TBMK])\b)?"
    r"\s?(?P<suffix>%|percent|bps|basis points)?",
    re.IGNORECASE,
)
_MAG = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3,
        "t": 1e12, "b": 1e9, "m": 1e6, "k": 1e3}


def parse_number(text: str) -> tuple[float, str, str] | None:
    """Best-effort (value, prefix, suffix) from a human string like "$3.8 billion"
    or "44.8%". Used only to promote a Director-authored `stat` overlay into a
    chart — never to conjure a figure that wasn't stated."""
    m = _NUM_RE.search(text or "")
    if not m:
        return None
    try:
        val = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    mag = (m.group("mag") or "").lower()
    if mag:
        val *= _MAG.get(mag, 1.0)
    suffix = (m.group("suffix") or "")
    if suffix.lower() in ("percent", "%"):
        suffix = "%"
    elif suffix.lower() in ("bps", "basis points"):
        suffix = " bps"
    return val, m.group("prefix") or "", suffix


# --------------------------------------------------------------------------- #
# Deriving a chart from a scene the Director didn't explicitly chart
# --------------------------------------------------------------------------- #
def from_scene(scene: Scene) -> DataViz | None:
    """Promote a beat's `stat` overlay into a single-value chart.

    This is the safety net behind "every important number gets a custom
    visualisation": when the Director states a figure but doesn't author a series,
    we still render the number as a branded animated counter rather than dropping
    a stock clip behind it. It parses ONLY what the overlay already says.
    """
    if scene.data and scene.data.valid():
        return scene.data
    stat = next((o for o in scene.overlays if o.type == "stat" and o.sub), None)
    if not stat:
        return None
    parsed = parse_number(stat.sub)
    if not parsed:
        return None
    value, prefix, suffix = parsed
    source = next((o.text for o in scene.overlays if o.type == "source"), "")
    decimals = 0 if float(value).is_integer() else 1
    return DataViz(
        kind="meter" if suffix == "%" and 0 <= value <= 100 else "counter",
        title=stat.text.strip(),
        points=[DataPoint(label=stat.text.strip()[:24], value=value,
                          emphasis="primary")],
        prefix=prefix, suffix=suffix, decimals=decimals,
        abbreviate=abs(value) >= 1000, source=source,
    )


def auto_kind(viz: DataViz) -> str:
    """Pick a form when the Director named data but not a chart type."""
    n = len(viz.points)
    if n <= 1:
        return "meter" if viz.suffix == "%" and 0 <= viz.points[0].value <= 100 \
            else "counter"
    if n == 2:
        return "delta"
    labels = [p.label for p in viz.points]
    # four-digit labels that ascend read as a time series
    if n >= 4 and all(re.fullmatch(r"(19|20)\d{2}", str(l)) for l in labels):
        return "line_trend"
    return "bar_compare"


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Layout:
    w: int
    h: int
    pad: int
    title_y: int
    plot_top: int
    plot_bottom: int
    footer_y: int

    @property
    def plot_h(self) -> int:
        return self.plot_bottom - self.plot_top

    @property
    def plot_w(self) -> int:
        return self.w - 2 * self.pad


def _layout(theme: BrandTheme, w: int, h: int) -> Layout:
    """Charts live ABOVE the caption band. The number is the hero, but the spoken
    line still gets its captions — dropping them for chart beats would trade
    retention and accessibility for nothing."""
    pad = round(float(theme.safe.get("side", 0.055)) * w) + round(20 * w / 1080)
    return Layout(
        w=w, h=h, pad=pad,
        title_y=int(h * 0.145),
        plot_top=int(h * 0.245),
        plot_bottom=int(h * 0.605),
        footer_y=int(h * 0.645),
    )


def _point_color(theme: BrandTheme, p: DataPoint, is_highlight: bool,
                 rising: bool | None) -> tuple[int, int, int]:
    """Palette role for one datum. `auto` infers direction; everything else is the
    Director's explicit call. Green/red stay reserved for genuine direction."""
    if p.emphasis == "primary":
        return theme.rgb("primary")
    if p.emphasis == "positive":
        return theme.rgb("positive")
    if p.emphasis == "negative":
        return theme.rgb("negative")
    if p.emphasis == "normal":
        return theme.rgb("secondary")
    if is_highlight:
        if rising is True:
            return theme.rgb("positive")
        if rising is False:
            return theme.rgb("negative")
        return theme.rgb("primary")
    return theme.rgb("secondary")


def _y_range(values: list[float]) -> tuple[float, float]:
    """Axis bounds derived from the data with a little headroom.

    Deliberately anchors at zero for all-positive series: a truncated y-axis makes
    a 2% move look like a cliff, which is exactly the kind of misleading graphic a
    finance channel cannot ship.
    """
    lo, hi = min(values), max(values)
    if lo >= 0:
        lo = 0.0
    if hi <= 0:
        hi = 0.0
    if math.isclose(lo, hi):
        hi = lo + (abs(lo) or 1.0)
    span = hi - lo
    return lo - span * 0.04, hi + span * 0.12


# --------------------------------------------------------------------------- #
# Frame generators — each yields Canvases for the whole clip
# --------------------------------------------------------------------------- #
def _base_canvas(theme: BrandTheme, lay: Layout) -> Canvas:
    """Background + grid. Built once and copied per frame."""
    c = Canvas(lay.w, lay.h, bg=theme.rgb("bg"), bg_alpha=1.0)
    c.vgradient(0, 0, lay.w, lay.h, theme.rgb("bg_soft"), theme.rgb("bg"),
                0.55, 0.0)
    # the signature rule under the title ties charts to the lower third
    c.rect(lay.pad, lay.title_y + round(lay.h * 0.045), round(lay.w * 0.14), 5,
           theme.rgb("primary"), alpha=1.0, radius=2)
    return c


def _grid(c: Canvas, theme: BrandTheme, lay: Layout, rows: int = 4) -> None:
    alpha = float(theme.chart.get("grid_opacity", 0.5))
    for i in range(rows + 1):
        y = lay.plot_top + lay.plot_h * i / rows
        c.rect(lay.pad, y, lay.plot_w, 2, theme.rgb("grid"), alpha=alpha)


def _bars(theme: BrandTheme, lay: Layout, viz: DataViz, frames: int, fps: int):
    pts = viz.points
    n = len(pts)
    lo, hi = _y_range([p.value for p in pts])
    span = hi - lo or 1.0
    gap = lay.plot_w * 0.06 / max(1, n - 1) if n > 1 else 0
    bw = (lay.plot_w - gap * (n - 1)) / n
    radius = float(theme.chart.get("bar_radius_px", 8))
    hi_idx = viz.highlight if 0 <= viz.highlight < n else n - 1
    rising = pts[-1].value >= pts[0].value if n > 1 else None
    anim = float(theme.chart.get("animate_sec", 1.6))
    base = _base_canvas(theme, lay)
    _grid(base, theme, lay)

    zero_y = lay.plot_bottom - (0.0 - lo) / span * lay.plot_h
    for f in range(frames):
        t = f / fps
        c = base.copy()
        for i, p in enumerate(pts):
            # stagger each bar so the series builds rather than snapping in
            delay = anim * 0.35 * (i / max(1, n - 1)) if n > 1 else 0.0
            prog = ease_out_expo((t - delay) / max(0.2, anim * 0.65))
            x = lay.pad + i * (bw + gap)
            full_h = (p.value - lo) / span * lay.plot_h
            top_full = lay.plot_bottom - full_h
            h = (zero_y - top_full) * prog
            color = _point_color(theme, p, i == hi_idx, rising)
            alpha = 1.0 if i == hi_idx else 0.82
            if h >= 0:
                c.rect(x, zero_y - h, bw, max(h, 1.0), color, alpha, radius)
            else:
                c.rect(x, zero_y, bw, max(-h, 1.0), color, alpha, radius)
        yield c


def _line(theme: BrandTheme, lay: Layout, viz: DataViz, frames: int, fps: int):
    pts = viz.points
    n = len(pts)
    lo, hi = _y_range([p.value for p in pts])
    span = hi - lo or 1.0
    xs = [lay.pad + lay.plot_w * i / max(1, n - 1) for i in range(n)]
    ys = [lay.plot_bottom - (p.value - lo) / span * lay.plot_h for p in pts]
    rising = pts[-1].value >= pts[0].value
    color = theme.rgb("positive") if rising else theme.rgb("negative")
    lw = float(theme.chart.get("line_width_px", 9))
    dot = float(theme.chart.get("dot_radius_px", 16))
    anim = float(theme.chart.get("animate_sec", 1.6))
    base = _base_canvas(theme, lay)
    _grid(base, theme, lay)

    for f in range(frames):
        t = f / fps
        c = base.copy()
        prog = ease_in_out(t / max(0.2, anim))
        # how far along the polyline we've drawn, in segment units
        travel = prog * (n - 1)
        seg = min(int(travel), n - 2) if n > 1 else 0
        frac = travel - seg
        drawn = [(xs[i], ys[i]) for i in range(seg + 1)]
        if n > 1:
            drawn.append((xs[seg] + (xs[seg + 1] - xs[seg]) * frac,
                          ys[seg] + (ys[seg + 1] - ys[seg]) * frac))
        if len(drawn) >= 2:
            c.area_under(drawn, lay.plot_bottom, color, alpha=0.26)
            c.polyline(drawn, lw, color, alpha=1.0)
            head = drawn[-1]
            c.circle(head[0], head[1], dot * 0.55, theme.rgb("bg"), 1.0)
            c.circle(head[0], head[1], dot * 0.40, color, 1.0)
        yield c


def _counter(theme: BrandTheme, lay: Layout, viz: DataViz, frames: int, fps: int):
    """A single hero figure. The geometry is a growing accent rule under the
    number; the number itself is drawtext (see `_counter_filters`)."""
    base = _base_canvas(theme, lay)
    anim = float(theme.chart.get("animate_sec", 1.6))
    mid_y = (lay.plot_top + lay.plot_bottom) / 2
    p = viz.points[0]
    color = _point_color(theme, p, True, None)
    for f in range(frames):
        t = f / fps
        c = base.copy()
        prog = ease_out_cubic(t / max(0.2, anim * 0.8))
        w = lay.plot_w * 0.5 * prog
        c.rect(lay.w / 2 - w / 2, mid_y + round(lay.h * 0.055), w, 7, color,
               alpha=1.0, radius=3)
        # a soft halo so the number sits on something
        c.rect(lay.pad, mid_y - round(lay.h * 0.10), lay.plot_w,
               round(lay.h * 0.20), theme.rgb("bg_soft"),
               alpha=0.45 * prog, radius=18)
        yield c


def _delta(theme: BrandTheme, lay: Layout, viz: DataViz, frames: int, fps: int):
    """Before → after. Two plates that rise in sequence with a connecting arrow."""
    a, b = viz.points[0], viz.points[1]
    rising = b.value >= a.value
    col_b = theme.rgb("positive") if rising else theme.rgb("negative")
    base = _base_canvas(theme, lay)
    anim = float(theme.chart.get("animate_sec", 1.6))
    plate_w = lay.plot_w * 0.42
    plate_h = lay.plot_h * 0.52
    y = lay.plot_top + lay.plot_h * 0.12
    xa = lay.pad
    xb = lay.pad + lay.plot_w - plate_w

    for f in range(frames):
        t = f / fps
        c = base.copy()
        pa = ease_out_cubic(t / max(0.2, anim * 0.5))
        pb = ease_out_cubic((t - anim * 0.45) / max(0.2, anim * 0.5))
        c.rect(xa, y + (1 - pa) * 40, plate_w, plate_h, theme.rgb("bg_soft"),
               alpha=0.92 * pa, radius=16)
        c.rect(xa, y + (1 - pa) * 40, plate_w, 8, theme.rgb("ink_dim"),
               alpha=0.9 * pa, radius=4)
        if pb > 0:
            c.rect(xb, y + (1 - pb) * 40, plate_w, plate_h, theme.rgb("bg_soft"),
                   alpha=0.92 * pb, radius=16)
            c.rect(xb, y + (1 - pb) * 40, plate_w, 8, col_b, alpha=pb, radius=4)
        # connector: a rule that grows between the plates, then an arrow head
        cy = y + plate_h / 2
        x0 = xa + plate_w + lay.plot_w * 0.02
        x1 = xb - lay.plot_w * 0.02
        grow = ease_out_cubic((t - anim * 0.25) / max(0.2, anim * 0.5))
        if grow > 0:
            c.segment(x0, cy, x0 + (x1 - x0) * grow, cy, 7, col_b, alpha=1.0)
            if grow > 0.85:
                tip = x1
                c.segment(tip, cy, tip - 22, cy - 18, 7, col_b, 1.0)
                c.segment(tip, cy, tip - 22, cy + 18, 7, col_b, 1.0)
        yield c


def _donut(theme: BrandTheme, lay: Layout, viz: DataViz, frames: int, fps: int):
    p = viz.points[0]
    total = sum(abs(q.value) for q in viz.points) or abs(p.value) or 1.0
    share = max(0.0, min(1.0, abs(p.value) / total if len(viz.points) > 1
                         else abs(p.value) / 100.0))
    color = _point_color(theme, p, True, None)
    base = _base_canvas(theme, lay)
    anim = float(theme.chart.get("animate_sec", 1.6))
    cx, cy = lay.w / 2, (lay.plot_top + lay.plot_bottom) / 2
    r = min(lay.plot_w, lay.plot_h) * 0.33
    width = r * 0.30
    for f in range(frames):
        t = f / fps
        c = base.copy()
        c.ring(cx, cy, r, width, theme.rgb("grid"), alpha=0.75)
        prog = ease_out_cubic(t / max(0.2, anim))
        c.ring(cx, cy, r, width, color, alpha=1.0, start=0.0,
               sweep=max(1e-3, share * prog))
        yield c


def _meter(theme: BrandTheme, lay: Layout, viz: DataViz, frames: int, fps: int):
    p = viz.points[0]
    share = max(0.0, min(1.0, abs(p.value) / 100.0))
    color = _point_color(theme, p, True, None)
    base = _base_canvas(theme, lay)
    anim = float(theme.chart.get("animate_sec", 1.6))
    bar_h = round(lay.h * 0.035)
    y = lay.plot_bottom - bar_h * 2.2
    for f in range(frames):
        t = f / fps
        c = base.copy()
        c.rect(lay.pad, y, lay.plot_w, bar_h, theme.rgb("grid"), alpha=0.8,
               radius=bar_h / 2)
        prog = ease_out_expo(t / max(0.2, anim))
        c.rect(lay.pad, y, max(bar_h, lay.plot_w * share * prog), bar_h, color,
               alpha=1.0, radius=bar_h / 2)
        yield c


_GENERATORS = {
    "bar_compare": _bars, "line_trend": _line, "counter": _counter,
    "delta": _delta, "donut": _donut, "meter": _meter,
}


# --------------------------------------------------------------------------- #
# Typography pass — labels, axes, and the animated value roll-up
# --------------------------------------------------------------------------- #
def _counter_filters(theme: BrandTheme, lay: Layout, viz: DataViz, value: float,
                     x: str, y: int, size: int, color: str, duration: float,
                     start: float = 0.0) -> list[str]:
    """A number that counts up to `value`.

    drawtext can only print integer expressions, so a smooth decimal roll-up is
    impossible in one filter. Quantising into N stepped drawtexts (each gated by
    `enable=between(...)`) gives the same read at a cost of ~26 filters — cheap,
    and it keeps our own formatter in charge of how figures look.
    """
    steps = max(4, int(theme.chart.get("counter_steps", 26)))
    anim = min(float(theme.chart.get("animate_sec", 1.6)), max(0.4, duration * 0.6))
    out: list[str] = []
    for k in range(steps):
        t0 = start + anim * k / steps
        t1 = start + anim * (k + 1) / steps
        v = value * ease_out_expo((k + 1) / steps)
        out.append(tx.drawtext(
            format_value(v, viz), font=theme.mono.path, size=size, color=color,
            x=x, y=str(y), border=round(5 * lay.w / 1080),
            border_color=theme.ff("bg"), shadow=4,
            enable=f"between(t,{t0:.3f},{t1:.3f})"))
    out.append(tx.drawtext(
        format_value(value, viz), font=theme.mono.path, size=size, color=color,
        x=x, y=str(y), border=round(5 * lay.w / 1080),
        border_color=theme.ff("bg"), shadow=4,
        enable=f"gte(t,{start + anim:.3f})"))
    return out


def _labels(theme: BrandTheme, lay: Layout, viz: DataViz, kind: str,
            duration: float) -> list[str]:
    """All the type that sits on a chart: title, per-point labels and values,
    the source credit and the optional note."""
    out: list[str] = []
    anim = float(theme.chart.get("animate_sec", 1.6))
    pts = viz.points
    n = len(pts)
    hi_idx = viz.highlight if 0 <= viz.highlight < n else n - 1
    rising = pts[-1].value >= pts[0].value if n > 1 else None

    if viz.title:
        size = theme.size("chart_title", lay.h)
        out += tx.drawtext_block(
            tx.wrap(theme.display.apply_case(viz.title), size, lay.w, max_lines=2),
            font=theme.display.path, size=size, color=theme.ff("ink"),
            x=str(lay.pad), y_top=lay.title_y - size, shadow=3,
        )

    lbl = theme.size("chart_label", lay.h)

    if kind in ("counter", "meter", "donut"):
        p = pts[0]
        color = theme.ff("primary") if p.emphasis in ("auto", "primary") else \
            theme.ff(p.emphasis)
        mid = (lay.plot_top + lay.plot_bottom) / 2
        num_size = theme.size("stat_number", lay.h)
        # Each form puts its hero number somewhere different, and each has its own
        # geometry to stay clear of: the counter's accent rule, the donut's ring
        # hole, the meter's bar. One shared position collides with all three.
        if kind == "donut":
            num_size = round(num_size * 0.74)   # must fit inside the ring hole
            num_y = int(mid - num_size * 0.60)
            label_y = int(mid + min(lay.plot_w, lay.plot_h) * 0.33 * 1.30)
        elif kind == "meter":
            bar_h = round(lay.h * 0.035)
            bar_y = lay.plot_bottom - bar_h * 2.2
            num_y = int(bar_y - num_size * 1.20)
            label_y = int(bar_y + bar_h * 2.0)
        else:                                   # counter
            num_y = int(mid - num_size * 0.62)
            # clear the growing accent rule, which sits at mid + 0.055*h
            label_y = int(mid + lay.h * 0.055 + num_size * 0.22)
        out += _counter_filters(theme, lay, viz, p.value, "(w-text_w)/2", num_y,
                                num_size, color, duration)
        if p.label:
            out += tx.drawtext_block(
                tx.wrap(theme.body.apply_case(p.label), lbl, lay.w, max_lines=2),
                font=theme.body.path, size=lbl, color=theme.ff("ink_dim"),
                y_top=label_y, shadow=2,
                alpha=tx.fade_alpha(anim * 0.5, duration + 1.0, fade=0.3),
            )

    elif kind == "delta":
        a, b = pts[0], pts[1]
        plate_w = lay.plot_w * 0.42
        num_size = round(theme.size("stat_number", lay.h) * 0.52)
        y = int(lay.plot_top + lay.plot_h * 0.12 + lay.plot_h * 0.52 * 0.28)
        for i, (p, x_center) in enumerate((
                (a, lay.pad + plate_w / 2),
                (b, lay.pad + lay.plot_w - plate_w / 2))):
            color = (theme.ff("ink_dim") if i == 0 else
                     theme.ff("positive" if rising else "negative"))
            out += _counter_filters(theme, lay, viz, p.value,
                                    f"{int(x_center)}-text_w/2", y, num_size,
                                    color, duration, start=anim * 0.45 * i)
            out.append(tx.drawtext(
                theme.body.apply_case(p.label)[:18], font=theme.body.path,
                size=lbl, color=theme.ff("ink_dim"),
                x=f"{int(x_center)}-text_w/2", y=str(y + round(num_size * 1.25)),
                shadow=2))
        if a.value:
            pct = (b.value - a.value) / abs(a.value) * 100.0
            # ASCII sign, not ▲/▼: the fallback faces (DejaVu/Ubuntu) have no
            # geometric-shape glyphs and render a tofu box instead.
            arrow = "+" if pct >= 0 else "-"
            out.append(tx.drawtext(
                f"{arrow}{abs(pct):.0f}%", font=theme.mono.path,
                size=round(lbl * 1.15),
                color=theme.ff("positive" if pct >= 0 else "negative"),
                x="(w-text_w)/2",
                y=str(int(lay.plot_top + lay.plot_h * 0.70)), shadow=3,
                alpha=tx.fade_alpha(anim * 0.8, duration + 1.0, fade=0.25)))

    else:                                       # bar_compare / line_trend
        for i, p in enumerate(pts):
            if kind == "bar_compare":
                gap = lay.plot_w * 0.06 / max(1, n - 1) if n > 1 else 0
                bw = (lay.plot_w - gap * (n - 1)) / n
                cx = lay.pad + i * (bw + gap) + bw / 2
            else:
                cx = lay.pad + lay.plot_w * i / max(1, n - 1)
                cx = min(max(cx, lay.pad + 40), lay.pad + lay.plot_w - 40)
            delay = anim * 0.35 * (i / max(1, n - 1)) if n > 1 else 0.0
            out.append(tx.drawtext(
                str(p.label)[:14], font=theme.body.path, size=lbl,
                color=theme.ff("ink_dim"), x=f"{int(cx)}-text_w/2",
                y=str(lay.plot_bottom + round(lay.h * 0.012)), shadow=2))
            # Only the highlighted datum carries its value: labelling every bar
            # turns a graphic into a spreadsheet.
            if i == hi_idx:
                color = theme.ff("positive" if rising else "negative") \
                    if rising is not None else theme.ff("primary")
                size = round(theme.size("stat_number", lay.h) * 0.34)
                out += _counter_filters(
                    theme, lay, viz, p.value, f"{int(cx)}-text_w/2",
                    lay.plot_top - round(size * 1.1), size, color, duration,
                    start=delay)

    if viz.source:
        out.append(tx.drawtext(
            viz.source[:60], font=theme.body.path, size=theme.size("source", lay.h),
            color=theme.ff("ink_dim"), x=str(lay.pad), y=str(lay.footer_y),
            alpha=0.92, shadow=2))
    if viz.note:
        out += tx.drawtext_block(
            tx.wrap(viz.note, theme.size("chart_label", lay.h), lay.w, max_lines=2),
            font=theme.body.path, size=theme.size("chart_label", lay.h),
            color=theme.ff("ink_dim"), x=str(lay.pad),
            y_top=lay.footer_y + round(lay.h * 0.028), alpha=0.85, shadow=2)
    return out


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def cache_key(viz: DataViz, theme: BrandTheme, kind: str, width: int,
              height: int, fps: int, duration: float) -> str:
    """Everything the drawn pixels depend on, and nothing else.

    A chart is a pure function of its data, its geometry and the brand. Re-runs
    of the same Short redraw byte-identical frames, so the key is the content
    itself rather than the scene it happens to sit in — the same figure reused
    across two shorts hits the same entry.
    """
    body = json.dumps({
        "version": _CACHE_VERSION, "kind": kind,
        "viz": viz.model_dump(mode="json"),
        "width": width, "height": height, "fps": fps,
        "duration": round(duration, 4), "brand": theme.fingerprint,
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


async def render(viz: DataViz, theme: BrandTheme, out: Path, width: int,
                 height: int, fps: int, duration: float) -> Path:
    """Render one chart to an MP4 the renderer can drop in as a scene background.

    Geometry comes from numpy, type from drawtext, and both are applied in a
    SINGLE ffmpeg pass — a second pass would cost a full re-encode of every chart
    beat across thousands of shorts.
    """
    if not viz.valid():
        raise ValueError("refusing to render a chart with no real data")
    kind = viz.kind if viz.kind in _GENERATORS else auto_kind(viz)

    cached = visual_cache_path(
        "dataviz", cache_key(viz, theme, kind, width, height, fps, duration))
    if cached.is_file() and cached.stat().st_size > 1024:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, out)
        return out

    lay = _layout(theme, width, height)
    frames = max(1, int(round(duration * fps)))
    gen = _GENERATORS[kind](theme, lay, viz, frames, fps)
    vf = ",".join(_labels(theme, lay, viz, kind, duration)) or None
    result = await write_video(gen, width, height, fps, out, vf=vf)
    visual_cache_store(cached, result)
    return result


def summarize(viz: DataViz) -> str:
    """One line for the production log — what number is actually on screen."""
    kind = viz.kind if viz.kind in _GENERATORS else auto_kind(viz)
    vals = ", ".join(f"{p.label}={format_value(p.value, viz)}"
                     for p in viz.points[:4])
    src = f" · {viz.source}" if viz.source else ""
    return f"{kind}: {vals}{src}"
