"""Regression + rendering tests for the K70 advanced data-visualisation engine (pipeline/dataviz_adv).

They inspect real drawn frames (text boxes recorded while drawing) and a real FFmpeg render -- not just exit codes --
and use the saved BLS responses under data/k70_usa_inflation_20261117 (no synthetic financial numbers).
"""
from __future__ import annotations

import asyncio
import json
import math
import wave
from pathlib import Path

import numpy as np
import pytest

from app.pipeline import dataviz, dataviz_adv as A
from app.pipeline.dataviz_adv import qa, story
from app.pipeline.dataviz_adv.core import DataError, FPS, H, Series, W, new_layer
from app.schemas.scene import DataSeries, DataViz, SceneGraph

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "k70_usa_inflation_20261117"
RET = "2026-11-17"


@pytest.fixture(scope="module")
def th():
    return A.ChartTheme.load("k70_chart_aurora")


@pytest.fixture(scope="module")
def allc():
    return json.loads((DATA / "bls_cpi_series.json").read_text())["series"]["CUUR0000SA0"]


@pytest.fixture(scope="module")
def cats():
    return json.loads((DATA / "bls_cpi_categories.json").read_text())


@pytest.fixture(scope="module")
def yoy(allc):
    return A.yoy_series("US CPI-U YoY", allc, "2021-01", "2026-09", "U.S. BLS CPI-U CUUR0000SA0, NSA", RET)


def race_entities(cats):
    order = ["CUUR0000SETB01", "CUUR0000SETA02", "CUUR0000SEHF01", "CUUR0000SAF11", "CUUR0000SEHA", "CUUR0000SAM2", "CUUR0000SETA01", "CUUR0000SAH1"]
    periods = [f"{y}-{m:02d}" for y in range(2020, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-09"]
    out = []
    for sid in order:
        lv = cats["series"][sid]
        out.append(Series(cats["series_names"][sid], periods, [lv[p] / lv["2020-01"] * 100 if p in lv else None for p in periods],
                          "index (Jan 2020 = 100)", f"U.S. BLS CPI-U {sid}, NSA", RET))
    return out


# --------------------------------------------------------------------------- data integrity
def test_series_requires_source_units_and_unique_periods():
    ok = dict(name="x", periods=["2026-01", "2026-02"], values=[1.0, 2.0], units="%", source="BLS", retrieved=RET)
    Series(**ok).validate()
    for bad in (dict(ok, source=""), dict(ok, units=""), dict(ok, periods=["2026-01", "2026-01"]), dict(ok, values=[1.0, float("nan")]),
                dict(ok, values=[None, None]), dict(ok, periods=["2026-01"], values=[1.0])):
        with pytest.raises(DataError):
            Series(**bad).validate()


def test_cpi_figures_match_bls_source(allc, yoy):
    """The numbers narrated in the Short, recomputed from the saved BLS response."""
    peak = max((v, p) for v, p in zip(yoy.values, yoy.periods) if v is not None)
    assert peak[1] == "2022-06" and round(peak[0], 1) == 9.1
    assert round(yoy.values[yoy.periods.index("2023-06")]) == 3
    assert round(yoy.values[yoy.periods.index("2026-09")], 1) == 3.7
    assert round(yoy.values[yoy.periods.index("2026-01")], 1) == 2.4


def test_rate_and_level_are_different_quantities(allc, yoy):
    lvl = A.cumulative_series("level", allc, "2020-01", "2020-01", "2026-09", "BLS", RET)
    assert round(lvl.values[-1], 1) == 30.6                      # cumulative price level since Jan 2020
    assert round(yoy.values[-1], 1) == 3.7                       # the inflation RATE
    assert lvl.values[-1] > 8 * yoy.values[-1]
    assert lvl.values[0] == 0


def test_missing_months_stay_missing(yoy, allc):
    assert yoy.values[yoy.periods.index("2025-10")] is None      # BLS never published Oct 2025
    assert sum(v is None for v in yoy.values) == 1
    i = yoy.periods.index("2025-10")
    mid = yoy.at(i)                                               # interpolated for the dashed bridge only
    assert min(yoy.values[i - 1], yoy.values[i + 1]) <= mid <= max(yoy.values[i - 1], yoy.values[i + 1])


def test_interpolation_is_exact_and_clamped():
    s = Series("t", ["2026-01", "2026-02", "2026-03"], [0.0, 10.0, 30.0], "%", "BLS", RET).validate()
    assert s.at(0) == 0 and s.at(1) == 10 and s.at(0.5) == 5 and s.at(1.75) == 25
    assert s.at(-3) == 0 and s.at(99) == 30


# --------------------------------------------------------------------------- line chart: sync, axes, text
def line(th, yoy, **kw):
    ip = yoy.periods.index("2022-06")
    return A.LineChart(th, yoy, A.Timeline([(0.0, 0), (2.0, ip), (4.0, len(yoy.periods) - 1)]), title="U.S. inflation rate, year over year",
                       y_fmt=lambda v: f"{v:.0f}%", pill_fmt=lambda v: f"{v:.1f}%", big_fmt=lambda v: (f"{v:.1f}%", "year over year"),
                       callouts=[A.Callout(ip, "PEAK 9.1%", "June 2022", th.negative, 1.5)], **kw), ip


def test_year_value_synchronisation(th, yoy):
    ch, ip = line(th, yoy)
    for t, period in ((2.0, "2022-06"), (4.0, "2026-09")):
        h = ch.head(t)
        assert yoy.periods[int(round(h))] == period
        L, boxes = qa.draw_and_record(lambda lay, tt: ch.draw(lay, tt), t)
        big = next(b for b in boxes if b["tag"] == "big")
        assert big["text"] == f"{yoy.values[int(round(h))]:.1f}%"
        pill = next(b for b in boxes if b["tag"] == "pill")
        assert pill["text"] == big["text"]


def test_axes_units_and_source_are_drawn(th, yoy):
    ch, _ = line(th, yoy)
    _, boxes = qa.draw_and_record(lambda lay, tt: ch.draw(lay, tt), 3.0)
    yt = [b["text"] for b in boxes if b["tag"] == "ytick"]
    assert yt and all(t.endswith("%") for t in yt)
    xt = [b["text"] for b in boxes if b["tag"] == "xtick"]
    assert any(t.isdigit() and 2021 <= int(t) <= 2026 for t in xt)
    src = [b for b in boxes if b["tag"] == "source"]
    assert src and "BLS" in " ".join(b["text"] for b in src)


def test_camera_zoom_retags_axes(th, yoy):
    ip = yoy.periods.index("2022-06")
    track = A.ViewTrack([(0, A.View(0, 68, 0, 10.4)), (2, A.View(8, 28, 3.5, 10.2))])
    ch = A.LineChart(th, yoy, A.Timeline([(0, 0), (2, 40)]), view=track, y_fmt=lambda v: f"{v:.0f}%")
    _, wide = qa.draw_and_record(lambda lay, t: ch.draw(lay, t), 0.1)
    _, tight = qa.draw_and_record(lambda lay, t: ch.draw(lay, t), 2.0)
    wide_x = [b["text"] for b in wide if b["tag"] == "xtick"]
    tight_x = [b["text"] for b in tight if b["tag"] == "xtick"]
    assert wide_x != tight_x and any(len(x) > 4 for x in tight_x)          # months appear once zoomed
    # view window moves continuously (no jump between keyframes)
    prev = track.at(0)
    for k in range(1, 61):
        v = track.at(k / 30)
        assert abs(v.x0 - prev.x0) < 1.0 and abs(v.y1 - prev.y1) < 0.4
        prev = v


@pytest.mark.parametrize("t", [0.4, 1.2, 2.0, 3.0, 4.0])
def test_line_text_is_inside_safe_area_and_readable(th, yoy, t):
    ch, _ = line(th, yoy)
    _, boxes = qa.draw_and_record(lambda lay, tt: ch.draw(lay, tt), t)
    assert qa.text_issues(boxes) == []
    assert qa.overlap_issues(boxes, ("big", "biglabel", "title")) == []


# --------------------------------------------------------------------------- bar race
def test_bar_race_drops_unpublished_periods_and_validates(th, cats):
    ents = race_entities(cats)
    race = A.BarRace(th, ents, A.Timeline([(0, 0), (6, 78)]))
    assert race.dropped == ["2025-10"] and "2025-10" not in race.periods and race.T == 80
    with pytest.raises(DataError):
        A.BarRace(th, ents[:1], A.Timeline([(0, 0), (1, 1)]))
    bad = Series("shifted", ents[0].periods[1:] + ["2026-10"], ents[0].values, "x", "BLS", RET)
    with pytest.raises(DataError):
        A.BarRace(th, [ents[0], bad], A.Timeline([(0, 0), (1, 1)]))
    neg = Series("neg", ents[0].periods, [-1.0] * len(ents[0].periods), "x", "BLS", RET)
    with pytest.raises(DataError):
        A.BarRace(th, [ents[0], neg], A.Timeline([(0, 0), (1, 1)]))


def test_bar_race_ranking_swaps_are_smooth_and_correct(th, cats):
    race = A.BarRace(th, race_entities(cats), A.Timeline([(0.0, 0), (6.8, 78)]))
    prev, worst = None, 0.0
    for k in range(int(6.8 * FPS) + 1):
        h = race.head(k / FPS)
        v, pos, ax = race.state(h)
        assert np.isfinite(pos).all() and pos.min() > -0.6 and pos.max() < len(pos) + 0.6
        if prev is not None:
            worst = max(worst, float(np.abs(pos - prev).max()))
        prev = pos
    assert worst < 1.0, f"ranking jumps by {worst:.2f} rows in one frame"
    # at the last period the vertical order is exactly the value order
    v, pos, _ = race.state(race.T - 1)
    assert list(np.argsort(pos)) == list(np.argsort(-v))
    assert race.final_ranking()[0][0].startswith("Gasoline")


def test_bar_race_rows_keep_a_minimum_gap_in_steady_state(th, cats):
    """Near-tied bars are pushed apart (min row gap) so labels stay legible; rows only overlap while two bars swap."""
    race = A.BarRace(th, race_entities(cats), A.Timeline([(0.0, 0), (6.8, 78)]))
    for h in (25, 40, 60, 78):
        _, pos, _ = race.state(float(h))
        gaps = np.diff(np.sort(pos))
        assert gaps.min() > 0.4, f"rows overlap at period {h}: gaps {gaps.round(2)}"
    _, pos, _ = race.state(0.0)                                   # every value is 100 in the base month: rows are still inside the list
    assert pos.min() > -0.7 and pos.max() < len(pos) + 0.7


@pytest.mark.parametrize("t", [0.5, 2.5, 4.5, 6.6])
def test_bar_race_text_safe_and_values_do_not_collide(th, cats, t):
    race = A.BarRace(th, race_entities(cats), A.Timeline([(0.0, 0), (6.8, 78)]), title="Price level by category")
    _, boxes = qa.draw_and_record(lambda lay, tt: race.draw(lay, tt), t)
    assert qa.text_issues(boxes) == []
    assert any(b["tag"] == "period" for b in boxes)
    assert any(b["tag"] == "source" for b in boxes)


# --------------------------------------------------------------------------- map
def test_geo_map_regions_and_unmapped_features(th, cats):
    regs = {"Northeast": "CUUR0100SA0", "Midwest": "CUUR0200SA0", "South": "CUUR0300SA0", "West": "CUUR0400SA0"}
    ser = [A.yoy_series(r, cats["series"][s], "2021-01", "2026-09", "U.S. BLS CPI-U by Census region", RET) for r, s in regs.items()]
    values = {pc: s for s in ser for pc in A.CENSUS_REGIONS[s.name]}
    shapes = A.load_us_states()
    assert len(shapes) == 51 and set(values) == {s.fid for s in shapes}
    gm = A.GeoMap(th, shapes, values, A.Timeline([(0, 0), (3, len(ser[0].periods) - 1)]), vmin=0, vmax=10, title="Inflation by region",
                  labels=A.CENSUS_REGIONS, rect=(60, 500, 1020, 1140), aspect=1.5)
    assert gm.unmapped == []
    _, boxes = qa.draw_and_record(lambda lay, tt: gm.draw(lay, tt), 1.5)
    assert qa.text_issues(boxes) == []
    assert any(b["tag"] == "maplabel" for b in boxes) and any(b["tag"] == "source" for b in boxes)
    partial = {k: v for k, v in values.items() if k != "TX"}
    gm2 = A.GeoMap(th, shapes, partial, A.Timeline([(0, 0), (3, 1)]), vmin=0, vmax=10)
    assert gm2.unmapped == ["TX"]                                 # drawn neutral grey, never coloured with a guess
    with pytest.raises(DataError):
        A.GeoMap(th, shapes, values, A.Timeline([(0, 0), (1, 1)]), vmin=5, vmax=5)


# --------------------------------------------------------------------------- storytelling + transitions
def test_story_components_text_is_safe(th):
    class S:
        def draw(self, L, t):
            story.before_after(L, th, t, before=9.1, after=3.7, before_label="June 2022", after_label="Sep 2026", y=300, t_second=1.3)
            story.percent_compare(L, th, t, [("Food at home", 32.4, th.categories[0]), ("Rent", 33.3, th.categories[1]),
                                              ("Gasoline", 68.8, th.gold)], rect=(90, 820, 990, 1300))
    _, boxes = qa.draw_and_record(lambda lay, tt: S().draw(lay, tt), 3.0)
    assert qa.text_issues(boxes) == []
    assert qa.overlap_issues(boxes, ("ba_before", "ba_after")) == []
    after = next(b for b in boxes if b["tag"] == "ba_after")
    assert after["text"] == "3.7%"                                # counter lands exactly on the sourced value


def test_headline_too_wide_is_rejected(th):
    with pytest.raises(DataError):
        story.headline(new_layer(), th, [("INFLATION IS COOLING PRICES AREN'T", th.ink, 0.0)], 1.0, size=118)


def test_morph_is_continuous_and_valid(th):
    mb = A.MorphLineBars(th, ["NE", "MW", "S", "W"], [4.2, 4.2, 3.4, 3.4], title="By region", fmt=lambda v: f"{v:.1f}%", source="U.S. BLS", t0=1.0, dur=1.0)
    times = [k / FPS for k in range(15, 91)]                      # after the panel intro (the first frames fade a panel in)
    diffs = qa.frame_diff_series(lambda lay, t: mb.draw(lay, t), times)
    assert max(diffs) < 4 * (np.median(diffs) + 0.05) + 3.0, f"transition pops: max {max(diffs):.2f}, median {np.median(diffs):.2f}"
    _, boxes = qa.draw_and_record(lambda lay, tt: mb.draw(lay, tt), 2.5)
    assert qa.text_issues(boxes) == []
    with pytest.raises(DataError):
        A.MorphLineBars(th, ["a", "b"], [1, 2], source="")
    with pytest.raises(DataError):
        A.MorphLineBars(th, ["a"], [1], source="x")


def test_camera_track_is_smooth():
    cam = A.CameraTrack([(0, 1.0, 0.5, 0.5), (1, 1.4, 0.3, 0.6), (2, 1.0, 0.5, 0.5)])
    prev = cam.at(0)
    for k in range(1, 61):
        cur = cam.at(k / 30)
        assert abs(cur[0] - prev[0]) < 0.05 and abs(cur[1] - prev[1]) < 0.05
        prev = cur
    img = new_layer()
    assert A.apply_camera(img, 1.5, 0.2, 0.2).size == (W, H)


# --------------------------------------------------------------------------- themes / colours
@pytest.mark.parametrize("brand", ["k70_chart_aurora", "k70_chart_sunset", "k70_chart_ocean"])
def test_colorways_keep_semantic_red_green_out_of_categories(brand):
    t = A.ChartTheme.load(brand)
    assert len(set(t.categories)) == len(t.categories) >= 8
    assert t.negative not in t.categories and t.positive not in t.categories
    assert t.direction(1.0)[1] == "up" and t.direction(-1.0)[1] == "down" and t.direction(0.0)[1] is None


def test_original_k70_theme_is_untouched():
    from app.brand.theme import load_theme
    classic = load_theme("k70")
    assert not classic.chart.get("category_colors")
    assert classic.id == "k70"


# --------------------------------------------------------------------------- schema / pipeline compatibility
def test_schema_2_1_is_backwards_compatible():
    old = {"schema_version": "2.0", "meta": {"video_id": "v", "channel_id": "c", "niche": "n", "title": "t", "hook": "h"},
           "scenes": [{"id": "s1", "narration": "x", "data": {"kind": "counter", "points": [{"label": "a", "value": 1}]}}]}
    g = SceneGraph.model_validate(old)
    assert g.scenes[0].data.valid() and g.scenes[0].data.series == [] and g.scenes[0].data.config == {}


def test_advanced_kind_requires_sourced_series():
    pts = dict(name="n", periods=["2026-01", "2026-02"], values=[1.0, 2.0], units="%", retrieved=RET)
    assert not DataViz(kind="line_cinematic").valid()
    assert not DataViz(kind="line_cinematic", series=[DataSeries(**pts, source="")]).valid()
    assert DataViz(kind="line_cinematic", series=[DataSeries(**pts, source="BLS")]).valid()
    with pytest.raises(DataError):
        A.build_chart(DataViz(kind="line_cinematic", series=[DataSeries(**pts, source="")]), A.ChartTheme.load(), 3.0)


def test_classic_chart_still_renders_through_dataviz(tmp_path):
    from app.brand.theme import load_theme
    viz = DataViz(kind="counter", points=[{"label": "CPI", "value": 3.7}], suffix="%", source="BLS")
    out = asyncio.run(dataviz.render(viz, load_theme("k70_chart_aurora"), tmp_path / "c.mp4", W, H, FPS, 0.5))
    info = qa.probe(out)
    assert (info["w"], info["h"], info["fps"]) == (W, H, 30.0)


def test_advanced_kind_renders_through_dataviz_with_stable_fps(tmp_path, yoy):
    from app.brand.theme import load_theme
    viz = DataViz(kind="line_cinematic", title="U.S. inflation", series=[DataSeries(name=yoy.name, periods=yoy.periods, values=yoy.values,
                                                                                     units="%", source=yoy.source, retrieved=RET)],
                  config={"timeline": [[0.1, 0], [1.0, 68]], "decimals": 1, "unit": "%"})
    out = asyncio.run(dataviz.render(viz, load_theme("k70_chart_aurora"), tmp_path / "adv.mp4", W, H, FPS, 1.0))
    info = qa.probe(out)
    assert (info["w"], info["h"], info["fps"], info["frames"]) == (W, H, 30.0, 30)
    assert info["codec"] == "h264" and info["pix_fmt"] == "yuv420p"
    # a real frame: the chart pixels exist (not an empty navy plate) and nothing was drawn outside the frame
    img = np.asarray(qa.frame_to_image(out, 0.9))
    assert img.std() > 12


# --------------------------------------------------------------------------- caption / voice synchronisation helper
def test_caption_sync_detects_drift(tmp_path):
    sr = 16000
    sig = np.zeros(sr * 3, dtype=np.int16)
    for a, b in ((0.2, 0.9), (1.4, 2.2)):
        n = np.arange(int(a * sr), int(b * sr))
        sig[n] = (6000 * np.sin(2 * math.pi * 220 * n / sr)).astype(np.int16)
    wav = tmp_path / "v.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr), w.writeframes(sig.tobytes())
    act = qa.speech_activity(wav)
    good = qa.caption_sync(act, [{"w": "a", "s": 0.2, "e": 0.55}, {"w": "b", "s": 0.55, "e": 0.9}, {"w": "c", "s": 1.4, "e": 2.2}])
    assert good["words_over_silence"] == 0 and good["uncovered_loud_frames"] == 0
    drift = qa.caption_sync(act, [{"w": "a", "s": 1.0, "e": 1.3}, {"w": "c", "s": 2.4, "e": 2.9}])
    assert drift["words_over_silence"] == 2 and drift["uncovered_loud_frames"] > 5
