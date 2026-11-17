"""Animated bar-chart race.

Row positions come from a per-period ranking with HYSTERESIS (a bar only overtakes another when it leads by more than
`hysteresis` of the axis, so near-ties do not flip-flop and rows never stack on top of each other), box-filtered over
`swap_periods` so every overtake is a smooth slide.  Values interpolate linearly between published periods; periods
where ANY entity is unpublished are dropped, never filled; the last period is always strictly value-ordered.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageDraw

from .core import (rrect, ChartTheme, DataError, Series, source_block, Timeline, W, H, clamp, eio, eo3, glass_panel, lerp, month_label, nice_ticks,
                   put, text_tile)


def circle_icon(path: Path, size: int = 56) -> Image.Image:
    im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse([0, 0, size - 1, size - 1], fill=255)
    im.putalpha(m)
    return im


class BarRace:
    def __init__(self, th: ChartTheme, entities: list[Series], timeline: Timeline, *, top_n: int = 8,
                 rect=(60, 395, 1020, 1330), title: str = "", subtitle: str = "", value_fmt: Callable[[float], str] = lambda v: f"{v:.0f}",
                 source: str = "", colors: Optional[dict[str, tuple]] = None, icons: Optional[dict[str, Image.Image]] = None,
                 camera_zoom: float = 1.0, panel: Optional[tuple] = (48, 225, 1032, 1480), hysteresis: float = 0.006, swap_periods: float = 5.0):
        if len(entities) < 2:
            raise DataError("a bar race needs at least two entities")
        for e in entities:
            e.validate()
        base = entities[0].periods
        for e in entities:
            if e.periods != base:
                raise DataError(f"entity {e.name!r} is not aligned to the same periods as {entities[0].name!r}")
        keep = [i for i in range(len(base)) if all(e.values[i] is not None for e in entities)]
        self.dropped = [base[i] for i in range(len(base)) if i not in keep]
        if len(keep) < 2:
            raise DataError("fewer than two complete periods")
        self.periods = [base[i] for i in keep]
        self.names = [e.name for e in entities]
        self.vals = np.array([[e.values[i] for i in keep] for e in entities], dtype=float)      # (N, T)
        if (self.vals < 0).any():
            raise DataError("bar race supports non-negative values only (negative bars would be misleading)")
        self.units = entities[0].units
        self.source = source or entities[0].source
        self.th, self.tl, self.top_n, self.rect = th, timeline, min(top_n, len(entities)), rect
        self.title, self.subtitle, self.value_fmt = title, subtitle, value_fmt
        self.panel, self.cam, self.swap = panel, camera_zoom, swap_periods
        order = np.argsort(-self.vals[:, -1], kind="stable")          # final ranking decides the colour order
        self.colors = {self.names[j]: th.categories[k % len(th.categories)] for k, j in enumerate(order)}
        self.icons = icons or {}
        self.T = len(self.periods)
        self.axis_max = self.vals.max(axis=0) * 1.12
        self.R = self._ranks(order, hysteresis)

    # -- time-dependent state ----------------------------------------------- #
    def head(self, t: float) -> float:
        return clamp(self.tl.at(t), 0, self.T - 1)

    def _ranks(self, start_order, hyst: float) -> np.ndarray:
        """R[e, k] = row of entity e in period k (0 = top), with hysteresis; strictly value-ordered at the last period."""
        N, T = self.vals.shape
        order = list(start_order)                      # ties in the base month fall back to the final ranking
        R = np.zeros((N, T))
        for k in range(T):
            delta = hyst * self.axis_max[k] if k < T - 1 else 0.0
            changed = True
            while changed:
                changed = False
                for i in range(N - 1):
                    a, b = order[i], order[i + 1]
                    if self.vals[b, k] - self.vals[a, k] > delta:
                        order[i], order[i + 1] = b, a
                        changed = True
            for row, e in enumerate(order):
                R[e, k] = row
        return R

    def state(self, h: float):
        """(values, row positions, axis max) at fractional period h; positions are box-filtered ranks so an overtake
        takes `swap_periods` periods and is continuous in time."""
        k = min(int(h), self.T - 2)
        f = h - k
        v = self.vals[:, k] * (1 - f) + self.vals[:, k + 1] * f
        ax = lerp(self.axis_max[k], self.axis_max[k + 1], f)
        offs = np.linspace(-self.swap / 2, self.swap / 2, 9)
        samples = np.stack([self._rank_at(clamp(h + o, 0, self.T - 1)) for o in offs])
        return v, samples.mean(axis=0), ax

    def _rank_at(self, x: float) -> np.ndarray:
        """Rank at fractional period x: ranks are held until the midpoint between two periods (nearest period)."""
        return self.R[:, int(round(x))]

    # -- frame --------------------------------------------------------------- #
    def draw(self, L: Image.Image, t: float, intro: bool = True) -> None:
        th = self.th
        a_in = eo3(t / 0.35) if intro else 1.0
        h = self.head(t)
        v, pos, ax = self.state(h)
        if self.panel:
            glass_panel(L, self.panel, th, a_in)
        px0 = self.panel[0] + 36 if self.panel else 60
        ty = self.panel[1] + 19 if self.panel else 240
        put(L, text_tile(self.title.upper(), th.body, 48, th.ink, None, 0, 4, spacing=2.2), px0, ty, alpha=a_in, tag="title", size=48)
        if self.subtitle:
            put(L, text_tile(self.subtitle.upper(), th.body, 36, th.dim, None, 0, 3, spacing=1.6), px0, ty + 62, alpha=a_in,
                tag="subtitle", size=36)
        rx0, ry0, rx1, ry1 = self.rect
        rh = (ry1 - ry0) / self.top_n
        bar_h = rh * 0.40
        bar_x0 = rx0 + 18
        bar_max_w = (rx1 - bar_x0) - 210                                  # room for the value label
        d = ImageDraw.Draw(L)
        # faint vertical grid at nice values
        for gv in nice_ticks(0, ax, 4):
            gx = bar_x0 + gv / ax * bar_max_w
            if gv > 0 and gx < rx1 - 200:
                for y in range(int(ry0), int(ry1), 26):
                    d.line([(gx, y), (gx, y + 10)], fill=(255, 255, 255, int(30 * a_in)), width=2)
        order = np.argsort(pos)
        for e in order:
            p = pos[e]
            if p > self.top_n - 0.35:
                continue
            fade = clamp((self.top_n - 0.35 - p) / 0.8) * a_in
            yrow = ry0 + p * rh
            w = max(8.0, v[e] / ax * bar_max_w)
            col = self.colors[self.names[e]]
            rrect(d, [bar_x0, yrow + rh * 0.54, bar_x0 + w, yrow + rh * 0.54 + bar_h], max(1, int(min(bar_h / 2 - 2, w / 2 - 2))),
                                fill=col + (int(255 * fade),))
            rrect(d, [bar_x0, yrow + rh * 0.54, bar_x0 + w, yrow + rh * 0.54 + bar_h * 0.45], max(1, int(min(bar_h * 0.16, w / 2 - 2))),
                                fill=(255, 255, 255, int(46 * fade)))
            ix = bar_x0
            ic = self.icons.get(self.names[e])
            if ic is not None:
                L.alpha_composite(ic, (int(ix), int(yrow + rh * 0.05)))
                ix += ic.width + 14
            put(L, text_tile(self.names[e].upper(), th.body, 44, th.ink, None, 0, 5, spacing=1.6), ix, yrow + rh * 0.04, alpha=fade,
                tag="name", size=44)
            put(L, text_tile(self.value_fmt(v[e]), th.display, 46, th.ink, None, 0, 5), bar_x0 + w + 16,
                yrow + rh * 0.54 + bar_h / 2, anchor="lm", alpha=fade, tag="value", size=46)
        # period indicator (the "year" counter)
        k = int(round(h))
        lab = month_label(self.periods[k])
        put(L, text_tile(lab, th.display, 96, th.gold, th.gold, 14, 8), rx1 - 6, ry0 - 70, anchor="rb", alpha=a_in * 0.95,
            tag="period", size=96)
        if self.source:
            source_block(L, th, self.source, px0 - 4, (self.panel[3] if self.panel else ry1 + 100) - 50, (self.panel[2] - self.panel[0]) - 68 if self.panel else 900, a_in)

    def final_ranking(self) -> list[tuple[str, float]]:
        return sorted(((n, float(self.vals[i, -1])) for i, n in enumerate(self.names)), key=lambda x: -x[1])
