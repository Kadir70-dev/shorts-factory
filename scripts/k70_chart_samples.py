#!/usr/bin/env python3
"""Two 5-second K70 Aurora chart samples (1080x1920 @ 30 fps) from verified BLS data -- nothing else is rendered.

    cd ~/shorts-factory && .venv/bin/python scripts/k70_chart_samples.py [--only race line]

1. Bar-chart race  -> the open-source `bar_chart_race` library (pip: bar_chart_race, MIT), styled with the K70 Aurora palette
2. Animated line   -> the existing K70 renderer (pipeline/dataviz_adv LineChart), with a head-synchronised date readout

Data: data/k70_usa_inflation_20261117/bls_cpi_categories.json and bls_cpi_series.json (U.S. BLS CPI-U API responses).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import matplotlib                                       # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt                         # noqa: E402
import pandas as pd                                     # noqa: E402
from matplotlib import font_manager                     # noqa: E402

DATA = ROOT / "data" / "k70_usa_inflation_20261117"
OUT = ROOT / "data" / "k70_chart_samples"
FONTS = ROOT / "config" / "brand" / "fonts"
W, H, FPS, SECONDS = 1080, 1920, 30, 5
SOURCE = "Source: U.S. Bureau of Labor Statistics, CPI-U (NSA)"


def aurora():
    from app.pipeline.dataviz_adv import ChartTheme
    return ChartTheme.load("k70_chart_aurora")


def hexc(c):
    return "#%02X%02X%02X" % tuple(c)


# --------------------------------------------------------------------------- #
# 1. bar-chart race (open-source library)
# --------------------------------------------------------------------------- #
def race_frame() -> tuple[pd.DataFrame, list[str]]:
    cats = json.loads((DATA / "bls_cpi_categories.json").read_text())
    ids = {"CUUR0000SETB01": "Gasoline", "CUUR0000SEHF01": "Electricity", "CUUR0000SAF11": "Food at home", "CUUR0000SEHA": "Rent",
           "CUUR0000SETA02": "Used cars"}
    # every 3rd month (Mar/Jun/Sep/Dec) from Sep 2020 to Sep 2026: 25 published periods; Oct 2025 (never published) is not used
    months = [f"{y}-{m:02d}" for y in range(2020, 2027) for m in (3, 6, 9, 12) if "2020-09" <= f"{y}-{m:02d}" <= "2026-09"]
    rows = {}
    for sid, name in ids.items():
        lv = cats["series"][sid]
        missing = [p for p in months + ["2020-01"] if p not in lv]
        assert not missing, (name, missing)                 # verified data only: no gaps, nothing interpolated by us
        rows[name] = [lv[p] / lv["2020-01"] * 100 for p in months]
    df = pd.DataFrame(rows, index=pd.to_datetime([m + "-15" for m in months]))
    return df, months


def _pandas_compat() -> None:
    """bar_chart_race 0.1.0 (2020) still calls `fillna(method=...)`, removed in pandas 3.  Shim it here instead of
    editing site-packages or pinning an old pandas."""
    def wrap(orig):
        def fillna(self, value=None, *args, method=None, **kw):
            if method in ("ffill", "pad"):
                return self.ffill(**{k: v for k, v in kw.items() if k in ("limit", "axis")})
            if method in ("bfill", "backfill"):
                return self.bfill(**{k: v for k, v in kw.items() if k in ("limit", "axis")})
            return orig(self, value, *args, **kw)
        return fillna
    for cls in (pd.Series, pd.DataFrame):
        if not getattr(cls.fillna, "_k70_compat", False):
            cls.fillna = wrap(cls.fillna)
            cls.fillna._k70_compat = True


def _declutter_value_labels() -> None:
    """Value labels of two bars that are crossing would print on top of each other: push them apart (>= 0.34 row)."""
    from bar_chart_race import _make_chart as mc
    if getattr(mc._BarChartRace.plot_bars, "_k70", False):
        return
    orig = mc._BarChartRace.plot_bars

    def plot_bars(self, i):
        orig(self, i)
        labels = self.ax.texts[1:] if self.period_label else list(self.ax.texts)
        labels = sorted(labels, key=lambda t: t.get_position()[1])
        gap = 0.34
        for a, b in zip(labels, labels[1:]):
            ya, yb = a.get_position()[1], b.get_position()[1]
            if yb - ya < gap:
                mid = (ya + yb) / 2
                a.set_y(mid - gap / 2)
                b.set_y(mid + gap / 2)
    plot_bars._k70 = True
    mc._BarChartRace.plot_bars = plot_bars


def hold_to(path: Path, seconds: float) -> None:
    """Hold the last frame so the finished ranking stays readable and the clip is exactly `seconds` long."""
    tmp = path.with_suffix(".tmp.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vf", f"tpad=stop_mode=clone:stop_duration={seconds}",
                    "-frames:v", str(int(seconds * FPS)), "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                    "-pix_fmt", "yuv420p", "-an", str(tmp)], check=True)
    tmp.replace(path)


def render_race(out: Path) -> dict:
    """K70-styled bar-chart race through the `bar_chart_race` library (it only draws bars/values/period; the K70 look,
    fonts, safe-area layout, title and source line are set here)."""
    _pandas_compat()
    _declutter_value_labels()
    import bar_chart_race as bcr
    th = aurora()
    for f in ("ArchivoBlack-Regular.ttf", "BarlowCondensed-Bold.ttf"):
        font_manager.fontManager.addfont(str(FONTS / f))
    bg, ink, dim, gold = hexc(th.bg), hexc(th.ink), hexc(th.dim), hexc(th.gold)
    plt.rcParams.update({"font.family": "Barlow Condensed", "font.weight": "bold", "text.color": ink})
    df, months = race_frame()
    colors = [hexc(c) for c in th.categories[:df.shape[1]]]
    PT = 72 / 100                                              # 1 px at dpi 100 in points
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=bg)
    ax = fig.add_axes([0.285, 0.20, 0.625, 0.56], facecolor=bg)
    n, vmax = df.shape[1], float(df.max().max())
    ax.set_ylim(0.2, n + 0.8)
    ax.set_xlim(0, vmax * 1.20)                                # fixed axis: bars never rescale mid-race
    ax.grid(True, axis="x", color=ink, alpha=0.14, linestyle=(0, (4, 6)), linewidth=2)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0, labelsize=52 * PT, colors=ink, pad=14)
    ax.tick_params(axis="x", length=0, labelsize=36 * PT, colors=dim, pad=10)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig.text(0.07, 0.915, "PRICES SINCE JAN 2020", fontsize=62 * PT, family="Archivo Black", weight="normal", color=ink, ha="left", va="center")
    fig.text(0.07, 0.875, "PRICE INDEX, JAN 2020 = 100", fontsize=40 * PT, color=dim, ha="left", va="center")
    fig.text(0.07, 0.085, SOURCE.upper(), fontsize=30 * PT, color=dim, ha="left", va="center")
    steps = 6                                                  # 6 frames per period at 30 fps -> 200 ms per period
    bcr.bar_chart_race(
        df, str(out), orientation="h", sort="desc", n_bars=n, fixed_order=False, fixed_max=True, steps_per_period=steps,
        period_length=int(1000 * steps / FPS), interpolate_period=True, label_bars=True, bar_size=0.52, cmap=colors,
        bar_label_size=50 * PT, shared_fontdict=None, fig=fig, dpi=100, bar_kwargs={"alpha": 1.0, "ec": "none"},
        period_label={"x": 0.97, "y": 1.085, "ha": "right", "va": "center", "size": 84 * PT, "family": "Archivo Black", "weight": "normal",
                      "color": gold}, period_fmt="%b %Y", filter_column_colors=False, writer=None)
    plt.close(fig)
    hold_to(out, SECONDS)
    return {"periods": len(months), "first": months[0], "last": months[-1]}


# --------------------------------------------------------------------------- #
# 2. animated line chart (existing K70 renderer: pipeline/dataviz_adv.LineChart)
# --------------------------------------------------------------------------- #
def render_line(out: Path) -> dict:
    from app.pipeline import dataviz_adv as A
    from app.pipeline.dataviz_adv.core import new_layer
    th = aurora()
    allc = json.loads((DATA / "bls_cpi_series.json").read_text())["series"]["CUUR0000SA0"]
    yoy = A.yoy_series("U.S. inflation rate, year over year", allc, "2021-01", "2026-09", "U.S. Bureau of Labor Statistics, CPI-U (NSA)", "2026-11-17")
    ip = yoy.periods.index("2022-06")
    n = len(yoy.periods) - 1
    chart = A.LineChart(
        th, yoy, A.Timeline([(0.15, 0), (1.9, ip), (3.0, 40), (4.5, n)]), title="U.S. inflation rate", rect=(170, 720, 985, 1250),
        panel=(48, 225, 1032, 1400), tick_size=40, y_fmt=lambda v: f"{v:.0f}%", pill_fmt=lambda v: f"{v:.1f}%",
        big_fmt=lambda v: (f"{v:.1f}%", "year over year"), date_fmt=A.month_label,
        view=A.ViewTrack([(0.0, A.View(0, n, 0, 10.6)), (0.9, A.View(0, n, 0, 10.6)), (1.6, A.View(8, 28, 3.2, 10.2)), (2.5, A.View(8, 28, 3.2, 10.2)),
                          (3.4, A.View(0, n, 0, 10.6))]),
        callouts=[A.Callout(ip, "PEAK 9.1%", "JUNE 2022", th.negative, 1.8)], source="Source: U.S. Bureau of Labor Statistics, CPI-U (NSA)")
    frames = SECONDS * FPS

    def lay(t):
        L = new_layer()
        chart.draw(L, t)
        return L

    A.compose.render_graphics_only(out, frames, lay, th.bg)
    return {"periods": len(yoy.periods), "gap": [p for p, v in zip(yoy.periods, yoy.values) if v is None]}


# --------------------------------------------------------------------------- #
def main() -> None:
    only = set(sys.argv[sys.argv.index("--only") + 1:]) if "--only" in sys.argv else {"race", "line"}
    OUT.mkdir(parents=True, exist_ok=True)
    if "race" in only:
        info = render_race(OUT / "sample_bar_chart_race.mp4")
        print("race", info)
    if "line" in only:
        print("line", render_line(OUT / "sample_animated_line.mp4"))


if __name__ == "__main__":
    main()
