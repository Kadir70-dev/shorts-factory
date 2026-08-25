#!/usr/bin/env python3
"""K70 PREMIUM SCENE ENGINE -- INTERNAL BENCHMARK EP04.

Builds on EP03's proven visual stack and pipeline (same vis types:
mblab_walk, mblab_character, chart, procedural_city, voxel_story,
stock) with this pass's real fixes already baked into the shared
_mblab_character.py module: fixed eye materials (recursive emission/
transmission/IOR zeroing + corrected iris hue/saturation/value),
smooth-shaded garments, and closed hip/thigh clothing gaps. All six
recurring characters appear. Does NOT introduce new vis types or
engine code -- reuses exactly what EP03 already proved end-to-end.

    .venv-win/Scripts/python.exe scripts/build_benchmark_ep04.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "k70_premium_benchmark" / "ep04"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MBLAB_DIR = ROOT / "tools/k70_scene_engine/.test_renders/mblab_proof"
JOHN_CKPT = str(MBLAB_DIR / "john_m_ca01_posed.blend")
BANKER_CKPT = str(MBLAB_DIR / "banker_m_af01_posed.blend")
SARAH_CKPT = str(MBLAB_DIR / "sarah_f_ca01_posed.blend")
INVESTOR_CKPT = str(MBLAB_DIR / "investor_f_as01_posed.blend")
WORKER_CKPT = str(MBLAB_DIR / "worker_m_la01_posed.blend")
BUSINESS_OWNER_CKPT = str(MBLAB_DIR / "business_owner_f_af01_posed.blend")

BEATS = [
    ("s0", "stock",
     "This is John. Like a lot of people, he has been renting for years, watching prices "
     "climb every single spring.",
     {"search_terms": ["american suburban house exterior daylight",
                       "suburban neighborhood street"]}),
    ("s1", "mblab_walk",
     "Today he is walking through a neighborhood he actually likes, seriously asking himself "
     "whether a five hundred thousand dollar house is realistic for him.",
     {"role": "john", "checkpoint": JOHN_CKPT}),
    ("s2", "mblab_character",
     "So he sits down with a banker, inside a properly furnished financial office, to get real "
     "numbers instead of guesses.",
     {"role": "banker", "checkpoint": BANKER_CKPT, "lighting": "office_interior",
      "shot": "medium", "angle": "three_quarter", "office_environment": True}),
    ("s3", "chart",
     "The banker breaks it down clearly: the home price, the down payment John would need "
     "up front, and the loan amount that's actually left to pay off over time.",
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
    ("s4", "mblab_character",
     "An investor across town is weighing a very different kind of decision -- where to put "
     "capital this quarter, and how much risk actually makes sense right now.",
     {"role": "investor", "checkpoint": INVESTOR_CKPT, "lighting": "office_interior",
      "shot": "medium", "angle": "three_quarter", "office_environment": True}),
    ("s5", "procedural_city",
     "Zoom out far enough, and John's decision is really just one small piece of a much "
     "bigger, constantly moving economy.",
     {}),
    ("s6", "mblab_character",
     "Meanwhile Sarah is having her own version of this conversation, at her own workplace, "
     "with her own paycheck and her own budget.",
     {"role": "sarah", "checkpoint": SARAH_CKPT, "lighting": "office_interior",
      "shot": "medium", "angle": "three_quarter", "office_environment": True}),
    ("s7", "mblab_character",
     "So is a business owner deciding whether to reinvest profit back into the company or "
     "finally take some of it home.",
     {"role": "business_owner", "checkpoint": BUSINESS_OWNER_CKPT, "lighting": "office_interior",
      "shot": "medium", "angle": "three_quarter", "office_environment": True}),
    ("s8", "mblab_character",
     "And a worker clocking in for another shift is doing the exact same math on a much "
     "smaller number, which somehow makes it matter even more.",
     {"role": "worker", "checkpoint": WORKER_CKPT, "lighting": "portrait_studio",
      "shot": "medium", "angle": "three_quarter"}),
    ("s9", "voxel_story",
     "Underneath all of these different lives, the same three things keep showing up: "
     "the bank, the money, and the house.",
     {"object_type": "bank"}),
    ("s10", "voxel_story",
     "The money moving between them.",
     {"object_type": "dollar"}),
    ("s11", "voxel_story",
     "And the house at the other end of it.",
     {"object_type": "house"}),
    ("s12", "mblab_character",
     "Which brings John back to the real question -- not what a bank is willing to lend him, "
     "but what he can actually afford without it controlling his life.",
     {"role": "john", "checkpoint": JOHN_CKPT, "lighting": "portrait_studio",
      "shot": "medium", "angle": "front"}),
    ("s13", "stock",
     "That's the real decision behind every mortgage conversation -- not the biggest number "
     "you qualify for, but the one you can actually live with.",
     {"search_terms": ["family in front of new house happy",
                       "front door of a home key handoff"]}),
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
        "video_id": "k70_premium_benchmark_ep04", "channel_id": "k70_finance",
        "niche": "personal_finance",
        "title": "K70 PREMIUM SCENE ENGINE -- INTERNAL BENCHMARK EP04 (not for publication)",
        "hook": "How much house can John actually afford?",
        "structure_id": "k70_premium_internal_benchmark_ep04",
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
