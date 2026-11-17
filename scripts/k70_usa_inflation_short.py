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
        # type "dataviz" = prerendered by scripts/k70_motion.py (real footage + live graphics layer): the renderer keeps
        # captions on and skips its own overlays
        return Visual(type="dataviz", strategy="real", scene_visual_type="real_footage", motion="none",
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
          Visual(type="dataviz", strategy="motion_gfx", scene_visual_type="abstract", motion="none", query="pexels_8960334.mp4",
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



def _keys(a: tuple[int, int], b: tuple[int, int]) -> list[str]:
    out, (y, m) = [], a
    while (y, m) <= b:
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def render_v2(graph, f: dict, theme) -> Path:
    """Render every scene with the K70 motion engine (real graded footage + live graphics), concat -> silent.mp4."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import k70_motion as M
    d = load_series()
    allc = d["CUUR0000SA0"]
    pal = {k: M.rgb(theme.palette[v]) for k, v in dict(bg="bg", ink="ink", dim="ink_dim", primary="primary", secondary="secondary",
                                                       gold="warn", red="negative", green="positive").items()}
    pal["glow"] = pal["primary"]
    FOOT = WORK / "footage"
    OUT = WORK / "scenes_v2"
    OUT.mkdir(exist_ok=True)
    SRCU = "SOURCE: U.S. BUREAU OF LABOR STATISTICS · CPI-U, NOT SEASONALLY ADJUSTED"
    mname = lambda key: label(key).upper()

    k_a = _keys((2021, 1), (2023, 6))
    v_a = [yoy(allc, k) if k in allc and f"{int(k[:4]) - 1}-{k[5:]}" in allc else None for k in k_a]
    k_b = _keys((2020, 1), (2026, 9))
    v_b = [allc.get(k) for k in k_b]
    k_c = _keys((2026, 1), (2026, 9))
    v_c = [yoy(allc, k) for k in k_c]
    base = allc[BASE]
    assert k_a.index("2022-06") == 17 and v_b.count(None) == 1 and round(v_a[17], 1) == 9.1

    def chart_a():
        return M.Chart(pal, "U.S. inflation rate, year over year", v_a, [(0.0, 0), (2.45, 17), (4.1, len(v_a) - 1)],
                       {0: "Jan 2021", 12: "Jan 2022", 24: "Jan 2023"}, [0, 3, 6, 9], 0, 10.4, lambda v: f"{v:.0f}%",
                       lambda val, h: (f"{val:.1f}%", f"{mname(k_a[int(round(h))])} · year over year"), SRCU,
                       callouts=[(17, "PEAK 9.1%", "June 2022", pal["red"], 2.5)], pill_fmt=lambda v: f"{v:.1f}%")

    def chart_b():
        return M.Chart(pal, "Consumer price level · CPI-U (1982-84 = 100)", v_b, [(0.15, 0), (3.0, len(v_b) - 1)],
                       {0: "Jan 2020", 24: "Jan 2022", 48: "Jan 2024", 80: "Sep 2026"}, [250, 275, 300, 325], 245, 345,
                       lambda v: f"{v:.0f}", lambda val, h: (f"+{(val / base - 1) * 100:.1f}%", "price level since Jan 2020"), SRCU,
                       pill_fmt=lambda v: f"{v:.1f}", line_cols=(pal["primary"], pal["secondary"]))

    def chart_c():
        return M.Chart(pal, "U.S. inflation rate in 2026, year over year", v_c, [(0.1, 0), (2.0, 8)],
                       {i: k_c[i][5:].replace("01", "Jan").replace("02", "Feb").replace("03", "Mar").replace("04", "Apr").replace("05", "May")
                        .replace("06", "Jun").replace("07", "Jul").replace("08", "Aug").replace("09", "Sep") for i in range(9)},
                       [0, 1, 2, 3, 4], 0, 5.0, lambda v: f"{v:.0f}%",
                       lambda val, h: (f"{val:.1f}%", f"{mname(k_c[int(round(h))])} · year over year"), SRCU,
                       callouts=[(0, "JAN 2.4%", "start of 2026", pal["gold"], 3.2)], pill_fmt=lambda v: f"{v:.1f}%")

    ink, gold, cyan, vio = pal["ink"], pal["gold"], pal["secondary"], pal["primary"]
    srcs = "SOURCE: BLS · CPI-U (NSA) · JAN 2020 TO SEP 2026"

    def stat_scene(val, label_, sub=""):
        def ov(t):
            L = M.base_layer(t, True)
            M.stat(L, t, pal, val, "+", "%", label_, sub, "up", y=400, count=0.8)
            M.source_line(L, srcs, t, 0.4, y=1395, pal=pal)
            M.add_flash(L, t)
            return L
        return ov

    def head_scene(blocks, size=118, align="left", y0=270, first=False):
        """blocks = [(t_start, t_end, [(text, colour, t_in)])]"""
        def ov(t):
            L = M.base_layer(t, True)
            for a, b, lines in blocks:
                if a <= t < b:
                    M.headline(L, lines, t - a, pal, size=size, y0=y0, align=align)
            if not first:
                M.add_flash(L, t)
            return L
        return ov

    def chart_scene(make):
        c = make()

        def ov(t):
            L = c.frame(t)
            M.add_flash(L, t, 0.22)
            return L
        return ov

    def closing(t):
        L = M.base_layer(t, True, shade=False)
        M.headline(L, [("COOLING", ink, 0.15), ("ISN'T", ink, 0.45), ("CHEAP.", gold, 0.8)], t, pal, size=196, y0=430, align="center")
        for txt, t0, y in (("WATCH THE PRICE LEVEL,", 1.55, 1180), ("NOT JUST THE RATE.", 1.8, 1250)):
            tile = M.text_tile(txt, str(M.BODY), 62, cyan, None, 0, 5, spacing=3)
            M.put(L, tile, M.W / 2, y + (1 - M.eo3((t - t0) / 0.4)) * 24, alpha=M.eo3((t - t0) / 0.4), anchor="cm")
        ln = int(M.lerp(0, 420, M.eo3((t - 1.4) / 0.5)))
        if ln > 2:
            M.ImageDraw.Draw(L).rectangle([M.W / 2 - ln / 2, 1128, M.W / 2 + ln / 2, 1133], fill=vio + (235,))
        M.add_flash(L, t)
        return L

    F = lambda n: FOOT / f"pexels_{n}.mp4"
    plan = {   # scene -> (mode, [(clip, start, share_of_scene)], overlay builder)
        "s1": ("plain", [(F(29369224), 0.0, 0.5), (F(8801848), 5.0, 0.5)],
               head_scene([(0, 99, [("INFLATION IS", ink, 0.10), ("COOLING.", ink, 0.38), ("PRICES", gold, 1.0), ("AREN'T.", gold, 1.22)])],
                          size=112, first=True)),
        "s2": ("chart", [(F(8799885), 8.0, 1.0)], chart_scene(chart_a)),
        "s2b": ("plain", [(F(8799885), 18.0, 1.0)],
                lambda t: _stat_down(M, pal, t, f["jun2023"])),
        "s3": ("plain", [(F(9046227), 0.5, 1.0)],
               head_scene([(0, 99, [("SLOWING", ink, 0.10), ("ISN'T", ink, 0.34), ("FALLING.", gold, 0.62)])], size=132)),
        "s4": ("plain", [(F(32536402), 1.0, 0.5), (F(32536402), 6.0, 0.5)],
               head_scene([(0, 2.2, [("INFLATION", cyan, 0.10), ("= SPEED", ink, 0.40)]),
                           (2.2, 99, [("PRICES", vio, 0.05), ("= DISTANCE", ink, 0.35)])], size=128)),
        "s5": ("chart", [(F(29576549), 6.0, 1.0)], chart_scene(chart_b)),
        "s6": ("plain", [(F(8801848), 1.5, 1.0)], stat_scene(round(f["food"]), "Food at home", "Jan 2020 to Sep 2026")),
        "s7": ("plain", [(F(8960335), 0.0, 1.0)], stat_scene(round(f["rent"]), "Rent", "Jan 2020 to Sep 2026")),
        "s8": ("plain", [(F(29576549), 2.0, 1.0)], stat_scene(round(f["gas"]), "Gasoline", "Jan 2020 to Sep 2026")),
        "s9": ("plain", [(F(8799885), 4.0, 0.5), (F(8541111), 2.0, 0.5)],
               head_scene([(0, 2.4, [("IT STACKS.", gold, 0.10)]), (2.4, 99, [("THE CLIMB", ink, 0.05), ("SLOWS.", cyan, 0.30)])], size=134)),
        "s10": ("chart", [(F(9046227), 6.0, 1.0)], chart_scene(chart_c)),
        "s11": ("chart", [(F(8960334), 1.0, 1.0)], closing),
    }
    cum, clips = 0.0, []
    for i, sc in enumerate(graph.scenes):
        mode, segs, ov = plan[sc.id]
        n = round((cum + sc.duration_sec) * 30) - round(cum * 30)
        total = n / 30
        seg_list, off = [], 0.0
        for k, (clip, start, share) in enumerate(segs):
            dur = total * share if k < len(segs) - 1 else total - off
            seg_list.append((clip, start, dur))
            off += dur
        out = OUT / f"{sc.id}.mp4"
        print(f"[motion] {sc.id} {n}f {mode}", flush=True)
        M.render_scene(out, n, seg_list, ov, mode, first_scene=(i == 0))
        clips.append(out)
        cum += sc.duration_sec
    lst = OUT / "scenes.txt"
    lst.write_text("\n".join(f"file '{c}'" for c in clips))
    silent = Path(graph.audio.voiceover_path).parents[1] / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True)
    return silent


def _stat_down(M, pal, t, value):
    L = M.base_layer(t, True)
    M.stat(L, t, pal, value, "", "%", "June 2023", "down from the 9.1% peak", "down", y=400, count=1.1, decimals=1, start=9.1)
    M.source_line(L, "SOURCE: BLS · CPI-U (NSA) · 12-MONTH CHANGE", t, 0.4, y=1395, pal=pal)
    M.add_flash(L, t)
    return L

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
    graph = await captions.transcribe(graph, load_theme(BRAND))
    graph.captions = aligned_captions(graph, load_theme(BRAND))
    graph = await music.add_music(graph, channel, family=plan.music_family)
    graph = await sfx.add_sound_design(graph)
    before = [s.narration for s in graph.scenes]
    print("[compliance] " + compliance.apply(graph, strict=False).format().replace("\n", "\n[compliance] "))
    assert before == [s.narration for s in graph.scenes], "compliance rewrote narration after voicing"
    (WORK / "scene_graph_final.json").write_text(graph.model_dump_json(indent=1))
    from app.brand import theme_for
    from app.pipeline import render_ffmpeg
    th = theme_for(graph, "compositor")
    th.intro["enabled"] = False                         # no brand stamp over the hook; the watermark stays
    work = Path(graph.audio.voiceover_path).parents[1]
    (work / "scene_graph.json").write_text(graph.model_dump_json())
    silent = render_v2(graph, f, load_theme(BRAND))
    raw = str(work / "raw.mp4")
    await render_ffmpeg._finish(graph, silent, Path(raw), th)
    fix_dropped_audio(graph, raw)
    final = await postprocess.finalize(graph, raw, channel)
    print("MP4:", final["mp4"])
    print("THUMB:", final["thumbnail"])


if __name__ == "__main__":
    asyncio.run(run("--check" in sys.argv))
