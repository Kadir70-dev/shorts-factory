#!/usr/bin/env python3
"""
Topic -> Claude Director -> real MP4. Phase 2 entrypoint.

    python make_gen.py "Why Americans are worried about inflation"
    python make_gen.py "How the electoral college actually works" --niche politics
    python make_gen.py "Why Americans tip everywhere" --niche facts
    python make_gen.py "The forgotten scandal that broke a president" --niche history
    python make_gen.py "How one company quietly became a monopoly" --niche business

Backends:
    --backend cli   (default)  uses the local `claude` CLI on your MAX plan
    --backend api              uses ANTHROPIC_API_KEY (Messages API)

Runs the full pipeline inline (no redis): research -> director -> tts ->
captions -> assets -> render -> post. Prints the timeline, metadata, and MP4.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

# K70 Network Solution buckets: friendly niche name -> (niche_slug, channel_id).
NICHE_CHANNEL = {
    "finance": ("usa_finance", "k70_economy"),
    "economy": ("usa_finance", "k70_economy"),
    "election": ("usa_politics", "k70_politics"),
    "politics": ("usa_politics", "k70_politics"),
    "facts": ("usa_facts", "k70_facts"),
    "history": ("usa_history", "k70_history"),
    "business": ("usa_business", "k70_business"),
    "cybersecurity": ("cybersecurity", "k70_cyber"),
    "cyber": ("cybersecurity", "k70_cyber"),
}

_KW = {
    "history": ["history", "dark history", "scandal", "forgotten", "weird law",
                "ancient", "war crime", "assassin", "conspiracy", "1800s", "century"],
    "business": ["billionaire", "company", "startup", "ceo", "ai ", "artificial intelligence",
                 "tech", "tesla", "apple", "google", "amazon", "bankrupt", "monopoly"],
    "facts": ["why americans", "why america", "why do americans", "tip", "healthcare",
              "why houses", "weird america", "hidden america", "how come"],
    "election": ["poll", "election", "ballot", "primary", "swing", "electoral", "vote", "campaign"],
    "politics": ["filibuster", "senate", "congress", "bill", "supreme court",
                 "impeach", "veto", "president", "how a", "explained"],
    "economy": ["inflation", "groceries", "broke", "middle class", "debt", "housing",
                "recession", "wages", "cost of living"],
    "cybersecurity": ["hacker", "hack", "breach", "data leak", "leaked", "password",
                      "phishing", "ransomware", "malware", "cyber", "dark web",
                      "exposed", "database", "credentials", "scam", "exploit"],
}


def guess_niche(topic: str) -> str:
    t = topic.lower()
    for niche, kws in _KW.items():
        if any(k in t for k in kws):
            return niche
    return "economy"


async def run(topic: str, niche: str, channel_id: str) -> None:
    from app.brand import load_theme
    from app.config import load_channel
    from app.director import get_director, structures
    from app.pipeline import (broll, captions, compliance, music, postprocess,
                              render, sfx, tts, variety)
    from app.schemas.video_spec import Niche, VideoSpec

    niche_enum = Niche(NICHE_CHANNEL[niche][0])     # friendly name -> slug -> enum
    # Phase 5.7: enable Pika cinematic AI-VIDEO inserts (capped + footage fallback).
    spec = VideoSpec(channel_id=channel_id, niche=niche_enum, topic=topic,
                     allow_ai_video=True)
    channel = load_channel(channel_id)

    print(f"\n[director] backend={os.getenv('DIRECTOR_BACKEND','cli')} "
          f"research={os.getenv('DIRECTOR_RESEARCH','1')} niche={niche}")
    print(f"[director] topic: {topic!r}  (this calls Claude — ~10-40s)")
    graph = await get_director(channel).build_scene_graph(spec)
    print(f"[director] OK — '{graph.meta.title}'")

    # Variety plan first: the visual engine, the music picker and the renderer all
    # read the same decisions, so it has to exist before any of them run.
    choice = structures.choose(spec.id, channel_id, niche_enum.value,
                               forced=graph.meta.structure_id, record=False)
    plan = variety.plan(spec.id, channel_id, load_theme(graph.brand_id or "k70"),
                        choice)
    variety.apply(graph, plan)
    print(f"[variety] {plan.summary()}")

    print("[tts] synthesizing voiceover in the channel's cloned voice…")
    graph = await tts.synthesize(graph, spec, channel)
    print("[captions] timing captions…")
    graph = await captions.transcribe(graph)
    print("[assets] visual ladder → resolving visuals…")
    graph = await broll.resolve_assets(graph, spec)
    _print_visual_mix(graph, spec)
    print("[music] scoring bed + beat-aware envelope…")
    graph = await music.add_music(graph, channel, family=plan.music_family)
    print(f"[music] mood: {graph.audio.music_mood} · "
          f"{len(graph.audio.music_envelope)} envelope keyframes")
    print("[sfx] designing retention sound cues…")
    graph = await sfx.add_sound_design(graph)
    print(f"[sfx] {len(graph.sfx)} cues: "
          f"{', '.join(sorted({c.role for c in graph.sfx})) or 'none'}")
    report = compliance.apply(graph, strict=False)
    print("[compliance] " + report.format().replace("\n", "\n[compliance] "))
    print("[render] building mp4…")
    raw = await render.render_remotion(graph)
    print("[post] finishing…")
    final = await postprocess.finalize(graph, raw, channel)

    print("\n=== SCRIPT ===")
    print(f"HOOK: {graph.meta.hook}")
    for s in graph.scenes:
        print(f"  {s.id} {s.duration_sec:4.1f}s [{s.visual.strategy:9}"
              f"→{s.visual.type:8}] {s.narration}")
    print(f"  total ~{graph.total_duration_sec:.1f}s · {len(graph.captions)} captions")
    print("\n=== METADATA ===")
    print(json.dumps(json.loads(final['metadata_json']), indent=2))
    print(f"\n✅ MP4:   {final['mp4']}")
    print(f"🖼  THUMB: {final['thumbnail']}")


def _print_visual_mix(graph, spec) -> None:
    """Phase-5.7 readout: the strategy the decision engine chose per scene, WHY,
    what finally resolved, the PIKA AI-video inserts (prompts + clip duration),
    the retention impact, and the final HYBRID mix percentages vs target."""
    from app.pipeline.broll import _ai_subject
    from app.pipeline.providers import build_video_prompt, clamp_insert_seconds

    n = len(graph.scenes) or 1
    strat_ct: dict[str, int] = {}
    type_ct: dict[str, int] = {}
    for s in graph.scenes:
        strat_ct[s.visual.strategy] = strat_ct.get(s.visual.strategy, 0) + 1
        type_ct[s.visual.type] = type_ct.get(s.visual.type, 0) + 1
    print("[visuals] per-scene decisions:")
    for s in graph.scenes:
        v = s.visual
        print(f"    {s.id} {v.strategy:9}→ {v.type:8} :: {v.decision_reason}")

    # --- PIKA AI-video readout ------------------------------------------------
    planned = [s for s in graph.scenes if s.visual.strategy == "ai_video"]
    resolved = [s for s in graph.scenes if s.visual.type == "ai_video"]
    print(f"[pika] cinematic AI-video inserts: {len(planned)} planned · "
          f"{len(resolved)} rendered as Pika "
          f"({len(planned) - len(resolved)} fell back to footage/image)")
    for s in planned:
        used = "✓ Pika clip" if s.visual.type == "ai_video" else \
               f"↳ fell back to {s.visual.type} (no PIKA_API_KEY or gen failed)"
        clip = clamp_insert_seconds(s.duration_sec)
        print(f"    {s.id} [{used}]  clip≈{clip:.0f}s")
        print(f"         prompt: {build_video_prompt(_ai_subject(s))[:140]}…")

    # --- final HYBRID mix vs Phase-5.7 target ---------------------------------
    mix = " · ".join(f"{k} {round(100*c/n)}%" for k, c in sorted(strat_ct.items()))
    print(f"[visuals] HYBRID strategy mix: {mix}")
    print(f"[visuals] resolved sources: " +
          " · ".join(f"{k} {c}" for k, c in sorted(type_ct.items())))
    real = type_ct.get("broll", 0) + type_ct.get("image", 0) + type_ct.get("solid", 0)
    vid = type_ct.get("ai_video", 0)
    img = type_ct.get("ai_image", 0)
    gfx = type_ct.get("manim", 0)
    print(f"[visuals] target real ~70% · Pika ai_video 15-20% · ai_image ~10% "
          f"· gfx 5-10%")
    print(f"[visuals] resolved ratio: real {round(100*real/n)}% · "
          f"pika {round(100*vid/n)}% · ai_image {round(100*img/n)}% · "
          f"gfx {round(100*gfx/n)}%")
    print(f"[visuals] retention impact (heuristic): {_retention(graph, spec)}")


def _retention(graph, spec) -> str:
    """AI-layer ON vs forced-all-real retention projection (heuristic, not measured
    analytics) — the lift from cinematic Pika/AI imagery on otherwise-unservable
    beats. Mirrors scripts/verify_visual_layer.py."""
    import copy
    from app.pipeline import scene_director as sd

    def score(decisions) -> float:
        m = len(decisions) or 1
        served = sum(1 for d in decisions
                     if d.strategy in (sd.AI_IMAGE, sd.AI_VIDEO, sd.HYBRID)) / m
        g = sum(1 for d in decisions if d.strategy == sd.MOTION_GFX) / m
        mismatch = sum(1 for d in decisions
                       if d.ai_eligible and d.strategy == sd.REAL) / m
        return round(70 + 18 * served + 8 * g - 14 * mismatch, 1)

    on = sd.decide(copy.deepcopy(graph), spec)
    base_spec = copy.deepcopy(spec)
    base_spec.allow_ai_video = False
    base_spec.allow_ai_image = False
    off = sd.decide(copy.deepcopy(graph), base_spec)
    s_on, s_off = score(on.decisions), score(off.decisions)
    return f"all-real {s_off} → hybrid {s_on}  (Δ {'+' if s_on >= s_off else ''}{round(s_on - s_off, 1)})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--niche", choices=list(NICHE_CHANNEL), default=None)
    ap.add_argument("--channel", default=None)
    ap.add_argument("--backend", choices=["cli", "api"], default="cli")
    ap.add_argument("--no-research", action="store_true")
    args = ap.parse_args()

    niche = args.niche or guess_niche(args.topic)
    channel_id = args.channel or NICHE_CHANNEL[niche][1]

    os.environ["DIRECTOR_MODE"] = "live"
    os.environ["DIRECTOR_BACKEND"] = args.backend
    os.environ["DIRECTOR_RESEARCH"] = "0" if args.no_research else "1"

    asyncio.run(run(args.topic, niche, channel_id))


if __name__ == "__main__":
    main()
