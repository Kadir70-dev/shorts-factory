#!/usr/bin/env python3
"""
Phase 5.5 verification — the Cinematic AI Visual Layer.

Runs the Smart Scene Decision Engine on the three reference topics and prints,
per scene: WHERE an AI image/video was inserted, WHY it was selected, the
resulting visual MIX vs the Phase-5.5 target, and a heuristic retention
projection (AI-layer ON vs forced-all-real). Then does ONE full MP4 render to
prove the pipeline end-to-end, with a stage-timed render readout.

    # decision dry-run on all 3 + one full render (history showcase, index 2):
    .venv/bin/python scripts/verify_visual_layer.py

    .venv/bin/python scripts/verify_visual_layer.py --render 0   # render topic 0
    .venv/bin/python scripts/verify_visual_layer.py --no-render  # decisions only
    .venv/bin/python scripts/verify_visual_layer.py --mock       # offline director

Live director uses the local `claude` CLI (Max plan). On any failure it falls
back to the offline mock director so the decision engine is always exercised.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

# (topic, niche_slug, channel_id)
TOPICS = [
    ("Why Americans tip everywhere", "usa_facts", "k70_facts"),
    ("Why swing states decide US elections", "usa_politics", "k70_politics"),
    ("The president who resigned in disgrace", "usa_history", "k70_history"),
]

BAR = "═" * 78


async def _build_graph(topic: str, niche_slug: str, channel_id: str, mock: bool):
    """Topic → SceneGraph via the Director (live CLI, mock fallback)."""
    from app.config import load_channel
    from app.director import get_director
    from app.schemas.video_spec import Niche, VideoSpec

    spec = VideoSpec(channel_id=channel_id, niche=Niche(niche_slug),
                     topic=topic, allow_ai_image=True, allow_ai_video=True)
    channel = load_channel(channel_id)
    os.environ["DIRECTOR_MODE"] = "mock" if mock else "live"
    try:
        graph = await get_director(channel).build_scene_graph(spec)
        return graph, spec, channel, ("mock" if mock else "live")
    except Exception as e:  # noqa: BLE001
        print(f"   ! live director failed ({type(e).__name__}: {str(e)[:80]}); "
              "using offline mock director")
        os.environ["DIRECTOR_MODE"] = "mock"
        from app.director.mock import MockDirector
        graph = await MockDirector(channel).build_scene_graph(spec)
        return graph, spec, channel, "mock-fallback"


def _retention_score(decisions) -> float:
    """Transparent HEURISTIC projection (NOT measured analytics — we have no
    watch-time data). Scored from the engine's DECISIONS, 0–100:
      • base 70           — every beat is intentional + always-moving here.
      • +18 × ai_served   — cinematic AI on eligible beats lifts production value.
      • +8  × gfx          — a clean animated chart beats a static number card.
      • −14 × mismatch    — a CONCEPT beat (abstract/history/etc.) left on literal
                            footage reads as generic stock → retention drag. This
                            is exactly what the AI-image slot removes.
    So turning the AI layer ON raises ai_served and removes mismatch — the delta
    is the projected lift from cinematic imagery on otherwise-unservable beats."""
    from app.pipeline import scene_director as sd
    n = len(decisions) or 1
    ai_served = sum(1 for d in decisions
                    if d.strategy in (sd.AI_IMAGE, sd.AI_VIDEO, sd.HYBRID)) / n
    gfx = sum(1 for d in decisions if d.strategy == sd.MOTION_GFX) / n
    mismatch = sum(1 for d in decisions
                   if d.ai_eligible and d.strategy == sd.REAL) / n
    return round(70 + 18 * ai_served + 8 * gfx - 14 * mismatch, 1)


def _mix(graph) -> dict[str, int]:
    ct: dict[str, int] = {}
    for s in graph.scenes:
        ct[s.visual.type] = ct.get(s.visual.type, 0) + 1
    return ct


def _print_decisions(graph) -> None:
    from app.pipeline import scene_director as sd
    n = len(graph.scenes) or 1
    sct: dict[str, int] = {}
    for s in graph.scenes:
        sct[s.visual.strategy] = sct.get(s.visual.strategy, 0) + 1
    print(f"   HOOK: {graph.meta.hook}")
    print("   ── per-scene decision ─────────────────────────────────────────")
    for s in graph.scenes:
        v = s.visual
        mark = "▶ AI" if v.strategy in (sd.AI_IMAGE, sd.AI_VIDEO, sd.HYBRID) \
            else ("▦ GFX" if v.strategy == sd.MOTION_GFX else "· real")
        print(f"   {mark:6} {s.id} [{v.strategy}]  {s.narration[:58]}")
        print(f"           why: {v.decision_reason}")
    mix = " · ".join(f"{k} {round(100*c/n)}%" for k, c in sorted(sct.items()))
    print(f"   ── strategy mix: {mix}")
    print("      target: real ~70% · Pika ai_video 15-20% · ai_image ~10% "
          "· gfx 5-10%")


async def _decisions_only(topic, niche, channel_id, mock):
    """Run the engine WITHOUT downloading assets, plus AI-on vs all-real retention."""
    from app.pipeline import scene_director as sd

    print(f"\n{BAR}\n▶ {topic}\n{BAR}")
    graph, spec, channel, mode = await _build_graph(topic, niche, channel_id, mock)
    print(f"   director: {mode} · niche {graph.meta.niche} · "
          f"{len(graph.scenes)} scenes · '{graph.meta.title[:54]}'")

    # AI layer ON
    rep_on = sd.decide(graph, spec)
    _print_decisions(graph)
    ret_on = _retention_score(rep_on.decisions)

    # baseline: force all-real (simulate the pre-5.5 engine) on a copy
    base = copy.deepcopy(graph)
    base_spec = copy.deepcopy(spec)
    base_spec.allow_ai_image = False
    base_spec.allow_ai_video = False
    rep_off = sd.decide(base, base_spec)
    ret_off = _retention_score(rep_off.decisions)

    ai_beats = [s.id for s in graph.scenes
                if s.visual.strategy in (sd.AI_IMAGE, sd.AI_VIDEO, sd.HYBRID)]
    print(f"   ── AI inserted on: {', '.join(ai_beats) or 'none'}")
    delta = round(ret_on - ret_off, 1)
    print(f"   ── retention projection (heuristic): all-real {ret_off} → "
          f"AI-layer {ret_on}  (Δ +{delta})" if delta >= 0 else
          f"   ── retention projection (heuristic): all-real {ret_off} → "
          f"AI-layer {ret_on}  (Δ {delta})")
    return graph, spec, channel


async def _full_render(topic, niche, channel_id, mock):
    """One full pipeline run → MP4, with a stage-timed readout and mix."""
    from app.pipeline import broll, captions, music, postprocess, render, sfx, tts

    print(f"\n{BAR}\n● FULL RENDER — {topic}\n{BAR}")
    graph, spec, channel, mode = await _build_graph(topic, niche, channel_id, mock)
    print(f"   director: {mode} · '{graph.meta.title[:54]}'")

    def stage(label, t0):
        print(f"   [{label:9}] {time.perf_counter()-t0:5.1f}s")

    t = time.perf_counter(); graph = await tts.synthesize(graph, spec, channel)
    stage("tts", t)
    t = time.perf_counter(); graph = await captions.transcribe(graph)
    stage("captions", t)
    t = time.perf_counter(); graph = await broll.resolve_assets(graph, spec)
    stage("assets", t)
    _print_decisions(graph)
    print(f"   resolved sources: " +
          " · ".join(f"{k} {c}" for k, c in sorted(_mix(graph).items())))
    t = time.perf_counter(); graph = await music.add_music(graph, channel)
    stage("music", t)
    t = time.perf_counter(); graph = await sfx.add_sound_design(graph)
    stage("sfx", t)
    t = time.perf_counter(); raw = await render.render_remotion(graph)
    stage("render", t)
    t = time.perf_counter(); final = await postprocess.finalize(graph, raw, channel)
    stage("post", t)

    from app.pipeline import scene_director as sd
    rep = sd.decide(graph, spec)              # deterministic; for the readout only
    gradients = sum(1 for s in graph.scenes if s.visual.type == "solid")
    print(f"   retention projection (heuristic): "
          f"{_retention_score(rep.decisions)}  · gradient fallbacks: {gradients}")
    print(f"   ✅ MP4: {final['mp4']}")
    sz = Path(final["mp4"]).stat().st_size if Path(final["mp4"]).exists() else 0
    print(f"      {sz/1e6:.1f} MB · ~{graph.total_duration_sec:.0f}s")


async def main_async(args):
    print("PHASE 5.5 — CINEMATIC AI VISUAL LAYER · verification")
    if not args.render_only:
        print("Smart Scene Decision Engine over the 3 reference topics.\n")
        for topic, niche, ch in TOPICS:
            await _decisions_only(topic, niche, ch, args.mock)

    if args.no_render:
        print(f"\n{BAR}\n(skipped full render: --no-render)\n{BAR}")
        return
    idx = args.render
    topic, niche, ch = TOPICS[idx]
    await _full_render(topic, niche, ch, args.mock)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", type=int, default=2,
                    help="index of the topic to fully render (default 2: history)")
    ap.add_argument("--no-render", action="store_true",
                    help="decisions only; no MP4")
    ap.add_argument("--mock", action="store_true",
                    help="use the offline mock director (no claude CLI)")
    ap.add_argument("--render-only", action="store_true",
                    help="skip the 3-topic dry-run; just render --render index")
    args = ap.parse_args()
    os.environ.setdefault("DIRECTOR_BACKEND", "cli")
    os.environ.setdefault("DIRECTOR_RESEARCH", "0")   # keep verification fast
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
