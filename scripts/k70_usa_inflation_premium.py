#!/usr/bin/env python3
"""K70 Aurora USA-finance Short, PREMIUM cut: "INFLATION FELL. PRICES DIDN'T." (35 s, 7 scenes).

Reuses the V1 facts/caption/audio helpers, the PR #13 chart engine (pipeline/dataviz_adv) and the PR #14 newspaper
card (dataviz_adv.press).  Every number is checked against data/k70_usa_inflation_20261117/bls_cpi_series.json (BLS API).
No upload / publish.

    .venv/bin/python scripts/k70_usa_inflation_premium.py --check     # data verification + script only
    .venv/bin/python scripts/k70_usa_inflation_premium.py --stills    # layout stills of every scene (no TTS / render)
    .venv/bin/python scripts/k70_usa_inflation_premium.py             # full render
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))
import k70_usa_inflation_short as V1          # noqa: E402

WORK = V1.WORK
BRAND, CHANNEL = V1.BRAND, V1.CHANNEL
VIDEO_ID = "k70-usa-inflation-premium-20261117"
RET = "2026-11-17"
FOOT = WORK / "footage"
OUT_MP4 = WORK / "K70_USA_Inflation_Premium_Final.mp4"
PREM = WORK / "premium"
SRC = "BLS CPI-U, all items, NSA"
RELEASE_URL = "https://www.bls.gov/news.release/archives/cpi_07132022.htm"
API_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0"

# (id, role, narration, window seconds, seconds of silence before the voice)
SCRIPT = [
    ("s1", "hook", "Inflation collapsed. Your grocery bill didn't.", 3.0, 0.0),
    ("s2", "context", "In June 2022, U.S. inflation hit 9.1 percent.", 4.0, 0.3),
    ("s3", "evidence", "A year later, it was just 3 percent. Sounds like a win, right?", 5.0, 0.5),
    ("s4", "tension", "But here's the trap: lower inflation doesn't mean prices went backwards.", 5.0, 0.15),
    ("s5", "evidence", "The price index actually rose over that same year.", 6.0, 0.9),
    ("s6", "insight", "It's like slowing a car. You're still moving forward, just not as fast.", 6.0, 0.2),
    ("s7", "cta", "Watch the price level, not just the inflation rate. Which bill still hurts most?", 6.0, 0.15),
]
WINDOW = {s[0]: s[3] for s in SCRIPT}


def verify() -> dict:
    """Hard guards: the on-screen / spoken numbers must equal the BLS data."""
    a = V1.load_series()["CUUR0000SA0"]
    f = {"cpi_jun21": a["2021-06"], "cpi_jun22": a["2022-06"], "cpi_jun23": a["2023-06"],
         "yoy_jun22": V1.yoy(a, "2022-06"), "yoy_jun23": V1.yoy(a, "2023-06")}
    assert a["2022-06"] == 296.311 and a["2023-06"] == 305.109, (a["2022-06"], a["2023-06"])
    assert round(f["yoy_jun22"], 1) == 9.1 and round(f["yoy_jun23"], 1) == 3.0, f
    assert f["cpi_jun23"] > f["cpi_jun22"]
    periods = [f"{2022 + (5 + k) // 12}-{(5 + k) % 12 + 1:02d}" for k in range(13)]
    assert periods[0] == "2022-06" and periods[-1] == "2023-06" and all(p in a for p in periods), periods
    return f


def build():
    from app.schemas.scene import AudioTrack, Scene, SceneGraph, SceneMeta, Visual
    scenes = []
    for sid, role, text, dur, _ in SCRIPT:
        chart = sid in ("s3", "s5")
        v = Visual(type="dataviz", strategy="dataviz" if chart else "real", scene_visual_type="data_viz" if chart else "real_footage",
                   motion="none", decision_reason="authored: BLS-sourced chart" if chart else "authored: licensed Pexels footage")
        scenes.append(Scene(id=sid, narration=text, visual=v, beat_role=role, duration_sec=dur, overlays=[],
                            transition_in="cut"))
    meta = SceneMeta(
        video_id=VIDEO_ID, channel_id=CHANNEL, niche="usa_finance",
        title="Inflation Fell. Prices Didn't.", hook="Inflation collapsed. Your grocery bill didn't.",
        description=("U.S. inflation fell from 9.1% (June 2022) to 3.0% (June 2023), but the CPI-U price index still rose, 296.311 to 305.109 "
                     "(not seasonally adjusted, 1982-84=100). Data: U.S. Bureau of Labor Statistics."),
        tags=["inflation", "CPI", "BLS", "prices", "US economy"], hashtags=["#inflation", "#CPI", "#economy", "#shorts"],
        thumbnail_text="INFLATION FELL. PRICES DIDN'T.", structure_id="one_number_story")
    return SceneGraph(meta=meta, scenes=scenes, audio=AudioTrack(), brand_id=BRAND, fps=30, width=1080, height=1920)


# --------------------------------------------------------------------------- #
def make_overlays(th, dur: dict[str, float], lead: dict[str, float]):
    """Returns {scene_id: (segments, overlay_fn or None, chart_fn or None)} ; times are scene-local."""
    from app.pipeline import dataviz_adv as A
    from app.pipeline.dataviz_adv import story
    from app.pipeline.dataviz_adv.core import eo3, put, text_tile, new_layer
    from PIL import Image
    allc = V1.load_series()["CUUR0000SA0"]
    ink, gold, cyan, red = th.ink, th.gold, th.secondary, th.negative
    F = lambda n: FOOT / f"pexels_{n}.mp4"

    def dip(L, t, d, fade_in=False, fade_out=False):          # quick dip to the chart plate colour (footage <-> chart cut)
        a = 0.0
        if fade_in:
            a = max(a, 1 - t / 0.22)
        if fade_out:
            a = max(a, 1 - (d - t) / 0.22)
        if a > 0.004:
            L.alpha_composite(Image.new("RGBA", L.size, th.bg + (int(255 * min(1, a)),)))

    # ---- s1 hook ----
    def ov1(t):
        L = story.shade_layer()
        story.headline(L, th, [("INFLATION", ink, 0.05), ("FELL?!", gold, 0.35)], t, size=150, y0=300)
        return L

    # ---- s2 newspaper ----
    news = A.NewsBrief(headline="U.S. Inflation Hits 9.1%", publisher="U.S. Bureau of Labor Statistics", published="2022-07-13",
                       source_url=RELEASE_URL, topic="CPI NEWS RELEASE")
    d2 = dur["s2"]

    def ov2(t):
        L = story.shade_layer()
        A.draw_news_brief(L, th, news, t - 0.3, hold=d2 - 0.3 - 0.05)
        dip(L, t, d2, fade_out=True)
        return L

    # ---- s3 chart 1 : cyan inflation rate ----
    th1 = dataclasses.replace(th, positive=cyan, negative=cyan)
    yoy = A.yoy_series("U.S. inflation rate, year over year", allc, "2022-06", "2023-06", SRC, RET)
    assert [round(v, 1) for v in yoy.values] == [9.1, 8.5, 8.3, 8.2, 7.7, 7.1, 6.5, 6.4, 6.0, 5.0, 4.9, 4.0, 3.0], yoy.values
    st1 = {"i": 0}
    t_end1 = lead["s3"] + 2.6
    line1 = A.LineChart(
        th1, yoy, A.Timeline([(0.3, 0), (t_end1, 12)]), title="U.S. inflation rate, 12-month change", y_floor=0, y_pad=0.14, snap=True,
        rect=(170, 740, 980, 1200), panel=(48, 225, 1032, 1340), tick_size=38, cols=(cyan, cyan),
        y_fmt=lambda v: f"{v:.0f}%", pill_fmt=lambda v: f"{v:.1f}%",
        big_fmt=lambda v: (f"{v:.1f}%", A.month_label(yoy.periods[st1["i"]]) + " · vs year before"),
        callouts=[A.Callout(0, "9.1%", "JUN 2022", red, 0.2), A.Callout(12, "3.0%", "JUN 2023", cyan, t_end1)])

    def ch3(t):
        st1["i"] = int(round(line1.head(t)))
        L = story.shade_layer()
        line1.draw(L, t)
        return L

    # ---- s5 chart 2 : gold CPI-U index ----
    th2 = dataclasses.replace(th, secondary=gold, primary=gold, positive=gold, negative=gold)
    keys = [f"{2022 + (5 + k) // 12}-{(5 + k) % 12 + 1:02d}" for k in range(13)]
    idx = A.Series("CPI-U price index (NSA)", keys, [allc[k] for k in keys], "index 1982-84=100", "U.S. BLS CUUR0000SA0", RET)
    assert idx.values[0] == 296.311 and idx.values[-1] == 305.109
    st2 = {"i": 0}
    t_end2 = lead["s5"] + 3.3
    line2 = A.LineChart(
        th2, idx, A.Timeline([(0.3, 0), (t_end2, 12)]), title="CPI-U price index, NSA", y_pad=0.16, snap=True, y_floor=295,
        rect=(190, 740, 980, 1180), panel=(48, 225, 1032, 1375), tick_size=38, cols=(gold, gold), source="",
        y_fmt=lambda v: f"{v:.0f}", pill_fmt=lambda v: f"{v:.3f}",
        big_fmt=lambda v: (f"{v:.3f}", A.month_label(idx.periods[st2["i"]]) + " · index level"),
        callouts=[A.Callout(0, "296.311", "JUN 2022", gold, 0.2)])

    def ch5(t):
        st2["i"] = int(round(line2.head(t)))
        L = story.shade_layer()
        line2.draw(L, t)
        put(L, text_tile("NOT SEASONALLY ADJUSTED · 1982-84 = 100", th.body, 34, th.dim, None, 0, 3, spacing=1.6), W / 2, 1296, anchor="cm", tag="nsa", size=34)
        put(L, text_tile("SOURCE: U.S. BLS, CPI-U ALL ITEMS (CUUR0000SA0)", th.body, 30, th.dim, None, 0, 3, spacing=1.2), W / 2, 1334, anchor="cm", tag="src", size=30)
        return L

    W = 1080

    # ---- s4 twist ----
    d4 = dur["s4"]

    def ov4(t):
        L = story.shade_layer()
        story.headline(L, th, [("BUT PRICES", ink, 0.1), ("DIDN'T", red, 0.5), ("FALL.", red, 0.8)], t, size=140, y0=300)
        dip(L, t, d4, fade_in=True)
        return L

    # ---- s6 car metaphor ----
    d6 = dur["s6"]

    def ov6(t):
        L = story.shade_layer()
        if t < d6 / 2:
            story.headline(L, th, [("INFLATION", cyan, 0.15), ("= SPEED", ink, 0.4)], t, size=130, y0=300)
        else:
            story.headline(L, th, [("PRICES", gold, 0.0), ("= DISTANCE", ink, 0.25)], t - d6 / 2, size=130, y0=300)
        return L

    # ---- s7 payoff ----
    def ov7(t):
        L = story.shade_layer()
        story.headline(L, th, [("SLOWER INFLATION", ink, 0.1), ("≠ LOWER PRICES", gold, 0.55)], t, size=84, y0=330)
        return L

    n = lambda s: dur[s]
    return {
        "s1": ([(F(29369224), 0.0, 0.5), (F(8541111), 3.0, 0.5)], ov1, None),
        "s2": ([(F(8799885), 8.0, 1.0)], ov2, None),
        "s3": (None, None, ch3),
        "s4": ([(F(29576549), 2.0, 0.5), (F(9046227), 0.5, 0.5)], ov4, None),
        "s5": (None, None, ch5),
        "s6": ([(F(32536402), 1.0, 0.5), (F(8801848), 6.0, 0.5)], ov6, None),
        "s7": ([(F(8541111), 6.0, 0.5), (F(8799885), 4.0, 0.5)], ov7, None),
    }


def render_scenes(graph, theme_brand, lead):
    from app.pipeline import dataviz_adv as A
    from app.pipeline.dataviz_adv import compose
    from app.pipeline.dataviz_adv.core import FPS
    th = A.ChartTheme.from_brand(theme_brand)
    dur = {s.id: s.duration_sec for s in graph.scenes}
    plan = make_overlays(th, dur, lead)
    out_dir = WORK / "scenes_premium"
    out_dir.mkdir(exist_ok=True)
    cum, clips, issues = 0.0, [], []
    for i, sc in enumerate(graph.scenes):
        segs, ov, chart = plan[sc.id]
        nfr = round((cum + sc.duration_sec) * FPS) - round(cum * FPS)
        total = nfr / FPS
        fn = chart or ov
        for tq in (0.5, total * 0.5, total - 0.2):
            A.Recorder.start()
            fn(tq)
            boxes = list(A.Recorder.active or [])
            A.Recorder.stop()
            issues += [f"{sc.id}@{tq:.2f}s: {m}" for m in A.qa.text_issues(boxes)]
        o = out_dir / f"{sc.id}.mp4"
        print(f"[motion] {sc.id} {nfr}f", flush=True)
        if chart:
            compose.render_graphics_only(o, nfr, chart, th.bg)
        else:
            seg_list, off = [], 0.0
            for k, (clip, start, share) in enumerate(segs):
                sd = total * share if k < len(segs) - 1 else total - off
                seg_list.append((clip, start, sd))
                off += sd
            compose.render_video(o, nfr, seg_list, ov, compose.Bg("plain"), first_scene=(i == 0))
        clips.append(o)
        cum += sc.duration_sec
    (PREM / "qa_text_issues.json").write_text(json.dumps(issues, indent=1))
    print(f"[qa] text issues in graphics layer: {len(issues)}", *issues[:10], sep="\n   ")
    lst = out_dir / "scenes.txt"
    lst.write_text("\n".join(f"file '{c}'" for c in clips))
    silent = Path(graph.audio.voiceover_path).parents[1] / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True)
    return silent


def stills() -> None:
    from app.brand import load_theme
    from app.pipeline import dataviz_adv as A
    from PIL import Image
    th = A.ChartTheme.from_brand(load_theme(BRAND))
    lead = {s[0]: s[4] for s in SCRIPT}
    plan = make_overlays(th, WINDOW, lead)
    (PREM / "stills").mkdir(parents=True, exist_ok=True)
    times = {"s1": [0.5, 2.0], "s2": [1.2, 3.0], "s3": [1.0, 2.5, 4.4], "s4": [0.5, 2.5], "s5": [1.0, 3.0, 5.4], "s6": [1.2, 4.5], "s7": [1.5, 3.8]}
    for sid, (segs, ov, ch) in plan.items():
        for t in times[sid]:
            L = (ch or ov)(t)
            if segs:
                clip, start, _ = segs[0]
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start + t), "-i", str(clip), "-frames:v", "1", "-vf",
                                "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", str(PREM / "stills" / "_bg.png")], check=True)
                bg = Image.open(PREM / "stills" / "_bg.png").convert("RGBA")
            else:
                bg = Image.new("RGBA", L.size, th.bg + (255,))
            bg.alpha_composite(L)
            bg.convert("RGB").resize((540, 960)).save(PREM / "stills" / f"{sid}_{t:.1f}.png")
    print("stills ->", PREM / "stills")


def pad_voice(graph):
    """Place each narration line inside its storyboard window (silence before the voice, tail to the window end)."""
    from app.pipeline.util import ffmpeg_concat_audio, ffprobe_duration
    job = Path(graph.audio.voiceover_path).parent
    clips = []
    for i, (sc, spec) in enumerate(zip(graph.scenes, SCRIPT)):
        clip = job / f"scene_{i:02d}.wav"
        trimmed = job / f"scene_{i:02d}_trim.wav"          # drop the engine's trailing silence so windows are exact
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-af",
                        "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse", str(trimmed)], check=True)
        trimmed.replace(clip)
        speech = ffprobe_duration(clip)
        lead = spec[4]
        target = max(spec[3], lead + speech + 0.25)
        tmp = job / f"scene_{i:02d}_pad.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-af",
                        f"adelay={int(lead * 1000)}:all=1,apad=whole_dur={target:.3f}", "-ar", "44100", "-ac", "1", str(tmp)], check=True)
        tmp.replace(clip)
        sc.duration_sec = round(ffprobe_duration(clip), 3)
        print(f"  {sc.id}: speech {speech:.2f}s lead {lead:.2f}s -> window {sc.duration_sec:.2f}s (storyboard {spec[3]:.1f}s)")
        clips.append(clip)
    master = job / "voiceover.wav"
    ffmpeg_concat_audio(clips, master)
    graph.audio.voiceover_path = str(master)
    return graph


def write_manifests() -> None:
    used = {29369224, 8541111, 8799885, 9046227, 8801848, 32536402, 29576549}
    base = json.loads((WORK / "footage_manifest.json").read_text())
    clips = [c for c in base["clips"] if c["id"] in used]
    have = {c["id"] for c in clips}
    for c in json.loads((WORK / "candidates" / "all_meta.json").read_text()).values():       # clips only recorded in the candidate search
        if c["id"] in used - have:
            clips.append({"provider": "Pexels", "id": c["id"], "page_url": c["url"], "author": c["user"], "author_url": c["user_url"],
                          "license": "Pexels License (free to use, no attribution required) https://www.pexels.com/license/",
                          "file": f"footage/pexels_{c['id']}.mp4", "download_resolution": "1080x1920", "duration_s": c["duration"],
                          "what_it_shows": c["query"], "modifications": "cropped to 9:16, slow push-in, colour grade; no watermark/logo added"})
    assert {c["id"] for c in clips} == used
    (PREM / "footage_license_manifest.json").write_text(json.dumps({"note": base["note"], "clips": clips}, indent=1))
    (PREM / "sources_manifest.json").write_text(json.dumps({
        "retrieved": RET,
        "data": [
            {"what": "CPI-U all items, U.S. city average, NSA, 1982-84=100 (CUUR0000SA0); Jun 2021 271.696, Jun 2022 296.311, Jun 2023 305.109",
             "publisher": "U.S. Bureau of Labor Statistics", "url": API_URL, "also_checked": "BLS Public Data API v1, re-queried live 2026-11-17: values identical to saved file"},
            {"what": "12-month change: Jun 2022 9.06% -> 9.1%; Jun 2023 2.97% -> 3.0% (computed from the index; matches BLS release)",
             "publisher": "U.S. Bureau of Labor Statistics"},
        ],
        "newspaper_card": {"headline": "U.S. Inflation Hits 9.1% (original K70 summary; no publisher masthead)",
                           "supporting_source": "BLS CPI news release USDL-22-1470, 'Consumer Price Index - June 2022'", "published": "2022-07-13",
                           "url": RELEASE_URL},
        "music_sfx": "Shorts Factory local generated/library assets (see job audio_manifest, graph.audio)",
        "voice": "Kokoro stock American English voice (self-hosted)"}, indent=1))


async def run(check_only: bool) -> None:
    f = verify()
    print("[verify] BLS:", {k: round(v, 3) for k, v in f.items()})
    graph = build()
    for s in SCRIPT:
        print(f"  {s[0]} {s[3]:>4}s  {s[2]}")
    if check_only:
        return
    PREM.mkdir(exist_ok=True)
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
    graph = pad_voice(graph)
    print(f"[tts] total {sum(s.duration_sec for s in graph.scenes):.2f}s")
    graph = await captions.transcribe(graph, load_theme(BRAND))
    graph.captions = V1.aligned_captions(graph, load_theme(BRAND))
    graph = await music.add_music(graph, channel, family=plan.music_family)
    graph = await sfx.add_sound_design(graph)
    before = [s.narration for s in graph.scenes]
    print("[compliance] " + compliance.apply(graph, strict=False).format().replace("\n", "\n[compliance] "))
    assert before == [s.narration for s in graph.scenes]
    work = Path(graph.audio.voiceover_path).parents[1]
    (PREM / "scene_graph.json").write_text(graph.model_dump_json(indent=1))
    th = theme_for(graph, "compositor")
    th.intro["enabled"] = False
    (work / "scene_graph.json").write_text(graph.model_dump_json())
    silent = render_scenes(graph, load_theme(BRAND), {s[0]: s[4] for s in SCRIPT})
    raw = str(work / "raw.mp4")
    await render_ffmpeg._finish(graph, silent, Path(raw), th)
    V1.fix_dropped_audio(graph, raw)
    final = await postprocess.finalize(graph, raw, channel)
    shutil.copyfile(final["mp4"], OUT_MP4)
    write_manifests()
    print("MP4:", OUT_MP4)


if __name__ == "__main__":
    if "--stills" in sys.argv:
        verify()
        PREM.mkdir(exist_ok=True)
        stills()
    else:
        asyncio.run(run("--check" in sys.argv))
