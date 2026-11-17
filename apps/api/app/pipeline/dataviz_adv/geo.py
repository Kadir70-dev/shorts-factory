"""Animated choropleth maps on Natural Earth boundaries (public domain, data/geo/NATURAL_EARTH.txt).

Use only when the story is geographic.  A map takes `{feature_id: Series}`; every colour on screen is the value of
a sourced Series at the current period.  The camera (`MapView` keyframes) can zoom/pan to a region.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageChops, ImageDraw

from .core import (ChartTheme, DataError, Series, source_block, Timeline, W, clamp, eio5, eo3, glass_panel, lerp, mix, month_label, put,
                   text_tile)

GEO_DIR = Path(__file__).resolve().parents[5] / "data" / "geo"

# U.S. Census Bureau regions (public classification) -> postal codes
CENSUS_REGIONS: dict[str, list[str]] = {
    "Northeast": ["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"],
    "Midwest": ["IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"],
    "South": ["DE", "DC", "FL", "GA", "MD", "NC", "SC", "VA", "WV", "AL", "KY", "MS", "TN", "AR", "LA", "OK", "TX"],
    "West": ["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"],
}


def region_of(postal: str) -> Optional[str]:
    for r, states in CENSUS_REGIONS.items():
        if postal in states:
            return r
    return None


# --------------------------------------------------------------------------- #
# projections
# --------------------------------------------------------------------------- #
def _albers(lon: float, lat: float, lon0: float, lat0: float, p1: float, p2: float) -> tuple[float, float]:
    r = math.radians
    n = (math.sin(r(p1)) + math.sin(r(p2))) / 2
    c = math.cos(r(p1)) ** 2 + 2 * n * math.sin(r(p1))
    rho0 = math.sqrt(c - 2 * n * math.sin(r(lat0))) / n
    rho = math.sqrt(c - 2 * n * math.sin(r(lat))) / n
    th = n * r(lon - lon0)
    return rho * math.sin(th), -(rho0 - rho * math.cos(th))      # y grows downward on screen


_PARAMS = {"lower48": (-96.0, 37.5, 29.5, 45.5), "AK": (-154.0, 50.0, 55.0, 65.0), "HI": (-157.0, 3.0, 8.0, 18.0)}


@dataclass
class Shape:
    fid: str
    name: str
    rings: list[list[tuple[float, float]]]        # projected, normalised later


def _rings(geom: dict) -> list[list[tuple[float, float]]]:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return [[(p[0], p[1]) for p in poly[0]] for poly in polys]


@lru_cache(maxsize=4)
def load_us_states() -> list[Shape]:
    """50 states + DC, Albers-USA style composite (Alaska scaled/inset, Hawaii inset)."""
    data = json.loads((GEO_DIR / "us_states_110m.geojson").read_text())
    raw: dict[str, tuple[str, list]] = {}
    for f in data["features"]:
        raw[f["properties"]["postal"]] = (f["properties"]["name"], _rings(f["geometry"]))
    shapes: dict[str, list] = {}
    for pc, (_, rings) in raw.items():
        key = pc if pc in ("AK", "HI") else "lower48"
        lon0, lat0, p1, p2 = _PARAMS[key]
        shapes[pc] = [[_albers(x, y, lon0, lat0, p1, p2) for x, y in ring if (key != "lower48" or True)] for ring in rings]
        if key == "AK":      # drop the far-west Aleutian ring that wraps the date line
            shapes[pc] = [r for r in shapes[pc] if all(abs(p[0]) < 1.5 for p in r)]
    # bounding box of the lower 48, then inset AK / HI beneath the south-west
    ll = [p for pc, rs in shapes.items() if pc not in ("AK", "HI") for r in rs for p in r]
    x0, x1 = min(p[0] for p in ll), max(p[0] for p in ll)
    y0, y1 = min(p[1] for p in ll), max(p[1] for p in ll)
    w, h = x1 - x0, y1 - y0

    def place(pc: str, scale: float, ax: float, ay: float) -> None:
        pts = [p for r in shapes[pc] for p in r]
        px0, px1 = min(p[0] for p in pts), max(p[0] for p in pts)
        py0, py1 = min(p[1] for p in pts), max(p[1] for p in pts)
        shapes[pc] = [[(ax + (x - px0) * scale, ay + (y - py0) * scale) for x, y in r] for r in shapes[pc]]

    place("AK", 0.30, x0 + 0.01 * w, y1 + 0.03 * h)
    place("HI", 1.0, x0 + 0.27 * w, y1 + 0.09 * h)
    allp = [p for rs in shapes.values() for r in rs for p in r]
    gx0, gx1 = min(p[0] for p in allp), max(p[0] for p in allp)
    gy0, gy1 = min(p[1] for p in allp), max(p[1] for p in allp)
    sc = max(gx1 - gx0, gy1 - gy0)
    return [Shape(pc, raw[pc][0], [[((x - gx0) / sc, (y - gy0) / sc) for x, y in r] for r in rs]) for pc, rs in shapes.items()]


@lru_cache(maxsize=2)
def load_world() -> list[Shape]:
    """Equirectangular world (lon/lat -> 0..1), Antarctica clipped."""
    data = json.loads((GEO_DIR / "world_countries_110m.geojson").read_text())
    out = []
    for f in data["features"]:
        if f["properties"]["iso_a3"] == "ATA":
            continue
        rings = [[((x + 180) / 360, (84 - y) / 150) for x, y in ring] for ring in _rings(f["geometry"])]
        out.append(Shape(f["properties"]["iso_a3"], f["properties"]["name"], rings))
    return out


# --------------------------------------------------------------------------- #
@dataclass
class MapView:
    cx: float = 0.5
    cy: float = 0.5
    zoom: float = 1.0


class MapTrack:
    def __init__(self, keys: list[tuple[float, MapView]]):
        self.keys = sorted(keys, key=lambda k: k[0])

    def at(self, t: float) -> MapView:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        for (t0, a), (t1, b) in zip(ks, ks[1:]):
            if t <= t1:
                u = eio5((t - t0) / max(1e-9, t1 - t0))
                return MapView(lerp(a.cx, b.cx, u), lerp(a.cy, b.cy, u), math.exp(lerp(math.log(a.zoom), math.log(b.zoom), u)))
        return ks[-1][1]


class GeoMap:
    def __init__(self, th: ChartTheme, shapes: list[Shape], values: dict[str, Series], timeline: Timeline, *,
                 rect=(60, 520, 1020, 1210), title: str = "", subtitle: str = "", vmin: float, vmax: float,
                 value_fmt: Callable[[float], str] = lambda v: f"{v:.1f}%", ramp: Optional[list[tuple]] = None,
                 view: Optional[MapTrack] = None, labels: Optional[dict[str, list[str]]] = None, source: str = "",
                 panel=(48, 225, 1032, 1480), aspect: float = 1.0, highlight: Optional[Callable[[float], set]] = None):
        if vmax <= vmin:
            raise DataError("map colour scale needs vmax > vmin")
        for s in values.values():
            s.validate()
        base = next(iter(values.values())).periods
        if any(s.periods != base for s in values.values()):
            raise DataError("all map series must share the same periods")
        self.th, self.shapes, self.values, self.tl = th, shapes, values, timeline
        self.rect, self.title, self.subtitle, self.vmin, self.vmax = rect, title, subtitle, vmin, vmax
        self.fmt, self.view, self.labels, self.panel, self.aspect = value_fmt, view or MapTrack([(0, MapView())]), labels or {}, panel, aspect
        self.ramp = ramp or [th.bg_soft, th.secondary, th.primary]
        self.periods = base
        self.source = source or next(iter(values.values())).source
        self.highlight = highlight
        missing = [s.fid for s in shapes if s.fid not in values]
        self.unmapped = missing                         # drawn neutral grey, never coloured with a guess

    def head(self, t: float) -> float:
        return clamp(self.tl.at(t), 0, len(self.periods) - 1)

    def colour(self, v: float) -> tuple:
        u = clamp((v - self.vmin) / (self.vmax - self.vmin))
        n = len(self.ramp) - 1
        i = min(int(u * n), n - 1)
        return mix(self.ramp[i], self.ramp[i + 1], u * n - i)

    def draw(self, L: Image.Image, t: float, intro: bool = True) -> None:
        th = self.th
        a_in = eo3(t / 0.35) if intro else 1.0
        h = self.head(t)
        if self.panel:
            glass_panel(L, self.panel, th, a_in)
        px0 = self.panel[0] + 36 if self.panel else 60
        put(L, text_tile(self.title.upper(), th.body, 48, th.ink, None, 0, 4, spacing=2.2), px0, self.panel[1] + 19, alpha=a_in, tag="title", size=48)
        if self.subtitle:
            put(L, text_tile(self.subtitle.upper(), th.body, 36, th.dim, None, 0, 3, spacing=1.6), px0, self.panel[1] + 81, alpha=a_in,
                tag="subtitle", size=36)
        rx0, ry0, rx1, ry1 = self.rect
        rw, rh = int(rx1 - rx0), int(ry1 - ry0)
        SS = 2
        canvas = Image.new("RGBA", (rw * SS, rh * SS), (0, 0, 0, 0))
        cd = ImageDraw.Draw(canvas)
        mv = self.view.at(t)
        base = min(rw, rh * self.aspect) * mv.zoom * SS
        hl = self.highlight(t) if self.highlight else set()
        for s in self.shapes:
            ser = self.values.get(s.fid)
            fill = (70, 82, 104) if ser is None else self.colour(ser.at(h))
            dim = bool(hl) and s.fid not in hl
            if dim:
                fill = mix(fill, th.bg, 0.55)
            for ring in s.rings:
                pts = [(rw * SS / 2 + (x - mv.cx) * base, rh * SS / 2 + (y - mv.cy) * base) for x, y in ring]
                if max(p[0] for p in pts) < -50 or min(p[0] for p in pts) > rw * SS + 50:
                    continue
                cd.polygon(pts, fill=fill + (255,), outline=th.bg + (255,))
                cd.line(pts + [pts[0]], fill=(255, 255, 255, 70 if not dim else 25), width=2)
        canvas = canvas.resize((rw, rh), Image.LANCZOS)
        if a_in < 0.999:
            canvas.putalpha(canvas.getchannel("A").point(lambda v: int(v * a_in)))
        L.alpha_composite(canvas, (int(rx0), int(ry0)))
        # region labels with live values
        for name, ids in self.labels.items():
            pts = [(x, y) for s in self.shapes if s.fid in ids for ring in s.rings for x, y in ring]
            if not pts:
                continue
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            sx = rx0 + rw / 2 + (cx - mv.cx) * base / SS
            sy = ry0 + rh / 2 + (cy - mv.cy) * base / SS
            if not (rx0 + 40 < sx < rx1 - 40 and ry0 + 30 < sy < ry1 - 30):
                continue
            val = self.values[next(i for i in ids if i in self.values)].at(h)
            put(L, text_tile(name.upper(), th.body, 40, th.ink, None, 0, 6, spacing=1.5), sx, sy - 26, anchor="cm", alpha=a_in, tag="maplabel", size=40)
            put(L, text_tile(self.fmt(val), th.display, 50, th.gold, None, 0, 6), sx, sy + 24, anchor="cm", alpha=a_in, tag="mapvalue", size=50)
        self._legend(L, a_in)
        self._timeline(L, h, a_in)
        if self.source:
            source_block(L, th, self.source, px0 - 4, self.panel[3] - 50, self.panel[2] - self.panel[0] - 68, a_in)

    def _legend(self, L, a: float) -> None:
        rx0, ry0, rx1, ry1 = self.rect
        y = ry1 + 28
        bar = Image.new("RGBA", (int(rx1 - rx0 - 120), 22), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bar)
        for x in range(bar.width):
            bd.line([(x, 0), (x, 22)], fill=self.colour(lerp(self.vmin, self.vmax, x / (bar.width - 1))) + (255,))
        m = Image.new("L", bar.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, bar.width - 1, 21], 9, fill=255)
        bar.putalpha(ImageChops.multiply(bar.getchannel("A"), m))
        L.alpha_composite(bar, (int(rx0 + 60), int(y)))
        put(L, text_tile(self.fmt(self.vmin), self.th.body, 34, self.th.dim, None, 0, 0), rx0 + 60, y + 34, alpha=a, tag="legend", size=34)
        put(L, text_tile(self.fmt(self.vmax), self.th.body, 34, self.th.dim, None, 0, 0), rx1 - 60, y + 34, anchor="rt", alpha=a, tag="legend", size=34)

    def _timeline(self, L, h: float, a: float) -> None:
        th = self.th
        rx0, ry0, rx1, ry1 = self.rect
        y = ry1 + 150
        x0, x1 = rx0 + 60, rx1 - 60
        d = ImageDraw.Draw(L)
        d.line([(x0, y), (x1, y)], fill=(255, 255, 255, 60), width=4)
        n = len(self.periods) - 1
        for i, p in enumerate(self.periods):
            if p.endswith("-01"):
                x = lerp(x0, x1, i / n)
                d.line([(x, y - 9), (x, y + 9)], fill=(255, 255, 255, 110), width=3)
        hx = lerp(x0, x1, h / n)
        d.line([(x0, y), (hx, y)], fill=th.secondary + (255,), width=6)
        d.ellipse([hx - 13, y - 13, hx + 13, y + 13], fill=th.gold + (255,))
        put(L, text_tile(month_label(self.periods[int(round(h))]), th.display, 52, th.gold, None, 0, 5), (x0 + x1) / 2, y + 36, anchor="ct",
            alpha=a, tag="period", size=52)
