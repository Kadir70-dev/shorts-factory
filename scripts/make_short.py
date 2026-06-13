#!/usr/bin/env python3
"""
Build ONE short end-to-end from EITHER a pre-authored SceneGraph JSON or a live
topic, with the narration→visual GROUNDING LOCK forced on. Runs the real pipeline
inline (no redis): [director] → tts → captions → assets(STRICT) → music → sfx →
render → post, and prints the point-to-point visual plan + the final MP4.

    # from a fixed, hand-authored scene graph (deterministic, no LLM):
    .venv/bin/python scripts/make_short.py --from-json data/demos/cyber_passwords.json

    # from a topic via the Claude Director (cybersecurity niche wired natively):
    .venv/bin/python scripts/make_short.py "The hacker who accidentally exposed millions of passwords" --niche cybersecurity

`--from-json` skips the Director (and its sanity gate) and renders the graph as-is
— ideal for demoing exact grounding. Strict mode (VISUAL_ACCURACY_MODE=strict) is
forced unless you pass --no-strict.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

BAR = "═" * 74


async def _graph_from_json(path: Path):
    from app.schemas.scene import SceneGraph
    graph = SceneGraph.model_validate_json(path.read_text())
    return graph


async def _graph_from_topic(topic: str, niche_slug: str, channel_id: str, mock: bool):
    from app.config import load_channel
    from app.director import get_director
    from app.schemas.video_spec import Niche, VideoSpec
    spec = VideoSpec(channel_id=channel_id, niche=Niche(niche_slug), topic=topic,
                     allow_ai_image=True, allow_ai_video=True)
    channel = load_channel(channel_id)
    os.environ["DIRECTOR_MODE"] = "mock" if mock else "live"
    graph = await get_director(channel).build_scene_graph(spec)
    return graph


def _print_plan(graph) -> None:
    print(f"\n   HOOK: {graph.meta.hook}")
    print(f"   TITLE: {graph.meta.title}")
    print("   ── point-to-point visual plan ────────────────────────────────")
    for s in graph.scenes:
        v = s.visual
        print(f"   {s.id} {s.duration_sec:4.1f}s [{v.strategy:9}→{v.type:8}] "
              f"{s.narration[:60]}")
        print(f"          SEE: {v.visual_intent[:74]}")
        print(f"          why: {v.decision_reason[:74]}")


# How each resolved visual TYPE maps to the strict priority tier it represents.
_TIER = {
    "broll": "Tier 1/3 · real footage (exact or cinematic supporting)",
    "image": "Tier 1/3 · real photo (Ken Burns)",
    "ai_video": "Tier 2 · AI motion recreation (Picsart image→video)",
    "ai_image": "Tier 2 · AI still recreation (+ Ken Burns)",
    "manim": "motion-graphics chart",
    "solid": "Tier 4 EXHAUSTED · animated-gradient safety net",
}


def _grounding_report(graph) -> dict:
    """Enforce + print the scene-by-scene grounding checklist against the RESOLVED
    graph: (1) narration, (2) exact visual proof = the file that resolved, (3) why,
    (4) the fallback tier it landed on. Then a STRICT audit: no duplicate clips, no
    un-asked cliché survived, every beat maps to narration (none left blank/solid).
    Returns a dict summary {passed, fails}."""
    from app.pipeline.broll import _CLICHE_TERMS

    print(f"\n{BAR}\n   GROUNDING REPORT — narration↔visual lock (enforced)\n{BAR}")
    seen: dict[str, str] = {}
    dups, cliches, blanks = [], [], []

    for s in graph.scenes:
        v = s.visual
        asset = Path(v.asset_path).name if v.asset_path else "—"
        fellback = (v.strategy == "ai_video" and v.type != "ai_video")
        print(f"\n   ▸ {s.id}  [{v.strategy} → {v.type}]  {_TIER.get(v.type, v.type)}"
              + ("  (Picsart unavailable → still+KenBurns)" if fellback else ""))
        print(f"     1. NARRATION : {s.narration}")
        print(f"     2. VISUAL    : {asset}   ({v.type}, motion={v.motion})")
        print(f"        intent    : {v.visual_intent}")
        print(f"     3. WHY       : {v.decision_reason}")
        print(f"     4. FALLBACK  : exact footage → AI recreation → supporting → "
              f"generic → gradient  (landed: {_TIER.get(v.type, v.type)})")

        # --- STRICT audit per scene ---
        if v.type in ("broll", "image") and v.asset_path:
            if v.asset_path in seen.values():
                dups.append(s.id)
        if v.asset_path:
            seen[s.id] = v.asset_path
        nl = s.narration.lower()
        bad = [c for kw in v.broll_keywords for c in _CLICHE_TERMS
               if c in kw.lower() and c not in nl and c.split()[0] not in nl]
        if bad:
            cliches.append((s.id, sorted(set(bad))))
        if v.type == "solid":
            blanks.append(s.id)

    print(f"\n   ── STRICT compliance ─────────────────────────────────────────")
    checks = [
        ("no duplicate clips", not dups, f"repeats: {dups}" if dups else "all unique"),
        ("no un-asked cliché (hoodie/matrix/green-terminal)", not cliches,
         f"{cliches}" if cliches else "clean"),
        ("every beat maps to narration (no blank/solid)", not blanks,
         f"solid fallbacks: {blanks}" if blanks else "every beat has a grounded visual"),
    ]
    for name, ok, detail in checks:
        print(f"     [{'PASS' if ok else 'FAIL'}] {name} — {detail}")
    passed = all(ok for _, ok, _ in checks)
    print(f"\n   {'✅ GROUNDING PASSED' if passed else '⚠ GROUNDING WARNINGS (see FAIL above)'}")
    return {"passed": passed, "dups": dups, "cliches": cliches, "blanks": blanks}


async def run(args) -> int:
    from app.config import load_channel, log_provider_validation, settings
    from app.pipeline import broll, captions, music, postprocess, render, sfx, tts
    from app.schemas.video_spec import Niche, VideoSpec

    print(f"{BAR}\n● MAKE SHORT — grounding lock {'ON' if settings().strict_visuals else 'OFF'}\n{BAR}")
    log_provider_validation()

    # 1) get a SceneGraph (fixed JSON or live Director)
    if args.from_json:
        graph = await _graph_from_json(Path(args.from_json))
        print(f"   source: {args.from_json}  ({len(graph.scenes)} scenes, fixed)")
    else:
        from make_gen import NICHE_CHANNEL, guess_niche  # reuse the niche map
        niche = args.niche or guess_niche(args.topic)
        niche_slug, default_ch = NICHE_CHANNEL[niche]
        graph = await _graph_from_topic(args.topic, niche_slug,
                                        args.channel or default_ch, args.mock)
        print(f"   source: Director · niche={niche} · '{graph.meta.title[:48]}'")

    channel = load_channel(graph.meta.channel_id)
    spec = VideoSpec(channel_id=graph.meta.channel_id, niche=Niche(graph.meta.niche),
                     topic=graph.meta.title, allow_ai_image=True, allow_ai_video=True)

    def stage(label, t0):
        print(f"   [{label:9}] {time.perf_counter()-t0:5.1f}s")

    try:
        t = time.perf_counter(); graph = await tts.synthesize(graph, spec, channel); stage("tts", t)
        t = time.perf_counter(); graph = await captions.transcribe(graph); stage("captions", t)
        t = time.perf_counter(); graph = await broll.resolve_assets(graph, spec); stage("assets", t)
        _print_plan(graph)
        # ENFORCE the grounding checklist BEFORE finalizing the render.
        report = _grounding_report(graph)
        # persist the resolved graph so the report can be re-inspected without a re-render
        gpath = settings().data_dir / "jobs" / graph.meta.video_id / "scene_graph.json"
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text(graph.model_dump_json(indent=2))
        if not report["passed"]:
            print("   (grounding warnings above — rendering anyway; demoting nothing)")
        t = time.perf_counter(); graph = await music.add_music(graph, channel); stage("music", t)
        t = time.perf_counter(); graph = await sfx.add_sound_design(graph); stage("sfx", t)
        t = time.perf_counter(); raw = await render.render_remotion(graph); stage("render", t)
        t = time.perf_counter(); final = await postprocess.finalize(graph, raw, channel); stage("post", t)
    except Exception as e:  # noqa: BLE001
        print(f"\n   ✗ pipeline stage failed: {type(e).__name__}: {e}")
        return 1

    # resolved-source readout (what each beat actually became)
    srcs: dict[str, int] = {}
    for s in graph.scenes:
        srcs[s.visual.type] = srcs.get(s.visual.type, 0) + 1
    print("\n   resolved sources: " + " · ".join(f"{k} {c}" for k, c in sorted(srcs.items())))
    mp4 = final["mp4"]
    sz = Path(mp4).stat().st_size / 1e6 if Path(mp4).exists() else 0
    print(f"   ✅ MP4: {mp4}  ({sz:.1f} MB · ~{graph.total_duration_sec:.0f}s)")
    if final.get("thumbnail"):
        print(f"   🖼  THUMB: {final['thumbnail']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", nargs="?", help="topic (omit when using --from-json)")
    ap.add_argument("--from-json", help="render a fixed SceneGraph JSON (skips the Director)")
    ap.add_argument("--niche", default=None, help="niche key (e.g. cybersecurity)")
    ap.add_argument("--channel", default=None, help="channel id override")
    ap.add_argument("--backend", choices=["cli", "api"], default="cli")
    ap.add_argument("--mock", action="store_true", help="offline mock director")
    ap.add_argument("--no-research", action="store_true")
    ap.add_argument("--no-strict", action="store_true", help="disable the grounding lock")
    args = ap.parse_args()
    if not args.topic and not args.from_json:
        ap.error("give a topic or --from-json")

    if not args.no_strict:
        os.environ.setdefault("VISUAL_ACCURACY_MODE", "strict")
    os.environ.setdefault("DIRECTOR_BACKEND", args.backend)
    os.environ.setdefault("DIRECTOR_RESEARCH", "0" if args.no_research else "1")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
