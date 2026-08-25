#!/usr/bin/env python3
"""K70 VOXEL V5.1 -- Premium cinematic composition selector.

Same shot spec V5 used (John, financial district, golden hour, 3+ NPCs,
2+ vehicles, storefront, signage, street props, vegetation, deep
skyline). V5 proved the AUTOMATION (structural gate, hard-reject,
candidate generation, zero manual coordinates) -- this run upgrades the
SELECTION quality on top of that unchanged automation, via
auto_scene_director.run_director_v2 (staged structural -> geometry-visual
-> lighting-visual -> medium-visual ranking, candidate_scorer.visual_score
for premium-composition scoring, and lighting_presets.setup_golden_hour_v2
for camera-relative golden-hour lighting).

    .venv-win/Scripts/python.exe scripts/build_voxel_v51_visual_director.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/k70_scene_engine/director"))
from auto_scene_director import run_director_v2
from candidate_scorer import DEPTH_LAYER_BY_KIND

JOB_DIR = ROOT / "data" / "jobs" / "k70_voxel_v51_visual_director"
V4_HERO = ROOT / "data/jobs/k70_voxel_v4_hero/hero_1080x1920.png"
V5_HERO = ROOT / "data/jobs/k70_voxel_v5_auto_director/final_hero.png"
REFERENCE = Path(r"C:\Users\Admin\Downloads\EXAMPLES.jpg")

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


def _draw_debug(image_path: Path, report: dict, out_path: Path):
    from PIL import Image, ImageDraw
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    colors = {"foreground": (255, 165, 0), "midground": (60, 230, 140), "background": (90, 160, 255)}
    for name, v in report["visibility"].items():
        if not v.get("in_frame"):
            continue
        xmin, ymin, xmax, ymax = v["screen_bbox"]
        px0, px1 = max(0, xmin * w), min(w, xmax * w)
        py0, py1 = max(0, (1 - ymax) * h), min(h, (1 - ymin) * h)  # normalized y=0 bottom -> pixel y=0 top
        layer = DEPTH_LAYER_BY_KIND.get(v.get("kind"), "background")
        color = colors.get(layer, (255, 255, 255))
        width = 5 if v.get("kind") == "hero" else 2
        draw.rectangle([px0, py0, px1, py1], outline=color, width=width)
        draw.text((px0 + 3, max(0, py0 + 3)), name, fill=color)
    for frac in (1 / 3, 2 / 3):
        draw.line([(frac * w, 0), (frac * w, h)], fill=(255, 255, 255), width=1)
        draw.line([(0, frac * h), (w, frac * h)], fill=(255, 255, 255), width=1)
    draw.text((8, h - 60), "orange=foreground  green=midground  blue=background  white=rule-of-thirds",
              fill=(255, 255, 255))
    img.save(out_path, quality=92)


def main():
    t0 = time.time()
    print("K70 VOXEL V5.1 -- Premium Cinematic Composition Selector")
    result = run_director_v2(SHOT_SPEC, JOB_DIR, n_candidates=24, seed_base=3000,
                             top_visual=6, top_final=3)

    (JOB_DIR / "director_decisions.json").write_text(json.dumps({
        "shot_spec": result["spec"],
        "n_candidates_generated": result["n_candidates"],
        "n_structurally_rejected": result["n_structurally_rejected"],
        "n_structural_survivors": result["n_structural_survivors"],
        "n_visual_finalists": result["n_visual_finalists"],
        "structurally_rejected_summary": result["structurally_rejected_summary"],
        "top_visual_seeds_and_scores": [{"seed": c["seed"], "total_score": c["score"]["total_score"]}
                                        for c in result["top_visual"]],
        "top_final_seeds_and_scores": [{"seed": c["seed"], "total_score": c["score"]["total_score"],
                                        "categories": c["score"]["categories"]} for c in result["top_final"]],
        "winner_seed": result["winner_seed"],
        "winner_camera": result["winner_plan"]["camera"],
        "winner_score_breakdown": result["winner_score"],
        "why_winner_scored_highest": "Highest visual_score total among structural survivors, re-scored twice "
                                     "against real rendered previews (360x640 for hero/practical-light luminance, "
                                     "then 540x960 for the final ranking pass) -- not just the geometry-only "
                                     "signal V5 relied on for its whole ranking. See candidate_scores.json for "
                                     "every candidate's full category breakdown.",
        "manual_coordinate_adjustments_after_generation": 0,
        "manual_camera_adjustments": 0,
        "manual_lighting_adjustments": 0,
        "timings": result["timings"],
    }, indent=2), encoding="utf-8")

    (JOB_DIR / "candidate_scores.json").write_text(json.dumps(result["all_candidates"], indent=2), encoding="utf-8")

    from PIL import Image, ImageDraw

    # ---- candidate_sheet.jpg: geometry-visual top-6 (before any image existed) ---- #
    cw, ch = 300, 20
    cand_sheet = Image.new("RGB", (700, 40 + len(result["top_visual"]) * 26), (15, 15, 18))
    cdraw = ImageDraw.Draw(cand_sheet)
    cdraw.text((8, 8), "V5.1 geometry-visual top candidates (pre-image ranking)", fill=(255, 255, 255))
    for i, c in enumerate(result["top_visual"]):
        cdraw.text((8, 40 + i * 26), f"seed {c['seed']}   visual_score={c['score']['total_score']}",
                  fill=(200, 220, 255))
    cand_sheet.save(JOB_DIR / "candidate_sheet.jpg", quality=90)

    # ---- top3_sheet.jpg: the 3 finalists' medium previews with scores ---- #
    pw, ph = 360, 640
    top3 = Image.new("RGB", (pw * len(result["top_final"]), ph + 40), (15, 15, 18))
    t3draw = ImageDraw.Draw(top3)
    for i, c in enumerate(result["top_final"]):
        if c["preview_path"] and Path(c["preview_path"]).exists():
            im = Image.open(c["preview_path"]).resize((pw, ph))
            top3.paste(im, (i * pw, 40))
        t3draw.text((i * pw + 8, 8), f"seed {c['seed']}  score={c['score']['total_score']}", fill=(255, 255, 255))
    top3.save(JOB_DIR / "top3_sheet.jpg", quality=90)

    # ---- comparison_sheet.jpg: reference / V4 / V5 / V5.1 ---- #
    final_img = Image.open(result["final_path"])
    target_h = 900
    def fit(im):
        w, h = im.size
        return im.resize((int(w * target_h / h), target_h))
    panels = [(fit(Image.open(REFERENCE)), "REFERENCE"), (fit(Image.open(V4_HERO)), "V4 (manual)"),
             (fit(Image.open(V5_HERO)), "V5 (auto, structural-only)"), (fit(final_img), "V5.1 (auto, visual-ranked)")]
    total_w = sum(p[0].width for p in panels) + 30 * (len(panels) - 1)
    comp = Image.new("RGB", (total_w, target_h + 40), (12, 12, 15))
    cdraw2 = ImageDraw.Draw(comp)
    x = 0
    for im, label in panels:
        comp.paste(im, (x, 40))
        cdraw2.text((x + 8, 10), label, fill=(255, 255, 255))
        x += im.width + 30
    comp.save(JOB_DIR / "comparison_sheet.jpg", quality=90)

    # ---- contact-style debug visualization on the WINNER ---- #
    final_report = json.loads((JOB_DIR / "final_report.json").read_text(encoding="utf-8"))
    _draw_debug(result["final_path"], final_report, JOB_DIR / "director_debug.png")

    metadata = {
        "title": "K70 Voxel V5.1 -- Premium Cinematic Composition Selector",
        "resolution": "1080x1920",
        "shot_spec": result["spec"],
        "winner_seed": result["winner_seed"],
        "n_candidates_generated": result["n_candidates"],
        "n_structurally_rejected": result["n_structurally_rejected"],
        "n_visual_finalists": result["n_visual_finalists"],
        "timings": result["timings"],
        "manual_coordinate_adjustments_after_generation": 0,
        "manual_camera_adjustments": 0,
        "manual_lighting_adjustments": 0,
        "files": {
            "final_hero": "final_hero.png", "candidate_sheet": "candidate_sheet.jpg",
            "top3_sheet": "top3_sheet.jpg", "comparison_sheet": "comparison_sheet.jpg",
            "director_debug": "director_debug.png (debug visualization only, not production output)",
            "director_decisions": "director_decisions.json", "candidate_scores": "candidate_scores.json",
        },
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    total_time = round(time.time() - t0, 1)
    print(f"\nWINNER: seed={result['winner_seed']} score={result['winner_score']['total_score']}")
    print(f"FINAL: {result['final_path']}")
    print(f"Structurally rejected {result['n_structurally_rejected']}/{result['n_candidates']}")
    print(f"Timings: {result['timings']}")
    print(f"Total driver time: {total_time}s")


if __name__ == "__main__":
    main()
