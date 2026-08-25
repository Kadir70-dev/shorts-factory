#!/usr/bin/env python3
"""K70 VOXEL V5.2 -- Composition hard-veto + real depth + establishing-shot
gate + NPC palette separation, on top of V5.1's proven golden-hour system
and structural automation.

    .venv-win/Scripts/python.exe scripts/build_voxel_v52_visual_director.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/k70_scene_engine/director"))
from auto_scene_director import run_director_v3

JOB_DIR = ROOT / "data" / "jobs" / "k70_voxel_v52_visual_director"
V4_HERO = ROOT / "data/jobs/k70_voxel_v4_hero/hero_1080x1920.png"
V51_HERO = ROOT / "data/jobs/k70_voxel_v51_visual_director/final_hero.png"

SHOT_SPEC = {
    "shot_type": "city_walk",
    "hero": "john",
    "location": "financial_district",
    "time_of_day": "golden_hour",
    "mood": "optimistic",
    "density": "high",
    "camera": "medium_tracking",
    "story_focus": "john",
    "required_visible": ["john", "3_npcs", "2_vehicles", "storefront", "street_sign", "skyline"],
}


def main():
    t0 = time.time()
    print("K70 VOXEL V5.2 -- Composition Veto + Real Depth + Establishing-Shot Gate")
    result = run_director_v3(SHOT_SPEC, JOB_DIR, n_candidates=24, seed_base=5000,
                             top_visual=6, top_final=3, composition_veto_threshold=6.0)

    (JOB_DIR / "director_decisions.json").write_text(json.dumps({
        "shot_spec": result["spec"],
        "n_candidates_generated": result["n_candidates"],
        "n_structurally_rejected": result["n_structurally_rejected"],
        "n_structural_survivors": result["n_structural_survivors"],
        "n_composition_vetoed": result["n_composition_vetoed"],
        "n_visual_finalists": result["n_visual_finalists"],
        "structurally_rejected_summary": result["structurally_rejected_summary"],
        "composition_vetoed_summary": result["composition_vetoed_summary"],
        "top_final_seeds_and_scores": [{"seed": c["seed"], "total_score": c["score"]["total_score"],
                                        "categories": c["score"]["categories"]} for c in result["top_final"]],
        "winner_seed": result["winner_seed"],
        "winner_camera": result["winner_plan"]["camera"],
        "winner_score_breakdown": result["winner_score"],
        "manual_coordinate_adjustments_after_generation": 0,
        "manual_camera_adjustments": 0,
        "manual_lighting_adjustments": 0,
        "timings": result["timings"],
    }, indent=2), encoding="utf-8")

    (JOB_DIR / "candidate_scores.json").write_text(json.dumps(result["all_candidates"], indent=2), encoding="utf-8")

    from PIL import Image, ImageDraw
    from candidate_scorer import DEPTH_LAYER_BY_KIND

    final_img = Image.open(result["final_path"])
    target_h = 900
    def fit(im):
        w, h = im.size
        return im.resize((int(w * target_h / h), target_h))
    panels = [(fit(Image.open(V4_HERO)), "V4 (manual)"), (fit(Image.open(V51_HERO)), "V5.1"),
             (fit(final_img), "V5.2 (composition veto + real depth)")]
    total_w = sum(p[0].width for p in panels) + 30 * (len(panels) - 1)
    comp = Image.new("RGB", (total_w, target_h + 40), (12, 12, 15))
    cdraw = ImageDraw.Draw(comp)
    x = 0
    for im, label in panels:
        comp.paste(im, (x, 40))
        cdraw.text((x + 8, 10), label, fill=(255, 255, 255))
        x += im.width + 30
    comp.save(JOB_DIR / "comparison_sheet.jpg", quality=90)

    final_report = json.loads((JOB_DIR / "final_report.json").read_text(encoding="utf-8"))

    def _draw_debug(image_path, report, out_path):
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        draw = ImageDraw.Draw(img)
        colors = {"foreground": (255, 165, 0), "midground": (60, 230, 140), "background": (90, 160, 255)}
        for name, v in report["visibility"].items():
            if not v.get("in_frame"):
                continue
            xmin, ymin, xmax, ymax = v["screen_bbox"]
            px0, px1 = max(0, xmin * w), min(w, xmax * w)
            py0, py1 = max(0, (1 - ymax) * h), min(h, (1 - ymin) * h)
            layer = DEPTH_LAYER_BY_KIND.get(v.get("kind"), "background")
            color = colors.get(layer, (255, 255, 255))
            width = 5 if v.get("kind") == "hero" else 2
            draw.rectangle([px0, py0, px1, py1], outline=color, width=width)
            draw.text((px0 + 3, max(0, py0 + 3)), name, fill=color)
        for frac in (1 / 3, 2 / 3):
            draw.line([(frac * w, 0), (frac * w, h)], fill=(255, 255, 255), width=1)
            draw.line([(0, frac * h), (w, frac * h)], fill=(255, 255, 255), width=1)
        img.save(out_path, quality=92)

    _draw_debug(result["final_path"], final_report, JOB_DIR / "director_debug.png")

    metadata = {
        "title": "K70 Voxel V5.2 -- Composition Veto + Real Depth + Establishing-Shot Gate",
        "resolution": "1080x1920",
        "shot_spec": result["spec"],
        "winner_seed": result["winner_seed"],
        "n_candidates_generated": result["n_candidates"],
        "n_structurally_rejected": result["n_structurally_rejected"],
        "n_composition_vetoed": result["n_composition_vetoed"],
        "n_visual_finalists": result["n_visual_finalists"],
        "timings": result["timings"],
        "manual_coordinate_adjustments_after_generation": 0,
        "manual_camera_adjustments": 0,
        "manual_lighting_adjustments": 0,
        "files": {
            "final_hero": "final_hero.png", "comparison_sheet": "comparison_sheet.jpg",
            "director_debug": "director_debug.png (debug visualization only, not production output)",
            "director_decisions": "director_decisions.json", "candidate_scores": "candidate_scores.json",
        },
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    total_time = round(time.time() - t0, 1)
    print(f"\nWINNER: seed={result['winner_seed']} score={result['winner_score']['total_score']}")
    print(f"FINAL: {result['final_path']}")
    print(f"Structurally rejected {result['n_structurally_rejected']}/{result['n_candidates']}, "
         f"composition vetoed {result['n_composition_vetoed']}")
    print(f"Timings: {result['timings']}")
    print(f"Total driver time: {total_time}s")


if __name__ == "__main__":
    main()
