#!/usr/bin/env python3
"""K70 Aurora USA-finance Short, V2 -- built on the advanced chart engine (pipeline/dataviz_adv).

V1 (K70_Aurora_USA_Inflation_Short.mp4) is NOT touched.  V2 fixes: weak hook, small charts, year/value sync,
number transitions, static chart scenes, slow cuts, no camera moves, weak chart<->footage transitions.

    cd ~/shorts-factory && .venv/bin/python scripts/k70_usa_inflation_short_v2.py            # full render
    cd ~/shorts-factory && .venv/bin/python scripts/k70_usa_inflation_short_v2.py --check    # facts + script only

Every number comes from data/k70_usa_inflation_20261117/bls_cpi_*.json (BLS API responses).  No upload / publish.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))
import k70_usa_inflation_short as V1          # noqa: E402  (facts, caption alignment, audio-mix repair)

WORK = V1.WORK
BRAND, CHANNEL = V1.BRAND, V1.CHANNEL
VIDEO_ID = "k70-usa-inflation-aurora-v2-20261117"
RET = "2026-11-17"
SRC_ALL = "U.S. Bureau of Labor Statistics, CPI-U all items (CUUR0000SA0), NSA"
FOOT = WORK / "footage"
OUT_MP4 = WORK / "K70_Aurora_USA_Inflation_Short_V2.mp4"

NARRATION = [
    ("s1", "hook", "Inflation fell by two thirds. Prices didn't."),
    ("s2", "context", "In June 2022, inflation hit 9.1 percent."),
    ("s2b", "context", "By 2023, it was down to near 3."),
    ("s3", "tension", "But slower inflation isn't lower prices."),
    ("s4", "insight", "Think of it as speed and distance."),
    ("s5", "insight", "Inflation is the speed. Prices are the distance:"),
    ("s5b", "evidence", "up more than 30 percent since 2020."),
    ("s6", "evidence", "Since 2020, groceries are up 32 percent."),
    ("s6b", "evidence", "Rent, up 33. Gasoline, up 69."),
    ("s7", "consequence", "Each year's increase stacks on top of the last."),
    ("s8", "reveal", "September: 3.7 percent. Up from 2.4 in January."),
    ("s9", "cta", "So cooling doesn't mean cheap. Watch the price level, not just the rate."),
]


def build(f: dict):
    from app.schemas.scene import AudioTrack, Overlay, Scene, SceneGraph, SceneMeta, Visual

    def vis(strategy: str, scene_type: str, note: str) -> Visual:
        # "dataviz" = prerendered by dataviz_adv / compose: the renderer keeps captions on and skips its own overlays
        return Visual(type="dataviz", strategy=strategy, scene_visual_type=scene_type, motion="none", decision_reason=note)

    chart = lambda: vis("dataviz", "data_viz", "authored: advanced chart on blurred real footage, BLS series")
    real = lambda: vis("real", "real_footage", "authored: licensed Pexels footage (footage_manifest.json)")
    stat_ov = [Overlay(type="stat", text="x", sub="x")]            # lets sfx.py land a hit on the number
    scenes = []
    for sid, role, text in NARRATION:
        v = chart() if sid in ("s2", "s5", "s6") else real()
        ov = stat_ov if sid in ("s2b", "s5b", "s6b", "s8") else []
        scenes.append(Scene(id=sid, narration=text, visual=v, beat_role=role, duration_sec=3.0, overlays=ov,
                            transition_in="whip" if sid in ("s2", "s5", "s6") else "cut"))
    meta = SceneMeta(
        video_id=VIDEO_ID, channel_id=CHANNEL, niche="usa_finance",
        title="Inflation Fell by Two Thirds. Prices Didn't.",
        hook="Inflation fell by two thirds. Prices didn't.",
        description=("U.S. inflation fell from 9.1% (June 2022) to about 3%, but the price LEVEL never reset: CPI is up about 31% since "
                     "January 2020. Data: U.S. Bureau of Labor Statistics CPI-U (not seasonally adjusted)."),
        tags=["inflation", "CPI", "cost of living", "BLS", "prices", "US economy"], hashtags=["#inflation", "#CPI", "#economy", "#shorts"],
        thumbnail_text="INFLATION FELL. PRICES DIDN'T.", structure_id="one_number_story")
    return SceneGraph(meta=meta, scenes=scenes, audio=AudioTrack(), brand_id=BRAND, fps=30, width=1080, height=1920)


# --------------------------------------------------------------------------- #
def render_scenes(graph, f: dict, theme) -> Path:
    from app.pipeline import dataviz_adv as A
    from app.pipeline.dataviz_adv import compose, story
    from app.pipeline.dataviz_adv.core import FPS, new_layer
    th = A.ChartTheme.from_brand(theme)
    series = V1.load_series()
    allc = series["CUUR0000SA0"]
    cats = json.loads((WORK / "bls_cpi_categories.json").read_text())
    dur = {s.id: s.duration_sec for s in graph.scenes}
    F = lambda n: FOOT / f"pexels_{n}.mp4"
    out_dir = WORK / "scenes_v2"
    out_dir.mkdir(exist_ok=True)
    ink, gold, cyan, vio, red = th.ink, th.gold, th.secondary, th.primary, th.negative

    def with_shade(fn):
        def ov(t):
            L = story.shade_layer()
            fn(L, t)
            return L
        return ov

    # ---- charts (sourced series) ------------------------------------------------------------------ #
    yoy_a = A.yoy_series("U.S. inflation rate, year over year", allc, "2021-01", "2023-06", SRC_ALL, RET)
    ip = yoy_a.periods.index("2022-06")
    d2 = dur["s2"]
    line = A.LineChart(
        th, yoy_a, A.Timeline([(0.25, 0), (d2 * 0.52, ip), (d2 - 0.35, len(yoy_a.periods) - 1)]), title="U.S. inflation rate, year over year",
        rect=(165, 650, 985, 1190), panel=(48, 225, 1032, 1330), tick_size=38,
        view=A.ViewTrack([(0.0, A.View(0, 29, 0, 10.6)), (d2 * 0.30, A.View(0, 29, 0, 10.6)), (d2 * 0.56, A.View(7, 27, 3.0, 10.2)),
                          (d2 * 0.74, A.View(7, 27, 3.0, 10.2)), (d2 - 0.2, A.View(0, 29, 0, 10.6))]),
        y_fmt=lambda v: f"{v:.0f}%", pill_fmt=lambda v: f"{v:.1f}%", big_fmt=lambda v: (f"{v:.1f}%", "year over year"),
        callouts=[A.Callout(ip, "PEAK 9.1%", "JUNE 2022", red, d2 * 0.55)])

    yo = A.yoy_series("Speed: inflation rate", allc, "2020-01", "2026-09", SRC_ALL, RET)
    lv = A.cumulative_series("Distance: price level since Jan 2020", allc, "2020-01", "2020-01", "2026-09", SRC_ALL, RET)
    d5 = dur["s5"]
    tl5 = A.Timeline([(0.3, 12), (d5 - 0.4, len(yo.periods) - 1)])
    top = A.LineChart(th, yo, tl5, rect=(165, 470, 985, 770), title="Speed: the inflation RATE", y_fmt=lambda v: f"{v:.0f}%", pill_fmt=lambda v: f"{v:.1f}%",
                      panel=(48, 225, 1032, 880), show_big=False, source="", tick_size=36,
                      view=A.ViewTrack([(0, A.View(12, len(yo.periods) - 1, 0, 10.6))]))
    bot = A.LineChart(th, lv, tl5, rect=(165, 1075, 985, 1290), title="Distance: the PRICE LEVEL, since Jan 2020", y_fmt=lambda v: f"+{v:.0f}%",
                      pill_fmt=lambda v: f"+{v:.1f}%", panel=(48, 890, 1032, 1425), show_big=False, cols=(vio, cyan), tick_size=36,
                      source="BLS CPI-U all items, NSA", view=A.ViewTrack([(0, A.View(12, len(yo.periods) - 1, 0, 36))]))

    order = ["CUUR0000SETB01", "CUUR0000SAF11", "CUUR0000SEHA", "CUUR0000SAH1", "CUUR0000SEHF01"]       # the categories the narration names, plus shelter + electricity
    periods = [f"{y}-{m:02d}" for y in range(2020, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-09"]
    ents = []
    for sid in order:
        lvl = cats["series"][sid]
        ents.append(A.Series(cats["series_names"][sid].replace(" (all types)", "").replace(" of primary residence", ""), periods,
                             [lvl[p] / lvl["2020-01"] * 100 if p in lvl else None for p in periods], "index (Jan 2020 = 100)",
                             f"U.S. BLS CPI-U {sid}, NSA", RET))
    d6 = dur["s6"]
    race = A.BarRace(th, ents, A.Timeline([(0.2, 0), (d6 - 0.9, 78)]), top_n=5, title="Price level by category", subtitle="labels: % change since Jan 2020",
                     value_fmt=lambda v: f"+{v - 100:.0f}%", source="U.S. BLS CPI-U (NSA); index Jan 2020 = 100", panel=(48, 225, 1032, 1480),
                     rect=(60, 500, 1020, 1330))
    assert race.dropped == ["2025-10"]
    cam6 = A.CameraTrack([(0, 1.0, 0.5, 0.45), (d6, 1.07, 0.5, 0.42)])

    # ---- overlay functions --------------------------------------------------------------------------- #
    f_jun23 = f["jun2023"]

    def ov_hook(L, t):
        story.headline(L, th, [("INFLATION", ink, 0.05), ("FELL.", gold, 0.30), ("PRICES", ink, 0.85), ("DIDN'T.", red, 1.10)], t, size=132, y0=270)
        story.source_line(L, th, "SOURCE: U.S. BLS CPI-U (NSA)", t, 0.6, y=1390)

    def ov_s2b(L, t):
        story.stat(L, th, t, f_jun23, suffix="%", label="June 2023", sub="down from the 9.1% peak", direction="down", start=9.1, decimals=1, dur=1.2, y=380)
        story.source_line(L, th, "SOURCE: U.S. BLS CPI-U (NSA) · 12-MONTH CHANGE", t, 0.4, y=1395)

    def ov_s3(L, t):
        story.headline(L, th, [("SLOWER", ink, 0.05), ("INFLATION", ink, 0.25), ("ISN'T", gold, 0.55), ("LOWER", gold, 0.72), ("PRICES.", gold, 0.90)], t, size=118, y0=300)

    d4 = dur["s4"]

    def ov_s4(L, t):
        h = d4 / 2
        if t < h:
            story.headline(L, th, [("INFLATION", cyan, 0.05), ("= SPEED", ink, 0.30)], t, size=140, y0=300)
        else:
            story.headline(L, th, [("PRICES", vio, 0.0), ("= DISTANCE", ink, 0.25)], t - h, size=140, y0=300)

    def ov_s5b(L, t):
        story.stat(L, th, t, f["level_change"], prefix="+", suffix="%", label="Price level since Jan 2020", sub="Jan 2020 to Sep 2026", direction="up", decimals=1,
                   dur=1.3, y=380)
        story.source_line(L, th, "SOURCE: U.S. BLS CPI-U (NSA)", t, 0.4, y=1395)

    d6b = dur["s6b"]

    def ov_s6b(L, t):
        if t < d6b * 0.5:
            story.stat(L, th, t, round(f["rent"]), prefix="+", suffix="%", label="Rent", sub="Jan 2020 to Sep 2026", direction="up", dur=0.7, y=380)
        else:
            story.stat(L, th, t - d6b * 0.5, round(f["gas"]), prefix="+", suffix="%", label="Gasoline", sub="Jan 2020 to Sep 2026", direction="up", dur=0.8, y=380)
        story.source_line(L, th, "SOURCE: U.S. BLS CPI-U (NSA)", t, 0.3, y=1395)

    d7 = dur["s7"]

    def ov_s7(L, t):
        if t < d7 / 2:
            story.headline(L, th, [("IT", ink, 0.05), ("STACKS.", gold, 0.20)], t, size=170, y0=300)
        else:
            story.headline(L, th, [("EVERY", ink, 0.0), ("YEAR.", cyan, 0.2)], t - d7 / 2, size=170, y0=300)

    def ov_s8(L, t):
        story.before_after(L, th, t, before=round(f["jan2026"], 1), after=round(f["sep2026"], 1), before_label="Jan 2026", after_label="Sep 2026",
                           y=300, t_second=dur["s8"] * 0.42)
        story.source_line(L, th, "INFLATION RATE, YEAR OVER YEAR · SOURCE: U.S. BLS CPI-U (NSA)", t, 0.5, y=1395)

    def ov_s9(L, t):
        story.headline(L, th, [("COOLING", ink, 0.15), ("ISN'T", ink, 0.45), ("CHEAP.", gold, 0.80)], t, size=190, y0=430, align="center")
        for txt, t0, y in (("WATCH THE PRICE LEVEL,", 1.55, 1190), ("NOT JUST THE RATE.", 1.8, 1260)):
            from app.pipeline.dataviz_adv.core import eo3, put, text_tile, W
            put(L, text_tile(txt, th.body, 62, cyan, None, 0, 5, spacing=3), W / 2, y + (1 - eo3((t - t0) / 0.4)) * 24, alpha=eo3((t - t0) / 0.4), anchor="cm",
                tag="closing", size=62)

    # ---- scene plan: (segments, bg, overlay) ------------------------------------------------------------ #
    d = dur
    off_aisle = 8.0
    plan = {
        "s1": ([(F(29369224), 0.0, 0.5), (F(8801848), 5.0, 0.5)], A.compose.Bg("plain"), with_shade(ov_hook)),
        "s2": ([(F(8799885), off_aisle, 1.0)], A.compose.Bg("ramp", blur_in=(0.0, 0.55), blur_out=(d["s2"] - 0.9, 0.7)),
               lambda t: _chart(line, t, d["s2"])),
        "s2b": ([(F(8799885), off_aisle + d["s2"], 1.0)], A.compose.Bg("plain"), with_shade(ov_s2b)),
        "s3": ([(F(9046227), 0.5, 0.5), (F(9046227), 5.5, 0.5)], A.compose.Bg("plain"), with_shade(ov_s3)),
        "s4": ([(F(32536402), 1.0, 0.5), (F(32536402), 6.0, 0.5)], A.compose.Bg("plain"), with_shade(ov_s4)),
        "s5": ([(F(32536402), 8.0, 1.0)], A.compose.Bg("ramp", blur_in=(0.0, 0.5), blur_out=(d["s5"] - 0.8, 0.6)),
               lambda t: _split(story, th, top, bot, t)),
        "s5b": ([(F(29576549), 2.0, 0.5), (F(8541111), 3.0, 0.5)], A.compose.Bg("plain"), with_shade(ov_s5b)),
        "s6": ([(F(8801848), 1.5, 1.0)], A.compose.Bg("ramp", blur_in=(0.0, 0.5), blur_out=(d["s6"] - 0.8, 0.6)),
               lambda t: _race(race, cam6, t)),
        "s6b": ([(F(8960335), 0.0, 0.5), (F(29576549), 8.0, 0.5)], A.compose.Bg("plain"), with_shade(ov_s6b)),
        "s7": ([(F(8799885), 4.0, 0.5), (F(8541111), 8.0, 0.5)], A.compose.Bg("plain"), with_shade(ov_s7)),
        "s8": ([(F(9046227), 6.0, 0.5), (F(8541111), 1.0, 0.5)], A.compose.Bg("plain"), with_shade(ov_s8)),
        "s9": ([(F(8960334), 1.0, 1.0)], A.compose.Bg("blur"), with_shade(ov_s9)),
    }
    cum, clips = 0.0, []
    for i, sc in enumerate(graph.scenes):
        segs, bg, ov = plan[sc.id]
        n = round((cum + sc.duration_sec) * FPS) - round(cum * FPS)
        total = n / FPS
        seg_list, off = [], 0.0
        for k, (clip, start, share) in enumerate(segs):
            sd = total * share if k < len(segs) - 1 else total - off
            seg_list.append((clip, start, sd))
            off += sd
        o = out_dir / f"{sc.id}.mp4"
        print(f"[motion] {sc.id} {n}f {sc.visual.strategy}", flush=True)
        compose.render_video(o, n, seg_list, ov, bg, first_scene=(i == 0))
        clips.append(o)
        cum += sc.duration_sec
    lst = out_dir / "scenes.txt"
    lst.write_text("\n".join(f"file '{c}'" for c in clips))
    silent = Path(graph.audio.voiceover_path).parents[1] / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True)
    return silent


def _chart(chart, t, dur):
    from app.pipeline.dataviz_adv import story
    from app.pipeline.dataviz_adv.core import new_layer
    L = story.shade_layer()
    chart.draw(L, t)
    return L


def _split(story, th, top, bot, t):
    from app.pipeline.dataviz_adv.core import new_layer
    L = new_layer()
    story.split_screen(L, th, top, bot, t, top_label="", bottom_label="")
    return L


def _race(race, cam, t):
    from app.pipeline.dataviz_adv.core import new_layer
    from app.pipeline.dataviz_adv.transitions import apply_camera
    L = new_layer()
    race.draw(L, t)
    z, cx, cy = cam.at(t)
    return apply_camera(L, z, cx, cy)


async def run(check_only: bool) -> None:
    f = V1.facts()
    graph = build(f)
    print(f"[script] {len(graph.scenes)} scenes, {sum(len(s.narration.split()) for s in graph.scenes)} spoken words")
    for s in graph.scenes:
        print(f"  {s.id:3} {s.visual.strategy:9} {s.narration}")
    if check_only:
        return
    from app.brand import load_theme, theme_for
    from app.config import load_channel
    from app.director import structures
    from app.pipeline import captions, compliance, music, postprocess, render_ffmpeg, sfx, tts, variety
    from app.schemas.video_spec import Niche, VideoSpec

    channel = load_channel(CHANNEL)
    spec = VideoSpec(channel_id=CHANNEL, niche=Niche("usa_finance"), topic="Inflation fell, prices didn't")
    spec.id = VIDEO_ID
    choice = structures.choose(spec.id, CHANNEL, "usa_finance", forced=graph.meta.structure_id, record=False)
    plan = variety.plan(spec.id, CHANNEL, load_theme(BRAND), choice)
    variety.apply(graph, plan)
    graph.variety["grade"] = "neutral_doc"
    graph.variety["caption_animation"] = "keyword_flash"
    graph = await tts.synthesize(graph, spec, channel)
    print(f"[tts] total {graph.total_duration_sec:.2f}s")
    graph = await captions.transcribe(graph, load_theme(BRAND))
    graph.captions = V1.aligned_captions(graph, load_theme(BRAND))
    graph = await music.add_music(graph, channel, family=plan.music_family)
    graph = await sfx.add_sound_design(graph)
    before = [s.narration for s in graph.scenes]
    print("[compliance] " + compliance.apply(graph, strict=False).format().replace("\n", "\n[compliance] "))
    assert before == [s.narration for s in graph.scenes]
    work = Path(graph.audio.voiceover_path).parents[1]
    (WORK / "scene_graph_v2.json").write_text(graph.model_dump_json(indent=1))
    th = theme_for(graph, "compositor")
    th.intro["enabled"] = False
    (work / "scene_graph.json").write_text(graph.model_dump_json())
    silent = render_scenes(graph, f, load_theme(BRAND))
    raw = str(work / "raw.mp4")
    await render_ffmpeg._finish(graph, silent, Path(raw), th)
    V1.fix_dropped_audio(graph, raw)
    final = await postprocess.finalize(graph, raw, channel)
    Path(final["mp4"]).replace(OUT_MP4) if False else None
    print("MP4:", final["mp4"])


if __name__ == "__main__":
    asyncio.run(run("--check" in sys.argv))
