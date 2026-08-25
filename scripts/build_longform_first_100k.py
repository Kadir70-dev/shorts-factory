#!/usr/bin/env python3
"""K70 LONG-FORM -- "Why Your First $100,000 Is the Hardest -- And What
Happens After". Voxel-first visual identity (frozen MB-Lab humans not
used). ~50% voxel character storytelling, ~25% real stock footage,
~15% procedural/3D environments, ~10% charts.

    .venv-win/Scripts/python.exe scripts/build_longform_first_100k.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "data" / "series" / "k70_longform" / "first_100k"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# vis types:
#   stock              -- real footage (existing, unchanged)
#   chart               -- dataviz (existing, unchanged)
#   procedural_city     -- reused static render (existing, unchanged)
#   voxel_story         -- static voxel object render (existing, unchanged)
#   voxel_human_still   -- single-frame voxel character render, ken-burns (new)
#   voxel_human_clip    -- short animated voxel character loop, no ken-burns (new)

BEATS = [
    ("s0", "voxel_human_clip",
     "Why does money seem to grow faster once you cross one hundred thousand dollars?",
     {"scene": "apartment", "role": "john", "anim": "idle", "rotation_z_deg": -15}),
    ("s1", "stock",
     "It's not magic. It's math -- and understanding it can change how you save for the rest of your life.",
     {"search_terms": ["american city skyline morning", "downtown financial district"]}),

    ("s2", "voxel_human_still",
     "Meet John. He's twenty-seven, works a normal job, and like most people, saving money never quite feels like it's working.",
     {"scene": "apartment", "role": "john", "anim": "idle", "rotation_z_deg": -20}),
    ("s3", "stock",
     "The paycheck comes in. The bills go out -- rent, groceries, the usual list.",
     {"search_terms": ["person paying bills at home", "commuters walking city street"]}),
    ("s4", "voxel_human_still",
     "After everything, there's not much left over. Some months, almost nothing at all.",
     {"scene": "apartment", "role": "john", "anim": "idle", "rotation_z_deg": 15}),
    ("s5", "chart",
     "This is where most people start -- and where a lot of people stay stuck.",
     {"data": {"kind": "bar_compare", "title": "John's monthly budget",
               "points": [{"label": "Income", "value": 3400.0, "emphasis": "normal"},
                          {"label": "Expenses", "value": 3350.0, "emphasis": "primary"},
                          {"label": "Left to save", "value": 50.0, "emphasis": "normal"}],
               "prefix": "$", "decimals": 0, "abbreviate": False, "highlight": 2,
               "note": "Illustrative example"}}),

    ("s6", "voxel_story",
     "So why does saving the very first bit of money feel so much harder than the rest?",
     {"object_type": "bank"}),
    ("s7", "voxel_human_clip",
     "The math is simple: if income barely covers expenses, there's nothing left over. Every dollar is already spoken for before it arrives.",
     {"scene": "apartment", "role": "john", "anim": "point", "rotation_z_deg": 0}),

    ("s8", "voxel_human_clip",
     "So John does something small. He trims one expense, and puts the difference aside -- fifty dollars a paycheck.",
     {"scene": "apartment", "role": "john", "anim": "point", "rotation_z_deg": -10}),
    ("s9", "voxel_story",
     "It's not much. But for the first time, it isn't zero.",
     {"object_type": "dollar"}),
    ("s10", "stock",
     "Weeks turn into months. The habit matters more than the amount.",
     {"search_terms": ["time lapse city calendar days passing", "person working at desk time lapse"]}),

    ("s11", "chart",
     "Ten thousand dollars. Still not life-changing on its own. But it's real, and it's his.",
     {"data": {"kind": "bar_compare", "title": "John's savings so far",
               "points": [{"label": "Month 1", "value": 50.0, "emphasis": "normal"},
                          {"label": "Month 12", "value": 1000.0, "emphasis": "normal"},
                          {"label": "Year 3", "value": 10000.0, "emphasis": "primary"}],
               "prefix": "$", "decimals": 0, "abbreviate": False, "highlight": 2,
               "note": "Hypothetical example, consistent monthly saving"}}),

    ("s12", "voxel_human_still",
     "Sarah's story looks a little different, but the shape of it is the same.",
     {"scene": "apartment", "role": "sarah", "anim": "idle", "rotation_z_deg": -20}),
    ("s13", "stock",
     "A household budget, a family to plan around, and the same basic question: what's actually left at the end of the month?",
     {"search_terms": ["family at home budgeting", "parent and child kitchen table"]}),

    ("s14", "voxel_human_clip",
     "A banker put it simply: the first ten or twenty thousand dollars is the hardest, because you're building the habit before you see the reward.",
     {"scene": "office", "roles": [{"role": "john", "anim": "idle", "location": [-0.55, -0.6, 0], "rotation_z_deg": 10},
                                    {"role": "banker", "anim": "point", "location": [0.5, 1.5, 0], "rotation_z_deg": 200}]}),
    ("s15", "voxel_human_still",
     "There's no interest check coming yet. No compounding doing the work for you. It's just discipline, showing up month after month.",
     {"scene": "office", "roles": [{"role": "john", "anim": "idle", "location": [-0.55, -0.6, 0], "rotation_z_deg": 10},
                                    {"role": "banker", "anim": "idle", "location": [0.5, 1.5, 0], "rotation_z_deg": 200}]}),

    ("s16", "chart",
     "Twenty-five thousand dollars in. The number is bigger now -- but the feeling of slow progress often hasn't changed much.",
     {"data": {"kind": "bar_compare", "title": "The long middle stretch",
               "points": [{"label": "Year 3", "value": 10000.0, "emphasis": "normal"},
                          {"label": "Year 5", "value": 25000.0, "emphasis": "primary"},
                          {"label": "Year 7", "value": 50000.0, "emphasis": "normal"}],
               "prefix": "$", "decimals": 0, "abbreviate": False, "highlight": 1,
               "note": "Hypothetical example, consistent monthly saving"}}),

    ("s17", "procedural_city",
     "Zoom out, and this same story is happening across an entire economy -- millions of people, at every stage of it.",
     {}),
    ("s18", "stock",
     "Markets moving, businesses growing, paychecks landing every two weeks in every direction.",
     {"search_terms": ["stock market trading floor", "business district people walking"]}),

    ("s19", "voxel_human_still",
     "This is an investor -- someone thinking less about saving the next dollar, and more about what money can start doing on its own.",
     {"scene": "office", "role": "investor", "anim": "idle", "rotation_z_deg": -15}),
    ("s20", "voxel_human_clip",
     "Because somewhere past that first big milestone, something genuinely changes: the money you already have starts helping earn the next dollar.",
     {"scene": "office", "role": "investor", "anim": "point", "rotation_z_deg": -10}),

    ("s21", "chart",
     "Here's a simple, hypothetical example. Assume a seven percent average annual return -- a common long-run historical stock market estimate, never guaranteed.",
     {"data": {"kind": "bar_compare", "title": "Same 7% return, different starting amounts (hypothetical)",
               "points": [{"label": "$10,000 earns", "value": 700.0, "emphasis": "normal"},
                          {"label": "$100,000 earns", "value": 7000.0, "emphasis": "primary"}],
               "prefix": "$", "decimals": 0, "abbreviate": False, "highlight": 1,
               "note": "Illustrative only -- returns are never guaranteed"}}),
    ("s22", "voxel_human_clip",
     "Same percentage. Seven times the dollars. That's the entire secret behind why a bigger principal starts to feel like it's working harder for you.",
     {"scene": "office", "role": "investor", "anim": "point", "rotation_z_deg": 0}),

    ("s23", "voxel_story",
     "It's not that the math changes at one hundred thousand dollars. It's that compounding needs a real base to work with -- and now there's one.",
     {"object_type": "bank"}),
    ("s24", "stock",
     "None of this happens overnight, and none of it is guaranteed. Markets go up and down, and past growth never promises future growth.",
     {"search_terms": ["economy business finance abstract", "city financial district evening"]}),

    ("s25", "voxel_human_still",
     "But the pattern holds for almost everyone who gets there: the first hundred thousand is mostly about behavior. What comes after leans more on math.",
     {"scene": "apartment", "role": "john", "anim": "idle", "rotation_z_deg": 15}),
    ("s26", "voxel_human_clip",
     "John isn't rich. He's not done. But he's not stuck at zero anymore, either -- and that's the part that was actually hard.",
     {"scene": "house", "role": "john", "anim": "idle", "rotation_z_deg": -25}),
    ("s27", "stock",
     "Wherever you're starting from, the first step is the same one John took: find the number that isn't zero, and protect it.",
     {"search_terms": ["sunrise over american suburb", "family in front of home"]}),
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
        "video_id": "k70_longform_first_100k", "channel_id": "k70_finance",
        "niche": "personal_finance",
        "title": "Why Your First $100,000 Is the Hardest (And What Happens After)",
        "hook": "Why does money seem to grow faster after the first $100K?",
        "structure_id": "k70_longform_first_100k",
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
