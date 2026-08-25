#!/usr/bin/env python3
"""K70 VOXEL V5 -- Auto Scene Director driver.

Runs the SAME conceptual shot as V4 (John, financial district, golden
hour, 3+ NPCs, 2+ vehicles, storefront, signage, street props, vegetation,
deep skyline) but the composition is fully director-generated -- no
hand-picked coordinates in this file at all.

    .venv-win/Scripts/python.exe scripts/build_voxel_v5_auto_director.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/k70_scene_engine/director"))
from auto_scene_director import run_director

JOB_DIR = ROOT / "data" / "jobs" / "k70_voxel_v5_auto_director"

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
    print("K70 VOXEL V5 -- Auto Scene Director")
    result = run_director(SHOT_SPEC, JOB_DIR, n_candidates=16, seed_base=2000, top_k=3)

    (JOB_DIR / "director_decisions.json").write_text(json.dumps({
        "shot_spec": result["spec"],
        "n_candidates_generated": result["n_candidates"],
        "n_rejected": result["n_rejected"],
        "n_survivors": result["n_survivors"],
        "rejected_summary": result["rejected_summary"],
        "top_3_seeds_and_scores": result["top_k"],
        "winner_seed": result["winner_seed"],
        "winner_camera": result["winner_plan"]["camera"],
        "winner_score_breakdown": result["winner_score"],
        "why_winner_scored_highest": "Highest total_score among non-rejected candidates (see "
                                     "candidate_scores.json for every candidate's category breakdown). "
                                     "No separate visual-model re-ranking was performed -- the spec "
                                     "allows this as optional and instructs not to build a new AI stack "
                                     "solely for it; the deterministic geometry-based score was used "
                                     "as the sole ranking signal, consistent with section 15/17.",
        "timings": result["timings"],
    }, indent=2), encoding="utf-8")

    (JOB_DIR / "candidate_scores.json").write_text(json.dumps(result["all_candidates"], indent=2), encoding="utf-8")

    # ---- candidate_sheet.jpg: top-3 previews with score labels ---- #
    from PIL import Image, ImageDraw
    cw, ch = 360, 640
    cand_sheet = Image.new("RGB", (cw * len(result["top_k"]), ch + 40), (15, 15, 18))
    draw = ImageDraw.Draw(cand_sheet)
    for i, c in enumerate(result["top_k"]):
        if c["preview_path"] and Path(c["preview_path"]).exists():
            im = Image.open(c["preview_path"]).resize((cw, ch))
            cand_sheet.paste(im, (i * cw, 40))
        draw.text((i * cw + 8, 8), f"seed {c['seed']}  score={c['score']['total_score']}", fill=(255, 255, 255))
    cand_sheet.save(JOB_DIR / "candidate_sheet.jpg", quality=90)

    # ---- contact_sheet.jpg: standard multi-sample grid of the FINAL winner image ---- #
    final_img = Image.open(result["final_path"])
    fw, fh = final_img.size
    crops = []
    n = 6
    for i in range(n):
        y0 = int(fh * i / n)
        y1 = int(fh * (i + 1) / n)
        crops.append(final_img.crop((0, y0, fw, y1)).resize((360, 220)))
    cols, rows = 2, 3
    tw, th = 360, 220
    contact = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(crops):
        contact.paste(im, ((i % cols) * tw, (i // cols) * th))
    contact.save(JOB_DIR / "contact_sheet.jpg", quality=90)

    # ---- comparison_sheet.jpg: reference vs V4 vs V5 ---- #
    ref = Image.open(r"C:\Users\Admin\Downloads\EXAMPLES.jpg")
    v4 = Image.open(ROOT / "data/jobs/k70_voxel_v4_hero/hero_1080x1920.png")
    v5 = final_img
    target_h = 960
    def fit(im):
        w, h = im.size
        return im.resize((int(w * target_h / h), target_h))
    ref_r, v4_r, v5_r = fit(ref), fit(v4), fit(v5)
    total_w = ref_r.width + v4_r.width + v5_r.width + 40
    comp = Image.new("RGB", (total_w, target_h + 40), (12, 12, 15))
    x = 0
    cdraw = ImageDraw.Draw(comp)
    for im, label in [(ref_r, "REFERENCE"), (v4_r, "V4 (manual)"), (v5_r, "V5 (auto-directed)")]:
        comp.paste(im, (x, 40))
        cdraw.text((x + 8, 10), label, fill=(255, 255, 255))
        x += im.width + 20
    comp.save(JOB_DIR / "comparison_sheet.jpg", quality=90)

    metadata = {
        "title": "K70 Voxel V5 -- Auto Scene Director",
        "resolution": "1080x1920",
        "shot_spec": result["spec"],
        "winner_seed": result["winner_seed"],
        "n_candidates_generated": result["n_candidates"],
        "n_rejected": result["n_rejected"],
        "timings": result["timings"],
        "manual_coordinate_adjustments_after_generation": 0,
        "files": {
            "final_hero": "final_hero.png", "contact_sheet": "contact_sheet.jpg",
            "candidate_sheet": "candidate_sheet.jpg", "comparison_sheet": "comparison_sheet.jpg",
            "director_decisions": "director_decisions.json", "candidate_scores": "candidate_scores.json",
        },
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    total_time = round(time.time() - t0, 1)
    print(f"\nWINNER: seed={result['winner_seed']} score={result['winner_score']['total_score']}")
    print(f"FINAL: {result['final_path']}")
    print(f"Rejected {result['n_rejected']}/{result['n_candidates']} candidates")
    print(f"Timings: {result['timings']}")
    print(f"Total driver time: {total_time}s")


if __name__ == "__main__":
    main()
