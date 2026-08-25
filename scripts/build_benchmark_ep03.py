#!/usr/bin/env python3
"""K70 PREMIUM SCENE ENGINE -- INTERNAL BENCHMARK EP03 (final character
production pass). NOT a public long-form video.

Builds on EP02's proven visual stack (MB-Lab characters, HDRI lighting,
camera presets, furnished office, Procgen city, fixed voxel house/bank)
and adds this pass's real, tested additions: a real walk-cycle animation
(MB-Lab's own walking.bvh, retargeted), real particle hair (not a
painted cap), a fixed eye-material bug, improved clothing coverage, and
all six recurring characters actually rendered (not just John+Banker).

    .venv-win/Scripts/python.exe scripts/build_benchmark_ep03.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "k70_premium_benchmark" / "ep03"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MBLAB_DIR = ROOT / "tools/k70_scene_engine/.test_renders/mblab_proof"
JOHN_CKPT = str(MBLAB_DIR / "john_m_ca01_posed.blend")
BANKER_CKPT = str(MBLAB_DIR / "banker_m_af01_posed.blend")
SARAH_CKPT = str(MBLAB_DIR / "sarah_f_ca01_posed.blend")

BEATS = [
    ("s0", "stock",
     "John is considering a five hundred thousand dollar house.",
     {"search_terms": ["american suburban house exterior daylight",
                       "suburban neighborhood street"]}),
    ("s1", "mblab_walk",
     "So he walks through the neighborhood to see it for himself.",
     {"role": "john", "checkpoint": JOHN_CKPT}),
    ("s2", "mblab_character",
     "Then he meets the banker, inside a properly furnished financial office.",
     {"role": "banker", "checkpoint": BANKER_CKPT, "lighting": "office_interior",
      "shot": "medium", "angle": "three_quarter", "office_environment": True}),
    ("s3", "chart",
     "The banker walks him through it: home price, down payment, and loan.",
     {"data": {
         "kind": "bar_compare", "title": "$500,000 home -- how it breaks down",
         "points": [
             {"label": "Home price", "value": 500000.0, "emphasis": "normal"},
             {"label": "Down payment (10%)", "value": 50000.0, "emphasis": "primary"},
             {"label": "Loan amount", "value": 450000.0, "emphasis": "normal"},
         ],
         "prefix": "$", "decimals": 0, "abbreviate": False, "highlight": 1,
         "note": "Illustrative example",
     }}),
    ("s4", "procedural_city",
     "Zoom out, and John's decision fits into a much wider economy.",
     {}),
    ("s5", "mblab_character",
     "Meanwhile, Sarah is having a similar conversation with her own paycheck, at her own workplace.",
     {"role": "sarah", "checkpoint": SARAH_CKPT, "lighting": "office_interior",
      "shot": "medium", "angle": "three_quarter", "office_environment": True}),
    ("s6", "voxel_story",
     "It comes down to the bank, the money, and the house.",
     {"object_type": "bank"}),
    ("s7", "voxel_story",
     "The money.",
     {"object_type": "dollar"}),
    ("s8", "voxel_story",
     "And John's house.",
     {"object_type": "house"}),
    ("s9", "mblab_character",
     "So John has to decide -- realistically -- how much he can actually spend.",
     {"role": "john", "checkpoint": JOHN_CKPT, "lighting": "portrait_studio",
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
        "video_id": "k70_premium_benchmark_ep03", "channel_id": "k70_finance",
        "niche": "personal_finance",
        "title": "K70 PREMIUM SCENE ENGINE -- INTERNAL BENCHMARK EP03 (not for publication)",
        "hook": "How much house can John actually afford?",
        "structure_id": "k70_premium_internal_benchmark_ep03",
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
