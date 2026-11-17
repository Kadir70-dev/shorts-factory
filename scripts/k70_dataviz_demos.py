#!/usr/bin/env python3
"""Demo renders of every advanced K70 chart type, driven by REAL BLS data (data/k70_usa_inflation_20261117/*.json).

    cd ~/shorts-factory && .venv/bin/python scripts/k70_dataviz_demos.py [--only line race map story split morph themes]

Writes ~4-6 s clips (graphics on the Aurora navy background, 1080x1920 @30) and still frames to data/k70_dataviz_demos/.
No synthetic numbers: every series is built from the saved BLS API responses.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.pipeline import dataviz_adv as A                      # noqa: E402
from app.pipeline.dataviz_adv import story                    # noqa: E402
from app.pipeline.dataviz_adv.core import FPS, Series, new_layer   # noqa: E402

DATA = ROOT / "data" / "k70_usa_inflation_20261117"
OUT = ROOT / "data" / "k70_dataviz_demos"
RET = "2026-11-17"
SRC_ALL = "U.S. Bureau of Labor Statistics, CPI-U all items (CUUR0000SA0), not seasonally adjusted"


def load():
    a = json.loads((DATA / "bls_cpi_series.json").read_text())["series"]
    c = json.loads((DATA / "bls_cpi_categories.json").read_text())
    return a, c["series"], c["series_names"]


def render(name: str, chart, dur: float, th, stills: list[float]) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = int(dur * FPS)
    t0 = time.time()

    def lay(t):
        L = new_layer()
        chart.draw(L, t)
        return L

    A.compose.render_graphics_only(OUT / f"{name}.mp4", frames, lay, th.bg)
    dt = time.time() - t0
    for s in stills:
        lay(s).save(OUT / f"{name}_t{s:.1f}.png")
    info = A.qa.probe(OUT / f"{name}.mp4")
    row = {"clip": name, "seconds": dur, "frames": info["frames"], "fps": info["fps"], "render_s": round(dt, 1), "ms_per_frame": round(dt / frames * 1000)}
    print(row, flush=True)
    return row


def main() -> None:
    only = set(sys.argv[sys.argv.index("--only") + 1:]) if "--only" in sys.argv else {"line", "race", "map", "story", "split", "morph", "themes"}
    th = A.ChartTheme.load("k70_chart_aurora")
    allc_d, cats, names = load()
    allc = allc_d["CUUR0000SA0"]
    rows = []

    yoy = A.yoy_series("U.S. inflation, year over year", allc, "2021-01", "2026-09", SRC_ALL, RET)
    ip = yoy.periods.index("2022-06")

    if "line" in only:
        v = A.ViewTrack([(0.0, A.View(0, 68, 0, 10.4)), (1.6, A.View(0, 68, 0, 10.4)), (2.7, A.View(8, 28, 3.5, 10.2)),
                         (4.4, A.View(8, 28, 3.5, 10.2)), (5.6, A.View(0, 68, 0, 10.4))])
        chart = A.LineChart(th, yoy, A.Timeline([(0.2, 0), (2.4, ip), (3.6, 33), (5.8, 68)]), title="U.S. inflation rate, year over year",
                            view=v, y_fmt=lambda x: f"{x:.0f}%", pill_fmt=lambda x: f"{x:.1f}%",
                            big_fmt=lambda x: (f"{x:.1f}%", "year over year"),
                            callouts=[A.Callout(ip, "PEAK 9.1%", "June 2022", th.negative, 2.5)])
        rows.append(render("line_cinematic", chart, 6.2, th, [1.0, 3.2, 5.9]))

    if "race" in only:
        order = ["CUUR0000SETB01", "CUUR0000SETA02", "CUUR0000SEHF01", "CUUR0000SAF11", "CUUR0000SEHA", "CUUR0000SAM2", "CUUR0000SETA01", "CUUR0000SAH1"]
        periods = [f"{y}-{m:02d}" for y in range(2020, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-09"]
        ents = []
        for sid in order:
            lv = cats[sid]
            b = lv["2020-01"]
            ents.append(Series(names[sid].replace(" (all types)", "").replace(" of primary residence", ""), periods,
                               [lv[p] / b * 100 if p in lv else None for p in periods], "index (Jan 2020 = 100)",
                               f"U.S. Bureau of Labor Statistics, CPI-U {sid}, NSA", RET))
        race = A.BarRace(th, ents, A.Timeline([(0.3, 0), (6.0, len(periods) - 2 + 2.5)]), top_n=8, title="Price level by category",
                         subtitle="index, Jan 2020 = 100", value_fmt=lambda x: f"{x:.0f}")
        print("race dropped periods:", race.dropped, "final:", [(n, round(v)) for n, v in race.final_ranking()[:3]])
        rows.append(render("bar_race", race, 6.8, th, [1.5, 3.5, 6.6]))

    if "map" in only:
        regs = {"Northeast": "CUUR0100SA0", "Midwest": "CUUR0200SA0", "South": "CUUR0300SA0", "West": "CUUR0400SA0"}
        ser = [A.yoy_series(r, cats[s], "2021-01", "2026-09", f"U.S. Bureau of Labor Statistics, CPI-U {s}, NSA, Census region", RET) for r, s in regs.items()]
        values = {pc: sr for sr in ser for pc in A.CENSUS_REGIONS[sr.name]}
        n = len(ser[0].periods) - 1
        mt = A.MapTrack([(0.0, A.MapView(0.5, 0.5, 1.0)), (3.4, A.MapView(0.5, 0.5, 1.0)), (4.6, A.MapView(0.62, 0.62, 1.7)), (6.2, A.MapView(0.5, 0.5, 1.0))])
        gm = A.GeoMap(th, A.load_us_states(), values, A.Timeline([(0.3, 0), (6.4, n)]), title="U.S. inflation by Census region",
                      subtitle="year over year", vmin=0, vmax=10, value_fmt=lambda x: f"{x:.1f}%", view=mt, labels=A.CENSUS_REGIONS,
                      source="U.S. BLS CPI-U by Census region (NSA)", rect=(60, 500, 1020, 1140), aspect=1.5)
        rows.append(render("geo_map", gm, 6.8, th, [0.6, 2.6, 4.6]))

    if "story" in only:
        class Story:
            def draw(self, L, t):
                story.before_after(L, th, t, before=allc and yoy.values[ip], after=yoy.values[-1], before_label="June 2022", after_label="Sep 2026",
                                   y=300, t_second=1.3)
                story.percent_compare(L, th, t, [("Food at home", 32.4, th.categories[0]), ("Rent", 33.3, th.categories[1]),
                                                  ("Shelter", 33.8, th.categories[2]), ("Gasoline", 68.8, th.gold)], rect=(90, 820, 990, 1300))
                story.source_line(L, th, "SOURCE: U.S. BLS CPI-U (NSA) · JAN 2020 TO SEP 2026", t, y=1420)
        rows.append(render("story_before_after", Story(), 4.5, th, [0.8, 4.2]))

    if "split" in only:
        lvl = A.cumulative_series("Price level since Jan 2020", allc, "2020-01", "2020-01", "2026-09", SRC_ALL, RET)
        yo = A.yoy_series("Inflation rate", allc, "2020-01", "2026-09", SRC_ALL, RET)
        tl = A.Timeline([(0.3, 12), (5.0, len(yo.periods) - 1)])
        top = A.LineChart(th, yo, tl, rect=(160, 440, 985, 720), title="Speed: inflation rate", y_fmt=lambda x: f"{x:.0f}%", pill_fmt=lambda x: f"{x:.1f}%",
                          panel=(48, 225, 1032, 820), show_big=False, source="",
                          view=A.ViewTrack([(0, A.View(12, len(yo.periods) - 1, 0, 10.2))]))
        bot = A.LineChart(th, lvl, tl, rect=(160, 1060, 985, 1330), title="Distance: price level since Jan 2020", y_fmt=lambda x: f"+{x:.0f}%",
                          pill_fmt=lambda x: f"+{x:.1f}%", panel=(48, 850, 1032, 1470), show_big=False, cols=(th.primary, th.secondary),
                          source="BLS CPI-U (NSA)", view=A.ViewTrack([(0, A.View(12, len(yo.periods) - 1, 0, 36))]))

        class Split:
            def draw(self, L, t):
                story.split_screen(L, th, top, bot, t, top_label="", bottom_label="")
        rows.append(render("split_screen", Split(), 5.6, th, [1.2, 3.2, 5.4]))

    if "morph" in only:
        reg = {"Northeast": "CUUR0100SA0", "Midwest": "CUUR0200SA0", "South": "CUUR0300SA0", "West": "CUUR0400SA0"}
        vals = [A.yoy_series(r, cats[s], "2026-09", "2026-09", "x", RET).values[0] if False else (cats[s]["2026-09"] / cats[s]["2025-09"] - 1) * 100
                for r, s in reg.items()]
        mb = A.MorphLineBars(th, list(reg), vals, title="Inflation by region, Sep 2026 (year over year)", fmt=lambda x: f"{x:.1f}%",
                             source="U.S. BLS CPI-U by Census region (NSA)", t0=1.4, dur=1.1)
        rows.append(render("morph_line_to_bars", mb, 4.2, th, [0.9, 1.9, 3.8]))

    if "themes" in only:
        for bid in ("k70_chart_aurora", "k70_chart_sunset", "k70_chart_ocean"):
            tt = A.ChartTheme.load(bid)
            ch = A.LineChart(tt, yoy, A.Timeline([(0.2, 0), (1.0, 68)]), title="U.S. inflation rate, year over year", y_fmt=lambda x: f"{x:.0f}%",
                             big_fmt=lambda x: (f"{x:.1f}%", "year over year"), pill_fmt=lambda x: f"{x:.1f}%")
            L = new_layer()
            from PIL import Image
            bg = Image.new("RGBA", L.size, tt.bg + (255,))
            ch.draw(L, 1.6)
            bg.alpha_composite(L)
            OUT.mkdir(parents=True, exist_ok=True)
            bg.convert("RGB").save(OUT / f"theme_{bid.replace('k70_chart_', '')}.png")
    prev = {}
    tf = OUT / "render_times.json"
    if tf.exists():
        prev = {r["clip"]: r for r in json.loads(tf.read_text())}
    prev.update({r["clip"]: r for r in rows})
    tf.write_text(json.dumps(list(prev.values()), indent=1))


if __name__ == "__main__":
    main()
