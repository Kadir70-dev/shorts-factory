#!/usr/bin/env python3
"""K70 PREMIUM SCENE ENGINE -- INTERNAL BENCHMARK EP02 (visual-engine
rebuild brief, Phase 13). NOT a public long-form video.

Same story as ep01 but built entirely on the rebuilt visual stack: real
MB-Lab humanoid characters (John + a genuinely different second
humanoid, the Banker) instead of the Gobkit mascot, a real furnished
office set instead of an empty floor, HDRI-based cinematic lighting, and
the new camera-shot presets, alongside the systems that were already
real and working (Procgen Maps city, the fixed voxel house/bank,
real broll footage, dataviz charts).

    .venv-win/Scripts/python.exe scripts/build_benchmark_ep02.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "k70_premium_benchmark" / "ep02"
OUT_DIR.mkdir(parents=True, exist_ok=True)

JOHN_CHECKPOINT = str(ROOT / "tools/k70_scene_engine/.test_renders/mblab_proof/john_m_ca01_posed.blend")
BANKER_CHECKPOINT = str(ROOT / "tools/k70_scene_engine/.test_renders/mblab_proof/banker_m_af01_posed.blend")

BEATS = [
    ("s0", "stock",
     "John earns five thousand dollars a month, and he's wondering how much house that "
     "actually buys him.",
     {"search_terms": ["bright modern home office desk daylight",
                       "person typing on laptop bright office window light"]}),
    ("s1", "mblab_character",
     "This is John.",
     {"role": "john", "checkpoint": JOHN_CHECKPOINT, "lighting": "portrait_studio",
      "shot": "medium", "angle": "three_quarter"}),
    ("s2", "stock",
     "He's considering a five hundred thousand dollar house, in a neighborhood he's had "
     "his eye on for a while.",
     {"search_terms": ["american suburban house exterior daylight",
                       "suburban neighborhood street"]}),
    ("s3", "procedural_building",
     "A real house, a real number, a real decision.",
     {"building_type": "house"}),
    ("s4", "mblab_character",
     "So John meets a banker, in a properly dressed financial office, to find out what he "
     "can actually afford.",
     {"role": "banker", "checkpoint": BANKER_CHECKPOINT, "lighting": "office_interior",
      "shot": "medium", "angle": "three_quarter", "office_environment": True}),
    ("s5", "chart",
     "The banker explains that the interest rate on his loan changes how much home he can "
     "afford -- even a small difference adds up over thirty years.",
     {"data": {
         "kind": "bar_compare", "title": "Est. monthly payment by rate (same loan)",
         "points": [
             {"label": "6.0% rate", "value": 2398.0, "emphasis": "normal"},
             {"label": "7.0% rate", "value": 2661.0, "emphasis": "primary"},
             {"label": "8.0% rate", "value": 2935.0, "emphasis": "normal"},
         ],
         "prefix": "$", "decimals": 0, "abbreviate": False, "highlight": 1,
         "note": "Illustrative example, same $400,000 loan amount",
     }}),
    ("s6", "stock",
     "Zoom out, and John is just one buyer in a housing market shaped by thousands of "
     "decisions just like his.",
     {"search_terms": ["city skyline economy", "downtown financial district aerial"]}),
    ("s7", "procedural_city",
     "The wider economy John's decision fits into.",
     {}),
    ("s8", "voxel_story",
     "The bank.",
     {"object_type": "bank"}),
    ("s9", "voxel_story",
     "The money.",
     {"object_type": "dollar"}),
    ("s10", "voxel_story",
     "John's house.",
     {"object_type": "house"}),
    ("s11", "mblab_character",
     "So John has to decide -- realistically -- how much he can actually spend.",
     {"role": "john", "checkpoint": JOHN_CHECKPOINT, "lighting": "portrait_studio",
      "shot": "medium", "angle": "front"}),
]


def main() -> None:
    scenes = []
    asset_plan = []
    for sid, vis, narration, extra in BEATS:
        scenes.append({
            "id": sid, "narration": narration, "duration_sec": 5.0,
            "visual": {"type": "image", "motion": "ken_burns"},
            "data": extra.get("data"),
            "beat_role": "body",
        })
        plan_entry = {"scene_id": sid, "vis": vis}
        plan_entry.update({k: v for k, v in extra.items() if k != "data"})
        asset_plan.append(plan_entry)

    meta = {
        "video_id": "k70_premium_benchmark_ep02", "channel_id": "k70_finance",
        "niche": "personal_finance",
        "title": "K70 PREMIUM SCENE ENGINE -- INTERNAL BENCHMARK EP02 (not for publication)",
        "hook": "How much house can John actually afford?",
        "structure_id": "k70_premium_internal_benchmark",
    }
    graph = {
        "schema_version": "1.0", "meta": meta, "fps": 30, "width": 1920, "height": 1080,
        "scenes": scenes,
    }
    (OUT_DIR / "scene_graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    (OUT_DIR / "asset_plan.json").write_text(json.dumps(asset_plan, indent=2), encoding="utf-8")
    print(f"wrote {len(scenes)} scenes -> {OUT_DIR}")


if __name__ == "__main__":
    main()
