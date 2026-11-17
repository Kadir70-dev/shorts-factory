"""Shared building blocks for the K70 advanced data-visualisation engine.

Pure functions of (data, time): no randomness, no network.  Everything is drawn with Pillow into RGBA frames
(1080x1920 by default) and handed to FFmpeg by `compose.py`.

Trust rules enforced here (see tests/test_dataviz_adv.py):
  * a `Series` must carry `source`, `units` and `retrieved` -- the engine refuses anonymous numbers
  * duplicate periods and non-finite values are rejected; missing values are kept as ``None`` (never invented)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE = 0.09, 0.19, 0.055          # fractions, same as the K70 brand `safe:` block


class DataError(ValueError):
    """Raised instead of drawing something misleading."""


# --------------------------------------------------------------------------- #
# colour / easing
# --------------------------------------------------------------------------- #
def rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1, c2, t: float) -> tuple[int, int, int]:
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c1, c2))  # type: ignore[return-value]


def eo3(x: float) -> float:
    return 1 - (1 - clamp(x)) ** 3


def eio(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


def eio5(x: float) -> float:
    x = clamp(x)
    return x * x * x * (x * (x * 6 - 15) + 10)


def eback(x: float, s: float = 1.9) -> float:
    x = clamp(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


# --------------------------------------------------------------------------- #
# theme
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChartTheme:
    """The subset of a K70 `BrandTheme` the engine needs, as plain tuples."""
    id: str
    bg: tuple
    bg_soft: tuple
    ink: tuple
    dim: tuple
    primary: tuple          # violet in Aurora
    secondary: tuple        # cyan in Aurora
    gold: tuple             # `warn`
    positive: tuple         # reserved: data direction "good"
    negative: tuple         # reserved: data direction "bad"
    grid: tuple
    categories: tuple       # distinct, balanced category colours (>= 8)
    display: str
    body: str

    @classmethod
    def from_brand(cls, theme) -> "ChartTheme":
        p = theme.palette
        sem = {rgb(p["positive"]), rgb(p["negative"])}                 # red/green keep their data-direction meaning
        cats = [c for c in (rgb(x) for x in (theme.chart.get("category_colors") or [])) if c not in sem]
        extras = [rgb(p["warn"]), rgb("#2DD4BF"), rgb("#93C5FD"), rgb("#C4B5FD"), rgb("#F9A8D4"), rgb("#FDBA74"), rgb("#38BDF8")]
        pool = cats + [c for c in extras if c not in cats and c not in sem]
        return cls(id=theme.id, bg=rgb(p["bg"]), bg_soft=rgb(p["bg_soft"]), ink=rgb(p["ink"]), dim=rgb(p["ink_dim"]),
                   primary=rgb(p["primary"]), secondary=rgb(p["secondary"]), gold=rgb(p["warn"]),
                   positive=rgb(p["positive"]), negative=rgb(p["negative"]), grid=rgb(p["grid"]),
                   categories=tuple(pool[:8]), display=str(theme.display.path), body=str(theme.body.path))

    @classmethod
    def load(cls, brand_id: str = "k70_chart_aurora") -> "ChartTheme":
        from ...brand.theme import load_theme
        return cls.from_brand(load_theme(brand_id))

    def direction(self, delta: float, eps: float = 0.0) -> tuple[tuple, Optional[str]]:
        """Meaningful direction colour (rising prices / rates = negative for consumers)."""
        if delta > eps:
            return self.negative, "up"
        if delta < -eps:
            return self.positive, "down"
        return self.gold, None


# --------------------------------------------------------------------------- #
# validated data
# --------------------------------------------------------------------------- #
@dataclass
class Series:
    name: str
    periods: list[str]
    values: list[Optional[float]]
    units: str                       # "%", "index (1982-84=100)", "USD" ...
    source: str                      # "U.S. Bureau of Labor Statistics, CPI-U, CUUR0000SA0"
    retrieved: str = ""              # ISO date the numbers were fetched
    notes: list[str] = field(default_factory=list)

    def validate(self) -> "Series":
        if not self.source.strip():
            raise DataError(f"series {self.name!r} has no source: refusing to draw unsourced numbers")
        if not self.units.strip():
            raise DataError(f"series {self.name!r} has no units")
        if len(self.periods) != len(self.values):
            raise DataError(f"series {self.name!r}: {len(self.periods)} periods vs {len(self.values)} values")
        if len(self.periods) < 2:
            raise DataError(f"series {self.name!r} needs at least 2 points")
        if len(set(self.periods)) != len(self.periods):
            dup = sorted({p for p in self.periods if self.periods.count(p) > 1})
            raise DataError(f"series {self.name!r} has duplicate periods: {dup[:3]}")
        for p, v in zip(self.periods, self.values):
            if v is not None and not math.isfinite(v):
                raise DataError(f"series {self.name!r}: non-finite value at {p}")
        if all(v is None for v in self.values):
            raise DataError(f"series {self.name!r} has no data")
        return self

    @property
    def valid_idx(self) -> list[int]:
        return [i for i, v in enumerate(self.values) if v is not None]

    def at(self, x: float) -> float:
        """Linear interpolation at fractional period index `x`; across a gap it interpolates between the two
        published neighbours (the chart draws that stretch dashed, it is never presented as data)."""
        idx = self.valid_idx
        x = clamp(x, idx[0], idx[-1])
        lo = max(i for i in idx if i <= x)
        hi = min(i for i in idx if i >= x)
        if lo == hi:
            return float(self.values[lo])
        return lerp(self.values[lo], self.values[hi], (x - lo) / (hi - lo))   # type: ignore[arg-type]


def yoy_series(name: str, level: dict[str, float], start: str, end: str, source: str, retrieved: str) -> Series:
    """12-month % change from a {'YYYY-MM': index} dict.  A month whose own or year-ago index is missing is `None`."""
    keys, (y, m) = [], (int(start[:4]), int(start[5:]))
    while (y, m) <= (int(end[:4]), int(end[5:])):
        keys.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    vals = []
    for k in keys:
        prev = f"{int(k[:4]) - 1}-{k[5:]}"
        vals.append((level[k] / level[prev] - 1) * 100 if k in level and prev in level else None)
    return Series(name, keys, vals, "%", source, retrieved, ["12-month change"]).validate()


def cumulative_series(name: str, level: dict[str, float], base: str, start: str, end: str, source: str, retrieved: str,
                      keep_gaps: bool = True) -> Series:
    """% change since `base` (cumulative: the PRICE LEVEL, not the rate)."""
    keys, (y, m) = [], (int(start[:4]), int(start[5:]))
    while (y, m) <= (int(end[:4]), int(end[5:])):
        keys.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    b = level[base]
    vals = [(level[k] / b - 1) * 100 if k in level else None for k in keys]
    return Series(name, keys, vals, "%", source, retrieved, [f"cumulative change since {base}"]).validate()


def month_label(period: str) -> str:
    names = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    return f"{names[int(period[5:7]) - 1]} {period[:4]}"


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    """'Nice' axis tick values inside [lo, hi]."""
    if hi <= lo:
        return [lo]
    span = hi - lo
    raw = span / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=10 * mag)
    first = math.ceil(lo / step - 1e-9) * step
    out, v = [], first
    while v <= hi + 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def fmt_number(v: float, decimals: int = 1, prefix: str = "", suffix: str = "", signed: bool = False) -> str:
    s = f"{abs(v):,.{decimals}f}" if decimals >= 0 else f"{abs(v):,.0f}"
    sign = "-" if v < 0 and round(abs(v), decimals) != 0 else ("+" if signed and v > 0 else "")
    return f"{sign}{prefix}{s}{suffix}"


# --------------------------------------------------------------------------- #
# camera: smooth view windows in data space
# --------------------------------------------------------------------------- #
@dataclass
class View:
    x0: float
    x1: float
    y0: float
    y1: float


class ViewTrack:
    """Keyframed data-space window.  Interpolated in log-space of the window size so zooms feel constant-speed."""

    def __init__(self, keys: list[tuple[float, View]], ease: Callable[[float], float] = eio5):
        if not keys:
            raise DataError("ViewTrack needs keyframes")
        self.keys, self.ease = sorted(keys, key=lambda k: k[0]), ease

    def at(self, t: float) -> View:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        for (t0, a), (t1, b) in zip(ks, ks[1:]):
            if t <= t1:
                u = self.ease((t - t0) / max(1e-9, t1 - t0))
                cx = lerp((a.x0 + a.x1) / 2, (b.x0 + b.x1) / 2, u)
                cy = lerp((a.y0 + a.y1) / 2, (b.y0 + b.y1) / 2, u)
                wx = math.exp(lerp(math.log(a.x1 - a.x0), math.log(b.x1 - b.x0), u))
                wy = math.exp(lerp(math.log(a.y1 - a.y0), math.log(b.y1 - b.y0), u))
                return View(cx - wx / 2, cx + wx / 2, cy - wy / 2, cy + wy / 2)
        return ks[-1][1]


class Timeline:
    """Maps scene time -> fractional period index with eased keyframes [(t, index), ...]."""

    def __init__(self, keys: list[tuple[float, float]], ease: Callable[[float], float] = eio):
        self.keys, self.ease = sorted(keys), ease

    def at(self, t: float) -> float:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        for (t0, i0), (t1, i1) in zip(ks, ks[1:]):
            if t <= t1:
                return lerp(i0, i1, self.ease((t - t0) / max(1e-9, t1 - t0)))
        return ks[-1][1]


# --------------------------------------------------------------------------- #
# text + compositing helpers
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=96)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=512)
def text_tile(text: str, face: str, size: int, fill, glow=None, glow_r: int = 14, shadow: int = 4,
              spacing: float = 0.0) -> Image.Image:
    """Text -> padded RGBA tile.  `fill` is an RGB tuple or a (top, bottom) gradient pair."""
    f = font(face, size)
    pad = (glow_r * 2 if glow else 0) + shadow + 8
    adv = [f.getlength(c) + spacing for c in text]
    w = int(sum(adv)) + pad * 2
    asc, desc = f.getmetrics()
    h = asc + desc + pad * 2
    mask = Image.new("L", (max(1, w), max(1, h)), 0)
    d = ImageDraw.Draw(mask)
    x = pad
    for c, a in zip(text, adv):
        d.text((x, pad), c, font=f, fill=255)
        x += a
    if isinstance(fill[0], tuple):
        arr = np.zeros((h, w, 4), np.uint8)
        for ch in range(3):
            arr[..., ch] = np.linspace(fill[0][ch], fill[1][ch], h, dtype=np.float32)[:, None]
        arr[..., 3] = 255
        body = Image.fromarray(arr, "RGBA")
    else:
        body = Image.new("RGBA", (w, h), tuple(fill) + (255,))
    body.putalpha(mask)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        sh.putalpha(mask.point(lambda v: int(v * 0.8)))
        out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(shadow)), (shadow // 2, shadow))
    if glow:
        gl = Image.new("RGBA", (w, h), tuple(glow) + (255,))
        gl.putalpha(mask.point(lambda v: int(v * 0.9)))
        out.alpha_composite(gl.filter(ImageFilter.GaussianBlur(glow_r)))
    out.alpha_composite(body)
    out.info["ink_pad"] = pad          # padding around the real glyphs (used by the bounds checker)
    out.info["text"] = text
    out.info["ink_bbox"] = mask.getbbox() or (0, 0, 1, 1)      # real glyph extents (not the font line box)
    return out


class Recorder:
    """Optional collector of every tile placed on a frame: lets tests assert 'no clipped / tiny / overlapping text'."""
    active: Optional[list] = None

    @classmethod
    def start(cls) -> list:
        cls.active = []
        return cls.active

    @classmethod
    def stop(cls) -> None:
        cls.active = None


def put(layer: Image.Image, tile: Image.Image, x: float, y: float, alpha: float = 1.0, scale: float = 1.0,
        anchor: str = "lt", tag: str = "", size: int = 0) -> None:
    """Alpha-composite `tile` at (x, y); anchor = {l,c,r}{t,m,b}."""
    if alpha <= 0.003 or scale <= 0.01:
        return
    pad = tile.info.get("ink_pad", 0)
    bb = tile.info.get("ink_bbox", (pad, pad, tile.width - pad, tile.height - pad))
    text = tile.info.get("text", "")
    if scale != 1.0:
        sc0 = tile
        tile = tile.resize((max(1, int(tile.width * scale)), max(1, int(tile.height * scale))), Image.BICUBIC)
        bb = tuple(v * scale for v in bb)
        tile.info.update({"ink_pad": int(pad * scale), "text": text})
    if alpha < 0.999:
        a = tile.getchannel("A").point(lambda v: int(v * alpha))
        tile = tile.copy()
        tile.putalpha(a)
    ax, ay = anchor[0], anchor[1]
    px = x - (tile.width / 2 if ax == "c" else tile.width if ax == "r" else 0)
    py = y - (tile.height / 2 if ay == "m" else tile.height if ay == "b" else 0)
    layer.alpha_composite(tile, (int(round(px)), int(round(py)))) if (
        -tile.width < px < layer.width and -tile.height < py < layer.height) else None
    if Recorder.active is not None and alpha > 0.5:
        Recorder.active.append({"tag": tag, "text": text, "x0": px + bb[0], "y0": py + bb[1], "x1": px + bb[2], "y1": py + bb[3],
                                "size": size, "alpha": alpha})


def source_block(layer: Image.Image, th: "ChartTheme", text: str, x: float, y: float, max_w: float, alpha: float = 1.0,
                 size: int = 31, max_lines: int = 2) -> None:
    """Source attribution that WRAPS inside `max_w` (never clipped); drawn bottom-up so the last line sits at `y`."""
    f = font(th.body, size)
    words, lines, cur = text.upper().split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if f.getlength(trial) + len(trial) * 0.6 <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        raise DataError(f"source text does not fit in {max_lines} lines: {text!r}")
    for i, ln in enumerate(lines):
        put(layer, text_tile(ln, th.body, size, th.dim, None, 0, 0, spacing=0.6), x, y + (i - (len(lines) - 1)) * (size + 8), alpha=alpha,
            tag="source", size=size)


def rrect(draw: ImageDraw.ImageDraw, box, radius: float, fill=None, outline=None, width: int = 1) -> None:
    """Rounded rectangle that never raises: the radius is clamped to the box (PIL fails when 2*radius >= height)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w < 1 or h < 1:
        return
    r = int(min(radius, w / 2 - 2, h / 2 - 2))
    if r < 1:
        draw.rectangle([x0, y0, x1, y1], fill=fill, outline=outline, width=width)
    else:
        draw.rounded_rectangle([x0, y0, x1, y1], r, fill=fill, outline=outline, width=width)


def vgrad(w: int, h: int, top_a: float, bot_a: float, color=(0, 0, 0)) -> Image.Image:
    a = np.linspace(top_a, bot_a, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., :3] = color
    arr[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def new_layer(w: int = W, h: int = H) -> Image.Image:
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def glass_panel(layer: Image.Image, box: tuple[int, int, int, int], th: ChartTheme, alpha: float = 1.0,
                accent: bool = True) -> None:
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, 40, fill=th.bg + (int(168 * alpha),), outline=(255, 255, 255, int(34 * alpha)), width=2)
    if accent:
        d.rounded_rectangle([x0, y0, x1, y0 + 7], 4, fill=th.primary + (int(200 * alpha),))


def start_flash(layer: Image.Image, t: float, strength: float = 0.25, dur: float = 0.16) -> None:
    if t < dur:
        layer.alpha_composite(Image.new("RGBA", layer.size, (255, 255, 255, int(255 * strength * (1 - t / dur) ** 2))))
