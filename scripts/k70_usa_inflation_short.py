#!/usr/bin/env python3
"""ONE K70 Aurora USA-finance Short: "Inflation is cooling. So why is everything still expensive?"

Authors the SceneGraph by hand (no Director call), pulls every number from the
saved BLS API response in data/k70_usa_inflation_20261117/bls_cpi_series.json,
and runs the normal Shorts Factory stages (tts -> assets -> captions -> music ->
sfx -> compliance -> render_ffmpeg -> postprocess).  It does NOT upload, schedule
or publish anything.

    cd ~/shorts-factory && .venv/bin/python scripts/k70_usa_inflation_short.py            # full render
    cd ~/shorts-factory && .venv/bin/python scripts/k70_usa_inflation_short.py --check    # facts + script only
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

WORK = ROOT / "data" / "k70_usa_inflation_20261117"
BLS = WORK / "bls_cpi_series.json"
BRAND = "k70_chart_aurora"
CHANNEL = "k70_economy"
VIDEO_ID = "k70-usa-inflation-aurora-20261117"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SRC = "Source: U.S. Bureau of Labor Statistics (CPI-U, NSA)"   # engine clips chart sources at 60 chars
LATEST = "2026-09"          # last month with a published year-over-year comparison (Oct 2025 was never published)
BASE = "2020-01"


# --------------------------------------------------------------------------- #
# Facts: every figure on screen is computed from the saved BLS response.
# --------------------------------------------------------------------------- #
def load_series() -> dict[str, dict[str, float]]:
    return json.loads(BLS.read_text())["series"]


def yoy(s: dict[str, float], key: str) -> float:
    y, m = key.split("-")
    return (s[key] / s[f"{int(y) - 1}-{m}"] - 1) * 100


def label(key: str) -> str:
    y, m = key.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def level_points(allc: dict[str, float]) -> list[tuple[str, float]]:
    keys, y, m = [], 2020, 1
    while (y, m) <= (2026, 9):
        keys.append(f"{y}-{m:02d}")
        m += 4
        if m > 12:
            m -= 12
            y += 1
    assert keys[0] == BASE and keys[-1] == LATEST and "2025-10" not in keys, keys
    out = []
    for k in keys:
        lab = "Jan 2020" if k == BASE else ("Sep 2026" if k == LATEST else "")
        out.append((lab, allc[k]))
    return out


def facts() -> dict:
    d = load_series()
    allc, food, rent, gas = d["CUUR0000SA0"], d["CUUR0000SAF11"], d["CUUR0000SEHA"], d["CUUR0000SETB01"]
    chg = lambda s: (s[LATEST] / s[BASE] - 1) * 100
    peak_key = max((k for k in allc if f"{int(k[:4]) - 1}-{k[5:]}" in allc), key=lambda k: yoy(allc, k))
    f = {
        "peak_key": peak_key, "peak": yoy(allc, peak_key),
        "jun2023": yoy(allc, "2023-06"),
        "level_change": chg(allc), "food": chg(food), "rent": chg(rent), "gas": chg(gas),
        "sep2026": yoy(allc, LATEST), "jan2026": yoy(allc, "2026-01"),
        "yoy_jun": [(str(y), yoy(allc, f"{y}-06")) for y in range(2021, 2027)],
        # every 4th month Jan 2020 -> Sep 2026 (evenly spaced in time; skips the never-published Oct 2025)
        "level": level_points(allc),
        "yoy_2026": [(MONTHS[m - 1], yoy(allc, f"2026-{m:02d}")) for m in range(1, 10)],
        "index_base": allc[BASE], "index_latest": allc[LATEST],
    }
    # Hard guards: the narration below states these rounded numbers.
    assert f["peak_key"] == "2022-06" and round(f["peak"], 1) == 9.1, f["peak"]
    assert round(f["jun2023"]) == 3, f["jun2023"]
    assert 30 < f["level_change"] < 31, f["level_change"]
    assert round(f["food"]) == 32 and round(f["rent"]) == 33 and round(f["gas"]) == 69, (f["food"], f["rent"], f["gas"])
    assert round(f["sep2026"], 1) == 3.7 and round(f["jan2026"], 1) == 2.4, (f["sep2026"], f["jan2026"])
    return f


# --------------------------------------------------------------------------- #
# Real footage: (clip file, start second) per scene.  Licences in footage_manifest.json
# --------------------------------------------------------------------------- #
FOOTAGE = {
    "s1": ("pexels_29369224.mp4", 0.0),    # shopper reading produce price tags ($ prices visible)
    "s2b": ("pexels_8799885.mp4", 18.0),   # supermarket aisle, cart POV (later in the same clip as s9)
    "s3": ("pexels_9046227.mp4", 0.5),     # retail checkout counter
    "s4": ("pexels_32536402.mp4", 1.0),    # US-style highway strip, trucks, gas-station signs
    "s6": ("pexels_8801848.mp4", 1.5),     # market produce aisle with US flag
    "s7": ("pexels_8960335.mp4", 0.0),     # HOUSE FOR RENT sign
    "s8": ("pexels_29576549.mp4", 2.0),    # gas pump, 87/89/93 octane buttons
    "s9": ("pexels_8799885.mp4", 4.0),     # supermarket aisle, cart POV
}


def build(f: dict):
    from app.schemas.scene import (AudioTrack, DataPoint, DataViz, Overlay, Scene, SceneGraph,
                                   SceneMeta, Visual)

    def real(sid: str, kw: list[str], intent: str) -> Visual:
        return Visual(type="broll", strategy="real", scene_visual_type="real_footage", motion="none",
                      query=FOOTAGE[sid][0], broll_keywords=kw, visual_intent=intent,
                      decision_reason="authored: licensed Pexels footage, see footage_manifest.json")

    chart = lambda: Visual(type="dataviz", strategy="dataviz", scene_visual_type="data_viz", motion="none",
                           decision_reason="authored: BLS CPI series")
    src_ov = Overlay(type="source", text="Source: BLS CPI-U · Jan 2020 to Sep 2026", y=0.90)

    yoy_chart = DataViz(
        kind="line_trend", title="U.S. inflation, year over year (each June)", suffix="%", decimals=1, highlight=1,
        points=[DataPoint(label=l, value=round(v, 1), emphasis="negative" if l == "2022" else "auto") for l, v in f["yoy_jun"]],
        source=SRC, note="CPI-U all items, 12-month % change, not seasonally adjusted")
    level_chart = DataViz(
        kind="line_trend", title="Consumer price level (CPI-U, 1982–84 = 100)", decimals=1, highlight=-1,
        points=[DataPoint(label=l, value=round(v, 1), emphasis="primary" if i == len(f["level"]) - 1 else "auto") for i, (l, v) in enumerate(f["level"])],
        source=SRC, note=f"+{f['level_change']:.1f}% from Jan 2020 to Sep 2026")
    y26_chart = DataViz(
        kind="line_trend", title="Inflation in 2026, year over year", suffix="%", decimals=1, highlight=-1,
        points=[DataPoint(label=l, value=round(v, 1), emphasis="negative" if i == len(f["yoy_2026"]) - 1 else "auto") for i, (l, v) in enumerate(f["yoy_2026"])],
        source=SRC, note="Jan 2.4% to Sep 3.7% · no Oct 2025 CPI")

    S = lambda sid, role, text, vis, **kw: Scene(id=sid, narration=text, visual=vis, beat_role=role, **kw)
    scenes = [
        S("s1", "hook", "Inflation is cooling. So why is everything still so expensive?",
          real("s1", ["grocery price tags", "supermarket produce prices"], "a shopper squinting at price tags"),
          duration_sec=3.6, overlays=[Overlay(type="headline", text="INFLATION IS COOLING. PRICES AREN'T.", y=0.12, emphasis="alert")]),
        S("s2", "context", "In June 2022, inflation hit 9.1 percent.", chart(), duration_sec=3.6, data=yoy_chart,
          transition_in="whip"),
        S("s2b", "context", "By 2023: near 3.", real("s2b", ["supermarket aisle"], "shopping on, prices unchanged"), duration_sec=2.4,
          overlays=[Overlay(type="stat", text="JUNE 2023", sub=f"{f['jun2023']:.1f}%", y=0.3, emphasis="normal"), src_ov]),
        S("s3", "tension", "But slowing inflation isn't falling prices.",
          real("s3", ["checkout counter", "cashier"], "the moment you pay"), duration_sec=2.6,
          overlays=[Overlay(type="headline", text="SLOWER ISN'T CHEAPER", y=0.12, emphasis="alert")]),
        S("s4", "insight", "Inflation is the speed. Prices are the distance already traveled.",
          real("s4", ["highway traffic", "trucks road"], "speed versus distance"), duration_sec=4.2,
          overlays=[Overlay(type="headline", text="RATE vs LEVEL", y=0.12)]),
        S("s5", "evidence", "Since 2020, prices are up more than 30 percent.", chart(), duration_sec=4.0, data=level_chart,
          transition_in="push_up"),
        S("s6", "evidence", "Groceries: up 32 percent.", real("s6", ["grocery market produce"], "fresh produce aisle"), duration_sec=2.4,
          overlays=[Overlay(type="stat", text="FOOD AT HOME", sub=f"+{f['food']:.0f}%", y=0.3, emphasis="negative"), src_ov]),
        S("s7", "evidence", "Rent: up 33 percent.", real("s7", ["house for rent sign"], "a rent sign"), duration_sec=1.9,
          overlays=[Overlay(type="stat", text="RENT", sub=f"+{f['rent']:.0f}%", y=0.3, emphasis="negative"), src_ov]),
        S("s8", "evidence", "Gasoline: up 69 percent.", real("s8", ["gas pump", "fuel"], "a gas pump"), duration_sec=2.2,
          overlays=[Overlay(type="stat", text="GASOLINE", sub=f"+{f['gas']:.0f}%", y=0.3, emphasis="negative"), src_ov]),
        S("s9", "consequence", "Each year stacks on the last. Slower inflation only slows the climb.",
          real("s9", ["supermarket aisle", "shopping cart"], "an endless supermarket aisle"), duration_sec=5.0,
          overlays=[Overlay(type="headline", text="IT STACKS.", y=0.12)]),
        S("s10", "reveal", "September: 3.7 percent. Up from 2.4 in January.", chart(), duration_sec=4.6, data=y26_chart,
          transition_in="push_up"),
        S("s11", "cta", "So cooling doesn't mean cheap. Watch the price level, not just the rate.",
          Visual(type="motion_gfx", strategy="motion_gfx", scene_visual_type="abstract", motion="none",
                 decision_reason="authored: closing typography over dimmed licensed footage"), duration_sec=4.4),
    ]
    meta = SceneMeta(
        video_id=VIDEO_ID, channel_id=CHANNEL, niche="usa_finance",
        title="Inflation Is Cooling… So Why Is Everything Still So Expensive?",
        hook="Inflation is cooling. So why is everything still so expensive?",
        description=("Inflation fell from 9.1% (June 2022) to about 3%, but the price LEVEL never reset: "
                     "CPI is up about 31% since January 2020. Data: U.S. Bureau of Labor Statistics CPI-U (not seasonally adjusted)."),
        tags=["inflation", "CPI", "cost of living", "BLS", "prices", "US economy"],
        hashtags=["#inflation", "#CPI", "#economy", "#shorts"], thumbnail_text="COOLING ≠ CHEAP".replace("≠", "IS NOT"),
        structure_id="one_number_story")
    return SceneGraph(meta=meta, scenes=scenes, audio=AudioTrack(), brand_id=BRAND, fps=30, width=1080, height=1920)


def prepare_footage(graph, f: dict) -> None:
    """Trim + crop each real clip to 1080x1920/30fps at its scene length with a slow push-in."""
    out = WORK / "prepared"
    out.mkdir(exist_ok=True)
    for sc in graph.scenes:
        if sc.id not in FOOTAGE:
            continue
        name, start = FOOTAGE[sc.id]
        src = WORK / "footage" / name
        dur = sc.duration_sec
        dst = out / f"{sc.id}.mp4"
        zoom = f"1+0.07*t/{max(dur, 0.1):.3f}"
        vf = (f"scale=w='ceil(1080*({zoom})/2)*2':h='ceil(1920*({zoom})/2)*2':eval=frame:force_original_aspect_ratio=increase,"
              f"crop=1080:1920,fps=30,setsar=1")
        # Landscape sources: pre-scale to cover 1920 height first so the push-in has resolution.
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", f"{dur + 0.2:.3f}", "-i", str(src),
                        "-vf", vf, "-t", f"{dur:.3f}", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                        "-pix_fmt", "yuv420p", str(dst)], check=True)
        sc.visual.asset_path = str(dst)



def closing_plate(theme, dst: Path, dur: float, footage: Path, start: float) -> Path:
    """Big animated type over the dimmed real clip (hook-style 'rate vs level' sign-off)."""
    tdir = WORK / "graphics"
    lines = [("COOLING", 175, "ink", 0.15, 480), ("ISN\u2019T", 175, "ink", 0.45, 665), ("CHEAP.", 175, "warn", 0.75, 850),
             ("WATCH THE PRICE LEVEL,", 58, "secondary", 1.45, 1135), ("NOT JUST THE RATE.", 58, "secondary", 1.7, 1215)]
    chain = ["scale=w='ceil(1080*(1+0.05*t/%.2f)/2)*2':h='ceil(1920*(1+0.05*t/%.2f)/2)*2':eval=frame:force_original_aspect_ratio=increase" % (dur, dur),
             "crop=1080:1920", "fps=30", "gblur=sigma=5", "eq=brightness=-0.22:saturation=0.55",
             f"drawbox=x=0:y=0:w=iw:h=ih:color={theme.hex('bg', '#081525')}@0.62:t=fill"]
    for i, (text, size, role, t0, y) in enumerate(lines):
        tf = tdir / f"close_{i}.txt"
        tf.write_text(text, encoding="utf-8")
        font = theme.display.path if size > 100 else theme.body.path
        a = f"if(lt(t,{t0}),0,min(1,(t-{t0})/0.35))"
        chain.append(f"drawtext=fontfile='{font}':textfile='{tf}':fontsize={size}:fontcolor={theme.hex(role, '#FFFFFF')}:"
                     f"x=(w-text_w)/2:y='{y}+(1-min(1,max(0,(t-{t0})/0.35)))*36':alpha='{a}':shadowx=3:shadowy=3:shadowcolor=black@0.6")
    chain.append(f"drawbox=x=(iw-420)/2:y=1085:w='420*min(1,max(0,(t-1.2)/0.5))':h=5:color={theme.hex('primary', '#A78BFA')}:t=fill")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", f"{dur + 0.2:.3f}", "-i", str(footage),
                    "-vf", ",".join(chain), "-t", f"{dur:.3f}", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-pix_fmt", "yuv420p", str(dst)], check=True)
    return dst


def fix_dropped_audio(graph, raw: str) -> None:
    """render_ffmpeg._finish loses ~12 s of audio (the AAC bus drops frames while the heavy video graph runs).

    The same audio filters, run on their own, are complete -- so rebuild the mix from the job's filter_complex.txt
    and remux it under the rendered video.
    """
    import re
    job = Path(raw).parent
    parts = (job / "filter_complex.txt").read_text().split(";")
    aud = [p for p in parts if re.match(r"\[\d+:a\]", p) or p.startswith(("[mus0]", "[vo]", "[amix]"))]
    first = min(int(re.match(r"\[(\d+):a\]", p).group(1)) for p in aud if re.match(r"\[\d+:a\]", p))
    renum = lambda p: re.sub(r"\[(\d+):a\]", lambda m: f"[{int(m.group(1)) - first}:a]", p)
    a = graph.audio
    files = [a.voiceover_path, a.music_path] + [str(ROOT / "data" / "assets" / "sfx" / f"{c.sound}.wav") for c in graph.sfx]
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for i, f in enumerate(files):
        cmd += (["-stream_loop", "-1", "-t", f"{graph.total_duration_sec:.3f}"] if i == 1 else []) + ["-i", f]
    (job / "audio_mix_fc.txt").write_text(";".join(renum(p) for p in aud))
    mix = job / "audio_mix.wav"
    subprocess.run(cmd + ["-filter_complex_script", str(job / "audio_mix_fc.txt"), "-map", "[a]", "-ar", "48000", "-t",
                          f"{graph.total_duration_sec:.3f}", str(mix)], check=True)
    fixed = job / "raw_fixed.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-i", str(mix), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-t", f"{graph.total_duration_sec:.3f}", str(fixed)], check=True)
    fixed.replace(raw)
    mix.unlink()


async def render_graphics(graph) -> None:
    from app.brand import load_theme
    from app.pipeline import dataviz, motiongfx
    theme = load_theme(BRAND)
    gdir = WORK / "graphics"
    gdir.mkdir(exist_ok=True)
    for sc in graph.scenes:
        if sc.visual.type == "dataviz":
            p = await dataviz.render(sc.data, theme, gdir / f"{sc.id}_chart.mp4", graph.width, graph.height, graph.fps, sc.duration_sec)
            sc.visual.asset_path = str(p)
        elif sc.visual.type == "motion_gfx":
            sc.visual.asset_path = str(closing_plate(theme, gdir / f"{sc.id}_close.mp4", sc.duration_sec,
                                                     WORK / "footage" / "pexels_8960334.mp4", 1.0))


def aligned_captions(graph, theme):
    """Word timings from the actual voice audio (no whisper binary on this machine).

    captions.transcribe() falls back to spreading each scene's words evenly over the whole clip, which drifts
    against the pauses.  Here we detect real speech segments per scene clip with ffmpeg silencedetect and place
    words along the speech-only timeline in proportion to their letter count.
    """
    import re
    from app.pipeline import captions as C
    from app.schemas.scene import Caption
    job = Path(graph.audio.voiceover_path).parent
    caps, t0 = [], 0.0
    for i, sc in enumerate(graph.scenes):
        clip = job / f"scene_{i:02d}.wav"
        err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(clip), "-af", "silencedetect=noise=-36dB:d=0.10", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
        ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
        dur, segs, cur = sc.duration_sec, [], 0.0
        for a, b in zip(starts, ends + [dur] * (len(starts) - len(ends))):
            if a - cur > 0.04:
                segs.append((cur, min(a, dur)))
            cur = max(cur, b)
        if dur - cur > 0.04:
            segs.append((cur, dur))
        if not segs:
            segs = [(0.0, dur)]
        total = sum(b - a for a, b in segs)

        def at(x: float) -> float:           # speech-timeline position -> clip time
            for a, b in segs:
                if x <= b - a + 1e-9:
                    return a + x
                x -= b - a
            return segs[-1][1]

        words = sc.narration.split()
        wt = [max(2, len(re.sub(r"[^A-Za-z0-9]", "", w))) + (2 if re.search(r"[.?!:]$", w) else 0) for w in words]
        acc, wtimes = 0.0, []
        for w, x in zip(words, wt):
            wtimes.append((w, t0 + at(total * acc / sum(wt)), t0 + at(total * (acc + x - (2 if re.search(r"[.?!:]$", w) else 0)) / sum(wt))))
            acc += x
        for k in range(0, len(wtimes), C.MAX_WORDS_PER_CAPTION):
            ch = wtimes[k:k + C.MAX_WORDS_PER_CAPTION]
            caps.append(Caption(start=round(ch[0][1], 3), end=round(ch[-1][2], 3), text=" ".join(w for w, _, _ in ch),
                                words=[{"w": w, "s": round(a, 3), "e": round(b, 3)} for w, a, b in ch]))
        t0 += dur
    return C._fit_to_safe_width(caps, theme, graph.width, graph.height)


async def run(check_only: bool) -> None:
    f = facts()
    print("[facts] " + json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in f.items()
                                   if not isinstance(v, list)}, indent=1))
    graph = build(f)
    words = sum(len(s.narration.split()) for s in graph.scenes)
    print(f"[script] {len(graph.scenes)} scenes, {words} spoken words")
    for s in graph.scenes:
        print(f"  {s.id} {s.visual.type:10} {s.narration}")
    if check_only:
        return

    from app.brand import load_theme
    from app.config import load_channel
    from app.director import structures
    from app.pipeline import captions, compliance, music, postprocess, render, sfx, tts, variety
    from app.schemas.video_spec import Niche, VideoSpec

    channel = load_channel(CHANNEL)
    spec = VideoSpec(channel_id=CHANNEL, niche=Niche("usa_finance"), topic="Inflation is cooling, so why is everything still so expensive?")
    spec.id = VIDEO_ID if hasattr(spec, "id") else VIDEO_ID
    choice = structures.choose(spec.id, CHANNEL, "usa_finance", forced=graph.meta.structure_id, record=False)
    plan = variety.plan(spec.id, CHANNEL, load_theme(BRAND), choice)
    variety.apply(graph, plan)
    graph.variety["grade"] = "neutral_doc"             # keep the Aurora navy true; warm/cool grades shift the palette
    graph.variety["caption_animation"] = "keyword_flash"
    print(f"[variety] {plan.summary()}")

    graph = await tts.synthesize(graph, spec, channel)          # real durations
    print(f"[tts] total {graph.total_duration_sec:.2f}s")
    prepare_footage(graph, f)
    await render_graphics(graph)
    graph = await captions.transcribe(graph, load_theme(BRAND))
    graph.captions = aligned_captions(graph, load_theme(BRAND))
    graph = await music.add_music(graph, channel, family=plan.music_family)
    graph = await sfx.add_sound_design(graph)
    before = [s.narration for s in graph.scenes]
    print("[compliance] " + compliance.apply(graph, strict=False).format().replace("\n", "\n[compliance] "))
    assert before == [s.narration for s in graph.scenes], "compliance rewrote narration after voicing"
    (WORK / "scene_graph_final.json").write_text(graph.model_dump_json(indent=1))
    raw = await render.render_remotion(graph)
    fix_dropped_audio(graph, raw)
    final = await postprocess.finalize(graph, raw, channel)
    print("MP4:", final["mp4"])
    print("THUMB:", final["thumbnail"])


if __name__ == "__main__":
    asyncio.run(run("--check" in sys.argv))
