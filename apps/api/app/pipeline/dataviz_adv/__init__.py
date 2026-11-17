"""K70 advanced data-visualisation engine.

    from app.pipeline.dataviz_adv import ChartTheme, Series, LineChart, BarRace, GeoMap, MorphLineBars, story, render_viz

Chart kinds (schema 2.1 `DataViz.kind`): line_cinematic, bar_race, geo_map, morph_bars -- all driven by sourced
`DataSeries`.  `dataviz.render()` delegates here for those kinds, so existing Scene graphs keep working.
See docs/K70_ADVANCED_DATAVIZ.md.
"""
from __future__ import annotations

from pathlib import Path

from . import compose, qa, story, transitions
from .core import (ChartTheme, DataError, Recorder, Series, Timeline, View, ViewTrack, cumulative_series, fmt_number, month_label, nice_ticks,
                   yoy_series)
from .geo import CENSUS_REGIONS, GeoMap, MapTrack, MapView, load_us_states, load_world, region_of
from .line import Callout, LineChart
from .race import BarRace
from .transitions import CameraTrack, MorphLineBars, apply_camera

__all__ = ["ChartTheme", "DataError", "Series", "Timeline", "View", "ViewTrack", "LineChart", "Callout", "BarRace", "GeoMap", "MapTrack",
           "MapView", "MorphLineBars", "CameraTrack", "apply_camera", "story", "compose", "qa", "transitions", "build_chart", "render_viz",
           "yoy_series", "cumulative_series", "month_label", "nice_ticks", "fmt_number", "load_us_states", "load_world", "CENSUS_REGIONS",
           "region_of", "Recorder"]


def _series(viz) -> list[Series]:
    out = []
    for s in viz.series:
        out.append(Series(s.name, list(s.periods), list(s.values), s.units, s.source, s.retrieved).validate())
    if not out:
        raise DataError("advanced chart kinds need DataViz.series")
    return out


def build_chart(viz, th: ChartTheme, duration: float):
    """DataViz (schema 2.1) -> chart object with .draw(layer, t)."""
    cfg = viz.config or {}
    ser = _series(viz)
    n = len(ser[0].periods)
    dec = int(cfg.get("decimals", viz.decimals))
    unit = cfg.get("unit", viz.suffix or ("%" if ser[0].units == "%" else ""))
    fmt = (lambda v: f"{v:.{dec}f}{unit}")
    tl = Timeline([tuple(k) for k in cfg.get("timeline", [[0.2, 0], [max(0.6, duration * 0.78), n - 1]])])
    if viz.kind == "line_cinematic":
        views = None
        if cfg.get("views"):
            views = ViewTrack([(k[0], View(*k[1:])) for k in cfg["views"]])
        co = [Callout(int(c[0]), c[1], c[2] if len(c) > 2 else "", None, float(c[3]) if len(c) > 3 else 0.0) for c in cfg.get("callouts", [])]
        return LineChart(th, ser[0], tl, view=views, title=cfg.get("title", viz.title), y_fmt=lambda v: f"{v:.0f}{unit}", pill_fmt=fmt,
                         big_fmt=lambda v: (fmt(v), cfg.get("big_label", viz.note)), callouts=co, source=viz.source or ser[0].source,
                         y_floor=cfg.get("y_floor"))
    if viz.kind == "bar_race":
        return BarRace(th, ser, tl, top_n=int(cfg.get("top_n", 8)), title=cfg.get("title", viz.title), subtitle=cfg.get("subtitle", viz.note),
                       value_fmt=fmt, source=viz.source or ser[0].source)
    if viz.kind == "geo_map":
        shapes = load_us_states()
        by = cfg.get("by", "region")
        values = {}
        for s in ser:
            ids = CENSUS_REGIONS.get(s.name) if by == "region" else [s.name]
            for pc in ids or []:
                values[pc] = s
        return GeoMap(th, shapes, values, tl, title=cfg.get("title", viz.title), subtitle=cfg.get("subtitle", viz.note), vmin=float(cfg["vmin"]),
                      vmax=float(cfg["vmax"]), value_fmt=fmt, source=viz.source or ser[0].source,
                      labels=CENSUS_REGIONS if by == "region" and cfg.get("labels", True) else None)
    if viz.kind == "morph_bars":
        s = ser[0]
        return MorphLineBars(th, s.periods, [float(v) for v in s.values], title=cfg.get("title", viz.title), fmt=fmt,
                             source=viz.source or s.source, t0=float(cfg.get("t0", 1.2)), dur=float(cfg.get("dur", 1.0)))
    raise DataError(f"not an advanced kind: {viz.kind}")


async def render_viz(viz, theme, out: Path, width: int, height: int, fps: int, duration: float) -> Path:
    """Entry used by `pipeline.dataviz.render` for the advanced kinds (theme = BrandTheme)."""
    import asyncio
    th = ChartTheme.from_brand(theme)
    chart = build_chart(viz, th, duration)
    frames = max(1, int(round(duration * fps)))

    def layer(t):
        from .core import new_layer
        L = new_layer(width, height)
        chart.draw(L, t)
        return L

    out.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(compose.render_graphics_only, out, frames, layer, th.bg)
    return out
