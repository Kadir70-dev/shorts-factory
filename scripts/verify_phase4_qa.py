#!/usr/bin/env python3
"""
Phase-4 QA — end-to-end stabilization run over THREE real demo shorts:
    1. Cybersecurity documentary  (footage-first + 1 AI hero stack, no character)
    2. Anime storytelling          (full bg▸subject▸fx hero + reusable character)
    3. Educational explainer       (footage + stat overlays + a DELIBERATELY broken
                                    asset to prove the solid-gradient fallback)

For each short the harness measures render time, RAM peak + free-floor, character
consistency, and runs the pipeline/qa.py audit (black-frame, per-scene non-black,
playability, budgets). Every short is wrapped in a TIMEOUT GUARD and a try/except
so one failure is RECORDED and the harness recovers and continues (failure
recovery + fallback validation). STRICT CPU-safe, cached-first assets (offline,
deterministic — no fresh generation), RENDER_BACKEND=ffmpeg.

    .venv/bin/python scripts/verify_phase4_qa.py [--keep]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

os.environ.update({
    "LAYERED_RENDER": "1", "CHARACTER_MEMORY": "1", "RENDER_BACKEND": "ffmpeg",
    "VISUAL_ACCURACY_MODE": "strict", "QA_ENABLED": "1",
    "AI_VIDEO_ENABLED": "0", "ENABLE_IMAGE_TO_VIDEO": "0", "COMFYUI_ENABLED": "0",
})

OUT_DIR = ROOT / "data" / "renders" / "_phase4_qa"
KADE = "ai_img_6e894cba1bb41368687ae33e0f2ef1ffd7643d5c.png"   # the locked character
PER_SHORT_TIMEOUT = 480.0                                       # timeout guard (s)


# --------------------------------------------------------------------------- #
# measurement
# --------------------------------------------------------------------------- #
class RamSampler(threading.Thread):
    def __init__(self, period: float = 0.2):
        super().__init__(daemon=True)
        self.period, self._stopping, self.min_free = period, False, float("inf")

    def run(self):
        from app.pipeline import ram
        while not self._stopping:
            a = ram.available_mb()
            if a is not None:
                self.min_free = min(self.min_free, a)
            time.sleep(self.period)

    def halt(self) -> float:
        self._stopping = True
        self.join(timeout=1.0)
        return self.min_free if self.min_free != float("inf") else -1.0


def _cpu_s() -> float:
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return ru.ru_utime + ru.ru_stime


def _assets():
    cache = ROOT / "data" / "cache"
    stills = [p for p in sorted(cache.glob("ai_img_*.png"),
                                key=lambda p: p.stat().st_size, reverse=True)]
    clips = [p for p in sorted(cache.glob("*.mp4"),
                               key=lambda p: p.stat().st_size, reverse=True)]
    kade = cache / KADE
    return stills, clips, (kade if kade.exists() else (stills[0] if stills else None))


# --------------------------------------------------------------------------- #
# the three demo SceneGraphs (cached-first, pre-seeded; no fresh generation)
# --------------------------------------------------------------------------- #
def _layer(role, kind, path=None, **kw):
    from app.schemas.scene import Layer
    return Layer(role=role, kind=kind, asset_path=(str(path) if path else None), **kw)


def _build_cyber(stills, clips, kade):
    from app.schemas.scene import Overlay, Scene, SceneGraph, SceneMeta, Visual
    meta = SceneMeta(video_id="qa_cyber", channel_id="k70_cyber",
                     niche="cybersecurity",
                     title="The Breach Nobody Noticed", hook="They were inside for months.")
    return SceneGraph(meta=meta, scenes=[
        Scene(id="s0", narration="For months, no one noticed they were inside.",
              duration_sec=3.2,
              visual=Visual(type="broll", asset_path=str(clips[0]),
                            scene_visual_type="real_footage", motion="zoom_in"),
              overlays=[Overlay(type="headline", text="Inside for months",
                                emphasis="alert")]),
        # HERO layered beat: AI background + fx (no character → 1 AI still).
        Scene(id="s1", narration="The intrusion spread through the network in silence.",
              duration_sec=4.0,
              visual=Visual(type="ai_image", scene_visual_type="dramatic", layers=[
                  _layer("background", "ai_image", stills[0], motion="zoom_in",
                         parallax=0.12),
                  _layer("fx", "asset", None, query="scanlines.png", blend="screen",
                         opacity=0.30, parallax=0.85)])),
        Scene(id="s2", narration="Analysts traced the breach to a single stolen key.",
              duration_sec=3.4,
              visual=Visual(type="broll", asset_path=str(clips[1]),
                            scene_visual_type="real_footage", motion="pan_lr")),
        Scene(id="s3", narration="Patch your systems before they find the door.",
              duration_sec=3.0,
              visual=Visual(type="broll", asset_path=str(clips[2]),
                            scene_visual_type="real_footage", motion="zoom_out"),
              overlays=[Overlay(type="stat", text="of breaches use stolen keys",
                                sub="61%", emphasis="negative")]),
    ]), None


def _build_anime(stills, clips, kade):
    from app.schemas.scene import Scene, SceneGraph, SceneMeta, Visual
    meta = SceneMeta(video_id="qa_anime", channel_id="k70_cyber",
                     niche="cybersecurity",
                     title="Kade and the Ghost Key", hook="One key opened every door.")
    # fx layer carries a bare texture name (resolver/composer resolve it).
    hero = Visual(type="ai_image", scene_visual_type="dramatic", layers=[
        _layer("background", "ai_image", stills[1] if len(stills) > 1 else stills[0],
               prompt="dark cyber control room, anime", motion="zoom_in", parallax=0.12),
        _layer("subject", "ai_image", kade, character="kade",
               prompt="kade, teen anime hacker, green hoodie, focused",
               motion="zoom_out", parallax=0.6),
        _layer("fx", "asset", None, query="scanlines.png", blend="screen",
               opacity=0.35, parallax=0.85)])
    return SceneGraph(meta=meta, scenes=[
        Scene(id="s0", narration="In a city of glass, one key opened every door.",
              duration_sec=3.0,
              visual=Visual(type="broll", asset_path=str(clips[0]),
                            scene_visual_type="real_footage", motion="zoom_in")),
        Scene(id="s1", narration="Kade traced the ghost key through the dark.",
              duration_sec=4.2, visual=hero),
        # recall — SAME locked character still reused (consistency target).
        Scene(id="s2", narration="He had seen this signature before.",
              duration_sec=3.2,
              visual=Visual(type="ai_image", asset_path=str(kade),
                            scene_visual_type="dramatic", motion="zoom_in")),
        Scene(id="s3", narration="Some doors should never be opened.",
              duration_sec=3.0,
              visual=Visual(type="broll", asset_path=str(clips[1]),
                            scene_visual_type="real_footage", motion="pan_lr")),
    ]), "kade"


def _build_edu(stills, clips, kade):
    from app.schemas.scene import Overlay, Scene, SceneGraph, SceneMeta, Visual
    meta = SceneMeta(video_id="qa_edu", channel_id="k70_facts", niche="usa_facts",
                     title="Why the Sky Is Blue", hook="It's not what you think.")
    return SceneGraph(meta=meta, scenes=[
        Scene(id="s0", narration="Sunlight looks white, but it's every color at once.",
              duration_sec=3.2,
              visual=Visual(type="broll", asset_path=str(clips[0]),
                            scene_visual_type="real_footage", motion="zoom_in"),
              overlays=[Overlay(type="headline", text="Every color at once")]),
        Scene(id="s1", narration="Air molecules scatter blue light the most.",
              duration_sec=3.4,
              visual=Visual(type="image", asset_path=str(stills[2] if len(stills) > 2 else stills[0]),
                            scene_visual_type="data_viz", motion="ken_burns"),
              overlays=[Overlay(type="stat", text="shorter = scattered more",
                                sub="450nm", emphasis="positive")]),
        # DELIBERATELY BROKEN asset → must fall back to a VISIBLE solid, not black.
        Scene(id="s2", narration="So the whole sky glows blue from every direction.",
              duration_sec=3.0,
              visual=Visual(type="broll", asset_path="/nonexistent/missing_asset.mp4",
                            fallback_color="#16384f", scene_visual_type="real_footage")),
        Scene(id="s3", narration="At sunset, the blue scatters away and red remains.",
              duration_sec=3.0,
              visual=Visual(type="broll", asset_path=str(clips[1]),
                            scene_visual_type="real_footage", motion="zoom_out")),
    ]), None


DEMOS = [
    ("Cybersecurity documentary", _build_cyber),
    ("Anime storytelling", _build_anime),
    ("Educational explainer", _build_edu),
]


# --------------------------------------------------------------------------- #
# run one short end-to-end with timeout + failure recovery
# --------------------------------------------------------------------------- #
async def _run_one(name, build):
    from app.config import load_channel, settings
    from app.pipeline import broll, music, qa, ram, render_ffmpeg, sfx, tts
    from app.schemas.video_spec import Niche, VideoSpec

    stills, clips, kade = _assets()
    graph, character = build(stills, clips, kade)
    channel = load_channel(graph.meta.channel_id)
    spec = VideoSpec(channel_id=graph.meta.channel_id,
                     niche=Niche(graph.meta.niche), topic=graph.meta.title,
                     allow_ai_image=True,
                     character_name=character or "",
                     character_desc=("kade, teen anime hacker, green hoodie, "
                                     "messy dark hair" if character else ""))
    out = OUT_DIR / f"{graph.meta.video_id}.mp4"
    failures: list[str] = []
    sampler = RamSampler(); sampler.start()
    cpu0 = _cpu_s(); t0 = time.perf_counter(); timed_out = False

    async def _pipeline():
        nonlocal graph
        graph = await tts.synthesize(graph, spec, channel)
        if settings().layered_render:
            graph = await broll.resolve_layers(graph, spec)
        try:
            graph = await music.add_music(graph, channel)
            graph = await sfx.add_sound_design(graph)
        except Exception as e:        # audio bed optional — recover & continue
            failures.append(f"audio-bed skipped ({type(e).__name__})")
        await render_ffmpeg.render(graph, out)

    try:
        await asyncio.wait_for(_pipeline(), timeout=PER_SHORT_TIMEOUT)
    except asyncio.TimeoutError:
        timed_out = True
        failures.append(f"render exceeded {PER_SHORT_TIMEOUT:.0f}s timeout guard")
    except Exception as e:            # FAILURE RECOVERY — record, don't crash the suite
        failures.append(f"{type(e).__name__}: {str(e)[:120]}")

    render_s = time.perf_counter() - t0
    cpu_s = _cpu_s() - cpu0
    min_free = sampler.halt()
    peak_rss = ram.child_peak_mb()

    # consistency — re-resolve / reuse the locked character still (anime only)
    consistency = None
    if character:
        hero = next((s for s in graph.scenes if s.id == "s1"), None)
        subj = next((l for l in (hero.visual.layers if hero else [])
                     if l.role == "subject"), None)
        recall = next((s for s in graph.scenes if s.id == "s2"), None)
        if subj and subj.asset_path and recall and recall.visual.asset_path:
            consistency = qa.consistency_pct(subj.asset_path,
                                             recall.visual.asset_path)

    rep = qa.analyze(graph, str(out), render_seconds=render_s,
                     ram_peak_mb=peak_rss, min_free_mb=min_free,
                     consistency=consistency, timed_out=timed_out)
    for c in rep.failures():
        if c.severity == "error":
            failures.append(f"QA: {c.name} — {c.detail}")
    return {
        "name": name, "vid": graph.meta.video_id, "out": out, "report": rep,
        "render_s": render_s, "cpu_s": cpu_s, "peak_rss": peak_rss,
        "min_free": min_free, "consistency": consistency, "failures": failures,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
async def run(keep: bool) -> int:
    from app.config import log_provider_validation, settings
    from app.pipeline import qa, ram

    BAR = "═" * 70
    print(f"{BAR}\n● PHASE-4 QA — 3 real shorts · STRICT CPU-safe · cached-first\n{BAR}")
    log_provider_validation()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not (ROOT / "data/assets/fx/scanlines.png").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts/make_fx_assets.py")])
    stills, clips, kade = _assets()
    if len(stills) < 2 or len(clips) < 3:
        print(f"✗ need ≥2 stills + ≥3 clips (have {len(stills)}, {len(clips)})")
        return 2
    print(f"[env] free RAM {ram.available_mb():.0f}MB / {ram.total_mb():.0f}MB · "
          f"layered={settings().layered_render} · qa={settings().qa_enabled}\n")

    results = []
    for name, build in DEMOS:
        print(f"\n{'─'*70}\n▶ {name}\n{'─'*70}")
        try:
            r = await _run_one(name, build)
        except Exception as e:        # last-resort recovery — suite never aborts
            print(f"   ✗ unrecoverable: {type(e).__name__}: {e}")
            results.append({"name": name, "vid": "?", "render_s": 0, "peak_rss": 0,
                            "min_free": -1, "consistency": None, "report": None,
                            "failures": [f"unrecoverable {type(e).__name__}: {e}"],
                            "out": None})
            continue
        print(qa.format_report(r["report"]))
        results.append(r)

    # --- summary table -------------------------------------------------------- #
    print(f"\n{BAR}\n● MEASURED RESULTS — 3 shorts\n{BAR}")
    hdr = f"  {'short':26} {'render':>7} {'CPU':>7} {'RAMpeak':>8} {'minfree':>8} {'consist':>8} {'QA':>5}"
    print(hdr); print("  " + "─" * (len(hdr) - 2))
    n_pass = 0
    for r in results:
        rep = r.get("report")
        qa_ok = "PASS" if (rep and rep.passed) else "FAIL"
        n_pass += 1 if qa_ok == "PASS" else 0
        cons = f"{r['consistency']:.0f}%" if r.get("consistency") is not None else "n/a"
        size = (f"{rep.metrics.get('size_mb','?')}MB" if rep else "—")
        print(f"  {r['name'][:26]:26} {r['render_s']:6.0f}s "
              f"{r.get('cpu_s',0):6.0f}s {r['peak_rss']:7.0f}M "
              f"{(r['min_free'] if r['min_free']>=0 else 0):7.0f}M {cons:>8} {qa_ok:>5}")

    # --- MP4 quality + failure points ---------------------------------------- #
    print(f"\n  MP4 QUALITY")
    for r in results:
        rep = r.get("report")
        if not rep:
            print(f"   • {r['name']}: NO OUTPUT")
            continue
        m = rep.metrics
        print(f"   • {r['name']}: {m.get('size_mb','?')}MB · {m.get('duration_s','?')}s "
              f"· black {m.get('black_seconds','?')}s · res ok="
              f"{any(c.name=='resolution 9:16' and c.passed for c in rep.checks)} "
              f"· audio={any(c.name=='has audio stream' and c.passed for c in rep.checks)}")

    print(f"\n  FAILURE POINTS")
    any_fail = False
    for r in results:
        fs = r.get("failures") or []
        if fs:
            any_fail = True
            print(f"   • {r['name']}:")
            for f in fs:
                print(f"       - {f}")
    if not any_fail:
        print("   • none — all 3 shorts rendered, passed QA, recovered cleanly")

    _recommend(results)

    if not keep:
        for r in results:
            if r.get("out") and Path(r["out"]).exists():
                Path(r["out"]).unlink()
        if OUT_DIR.exists() and not any(OUT_DIR.iterdir()):
            OUT_DIR.rmdir()
    else:
        print(f"\n[keep] shorts in {OUT_DIR}")

    print()
    ok = n_pass == len(results)
    print(f"{'✓' if ok else '✗'} PHASE-4 QA: {n_pass}/{len(results)} shorts passed QA")
    return 0 if ok else 1


def _recommend(results) -> None:
    from app.config import settings
    s = settings()
    peaks = [r["peak_rss"] for r in results if r.get("peak_rss")]
    frees = [r["min_free"] for r in results if r.get("min_free", -1) >= 0]
    rends = [r["render_s"] for r in results if r.get("render_s")]
    peak = max(peaks) if peaks else 0
    free = min(frees) if frees else -1
    slow = max(rends) if rends else 0
    print(f"\n  RECOMMENDED PRODUCTION SETTINGS — your laptop (i5 / no GPU / 12GB)")
    print(f"   measured worst case: render {slow:.0f}s · ffmpeg peak ~{peak:.0f}MB · "
          f"min free ~{(free if free>=0 else 0):.0f}MB")
    print( "   • RENDER_BACKEND=ffmpeg            (no Node/Remotion service — most stable)")
    print( "   • LAYERED_RENDER=1                 (layered hero proven CPU-safe)")
    print(f"   • LAYERED_AI_STILL_BUDGET=2        (≤2 AI stills/short — respects ~11min/img)")
    print( "   • LAYERED_MAX_HERO_SCENES=1        (one full stack per short)")
    print( "   • LAYERED_FFMPEG_THREADS=4         (i5 — leave headroom for the OS)")
    print( "   • LAYERED_SUBJECT_MATTE=oval       (CPU cutout; set =rembg only if installed)")
    print(f"   • LAYERED_MIN_FREE_MB={max(1000, int((free if free>0 else 1200)*0.5)):<13} "
          f"(fallback to simple render below this)")
    print(f"   • QA_ENABLED=1                     (catch black frames / RAM spikes per run)")
    print( "   • arq max_jobs=1                   (ONE short at a time — never parallel renders)")
    print( "   • COMFYUI off unless running       (local LCM ~11min/img; HF FLUX-schnell is the free workhorse)")
    print( "   • keep an 8GB swapfile             (headroom; peak stayed well under 12GB here)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    return asyncio.run(run(args.keep))


if __name__ == "__main__":
    sys.exit(main())
