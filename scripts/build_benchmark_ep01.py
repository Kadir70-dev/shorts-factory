#!/usr/bin/env python3
"""K70 SCENE ENGINE -- INTERNAL BENCHMARK (production-fix brief section 13).

NOT a public long-form video. A short (~50s) internal test that the six
K70 scene-engine repos, now individually fixed and tested this session,
work TOGETHER in one story: John earns $5,000/month, wants a house,
visits a bank, learns interest rates change affordability, and inflation
is raising his everyday costs -- so he has to decide what he can
realistically spend.

Emits scene_graph.json + asset_plan.json into
data/series/k70_benchmark/ep01/, same authoring pattern as
build_mortgage_ep01.py, read by scripts/produce_benchmark_ep01.py.

    .venv-win/Scripts/python.exe scripts/build_benchmark_ep01.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "k70_benchmark" / "ep01"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Each beat: (id, vis, narration, extra asset_plan fields)
BEATS = [
    ("s0", "stock",
     "John earns five thousand dollars a month, and like a lot of people, "
     "he's wondering how much house that actually buys him.",
     {"search_terms": ["young professional reviewing finances at home",
                       "person using calculator laptop budgeting"]}),
    ("s1", "environment",
     "He's been eyeing a house in a neighborhood he likes -- the kind of "
     "place he imagines actually settling down in.",
     {"character": "john", "character_angle": "three_quarter", "environment": "house"}),
    ("s2", "stock",
     "So John visits the bank to find out what he can actually afford.",
     {"search_terms": ["bank exterior daylight", "financial district building"]}),
    ("s3", "environment",
     "The loan officer explains that the interest rate on his loan changes "
     "how much home he can afford.",
     {"character": "john", "character_angle": "three_quarter", "environment": "bank"}),
    ("s4", "chart",
     "Even a small difference in rate adds up over thirty years of payments.",
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
    ("s5", "stock",
     "Meanwhile, inflation has been quietly raising some of his everyday "
     "expenses too.",
     {"search_terms": ["grocery store shopping prices", "family budget rising costs"]}),
    ("s6", "voxel_story",
     "That means less of his paycheck is actually free for a mortgage "
     "payment than it used to be.",
     {"object_type": "dollar"}),
    ("s7", "procedural_city",
     "Zoom out, and John is just one buyer in a housing market shaped by "
     "thousands of decisions just like his.",
     {}),
    ("s8", "character",
     "So John has to decide -- realistically -- how much he can actually "
     "spend.",
     {"character": "john", "character_angle": "front"}),
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
        "video_id": "k70_benchmark_ep01", "channel_id": "k70_finance",
        "niche": "personal_finance",
        "title": "K70 SCENE ENGINE -- INTERNAL BENCHMARK (not for publication)",
        "hook": "How much house can John actually afford?",
        "structure_id": "k70_internal_benchmark",
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
