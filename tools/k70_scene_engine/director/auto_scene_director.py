"""K70 AUTO SCENE DIRECTOR V1 -- top-level orchestrator. Pure Python
(shells out to Blender per candidate; does not import bpy itself).

Pipeline (matches the requested workflow exactly):
  generate N seeded candidates (composition.py, cheap, no Blender)
  -> for each: Blender "check" pass (geometry + real visibility/occlusion
     via world_to_camera_view + ray_cast, NO image render -- fast)
  -> hard-reject invalid candidates (candidate_scorer.hard_reject)
  -> score survivors (candidate_scorer.score_candidate)
  -> keep top 3 by score
  -> Blender "render" pass for those 3 only, at a small preview resolution
  -> pick #1 (by the same geometry score -- see director_decisions.json
     for the explicit note that no separate visual re-ranking model was
     available/used, per the spec's "optional, don't build a new AI stack"
     instruction)
  -> Blender "render" pass for the winner at full 1080x1920

Every stage's timing is tracked and reported.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot_templates import resolve_shot_spec
from composition import plan_scene
from candidate_scorer import (hard_reject, score_candidate, visual_score, visual_score_v52,
                              composition_hard_veto, establishing_shot_reject,
                              hero_prominence_hard_veto)

ROOT = Path(__file__).resolve().parents[3]
BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
BDIR = ROOT / "tools/k70_scene_engine/blender"


def _run_blender(plan, mode, width, height, samples, report_path, output_path=None, timeout=300, practical_emission=2.3):
    spec = {"plan": plan, "mode": mode, "width": width, "height": height, "samples": samples,
            "report_path": str(report_path), "practical_emission": practical_emission}
    if output_path:
        spec["output_path"] = str(output_path)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(BDIR / "_director_build_and_check.py"), "--", args_path],
        capture_output=True, text=True, timeout=timeout,
    )
    Path(args_path).unlink(missing_ok=True)
    ok_marker = "K70_DIRECTOR_CHECK_OK" if mode == "check" else "K70_DIRECTOR_RENDER_OK"
    if ok_marker not in proc.stdout:
        raise RuntimeError(f"director pass failed (mode={mode}):\nSTDOUT:{proc.stdout[-2500:]}\nSTDERR:{proc.stderr[-2000:]}")
    return json.loads(Path(report_path).read_text(encoding="utf-8"))


def run_director(spec: dict, job_dir: Path, n_candidates: int = 16, seed_base: int = 1000, top_k: int = 3):
    job_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir = job_dir / "candidates"
    candidates_dir.mkdir(exist_ok=True)

    spec = resolve_shot_spec(spec)
    timings = {}
    t0 = time.time()

    # ---- 1. generate + check N candidates (cheap: geometry + raycast only, no render) ---- #
    results = []
    for i in range(n_candidates):
        seed = seed_base + i
        plan = plan_scene(spec, seed)
        report_path = candidates_dir / f"cand_{seed}_report.json"
        # Resume-safe: a "check" pass writes ONLY this JSON (no image), so
        # an existing, parseable report is a complete, safe-to-reuse
        # result -- unlike a "render" pass below, where the report is
        # written BEFORE the image, so an interrupted run can leave a
        # report with no corresponding PNG.
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                report = _run_blender(plan, "check", width=360, height=640, samples=1, report_path=report_path)
        else:
            report = _run_blender(plan, "check", width=360, height=640, samples=1, report_path=report_path)
        rejected_reasons = hard_reject(report)
        score = score_candidate(report, plan) if not rejected_reasons else {"categories": {}, "total_score": -1}
        results.append({"seed": seed, "plan": plan, "report": report,
                        "rejected": bool(rejected_reasons), "reject_reasons": rejected_reasons,
                        "score": score})
    timings["candidate_generation_and_check_sec"] = round(time.time() - t0, 1)

    survivors = [r for r in results if not r["rejected"]]
    rejected = [r for r in results if r["rejected"]]
    survivors.sort(key=lambda r: r["score"]["total_score"], reverse=True)
    top = survivors[:top_k]

    # ---- 2. render top-K as cheap previews ---- #
    t1 = time.time()
    for r in top:
        preview_path = candidates_dir / f"cand_{r['seed']}_preview.png"
        report_path = candidates_dir / f"cand_{r['seed']}_preview_report.json"
        # Resume-safe only if the actual PNG exists -- a "render" pass
        # writes its JSON report BEFORE the image, so a report alone
        # (e.g. from an interrupted prior run) does not prove the image
        # completed.
        if not preview_path.exists():
            _run_blender(r["plan"], "render", width=360, height=640, samples=16,
                        report_path=report_path, output_path=preview_path)
        r["preview_path"] = str(preview_path)
    timings["top_k_preview_render_sec"] = round(time.time() - t1, 1)

    if not top:
        raise RuntimeError(f"ALL {n_candidates} candidates were hard-rejected -- no survivor to render. "
                          f"Reasons seen: {sorted(set(reason for r in rejected for reason in r['reject_reasons']))}")

    winner = top[0]

    # ---- 3. final full-res render of the winner only ---- #
    t2 = time.time()
    final_path = job_dir / "final_hero.png"
    final_report_path = job_dir / "final_report.json"
    if not final_path.exists():
        _run_blender(winner["plan"], "render", width=1080, height=1920, samples=96,
                    report_path=final_report_path, output_path=final_path, timeout=600)
    timings["final_render_sec"] = round(time.time() - t2, 1)
    timings["total_sec"] = round(time.time() - t0, 1)

    return {
        "spec": spec, "n_candidates": n_candidates, "n_rejected": len(rejected), "n_survivors": len(survivors),
        "top_k": [{"seed": r["seed"], "score": r["score"], "preview_path": r.get("preview_path")} for r in top],
        "winner_seed": winner["seed"], "winner_plan": winner["plan"], "winner_score": winner["score"],
        "rejected_summary": [{"seed": r["seed"], "reasons": r["reject_reasons"]} for r in rejected],
        "final_path": str(final_path), "timings": timings,
        "all_candidates": [{"seed": r["seed"], "rejected": r["rejected"], "reject_reasons": r["reject_reasons"],
                            "total_score": r["score"]["total_score"]} for r in results],
    }


def run_director_v2(spec: dict, job_dir: Path, n_candidates: int = 16, seed_base: int = 3000,
                    top_structural_to_visual: int | None = None, top_visual: int = 6, top_final: int = 3):
    """K70 V5.1 -- premium cinematic composition selector. Same STRUCTURAL
    gate as V5 (hard_reject, unchanged), then a staged VISUAL ranking V5
    never had:

      N candidates -> structural check (cheap, no image)
      -> hard_reject survivors -> visual_score (geometry-only, no image)
      -> top `top_visual` -> 360x640 lighting preview each
      -> visual_score AGAIN, now with rendered luminance (hero/practical
         light) -> top `top_final`
      -> 540x960 medium preview each -> visual_score once more on the
         better image -> winner
      -> 1080x1920 final render

    This is what section 15/16's two-stage structural/visual split and
    staged-preview-resolution workflow ask for -- V5's single-stage
    "render 3 previews at one fixed resolution, never re-score them"
    couldn't catch a lighting/composition problem that only becomes
    visible once an actual image exists."""
    job_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir = job_dir / "candidates"
    candidates_dir.mkdir(exist_ok=True)

    spec = resolve_shot_spec(spec)
    timings = {}
    t0 = time.time()

    # ---- 1. generate + STRUCTURAL check N candidates (cheap, no image) ---- #
    results = []
    for i in range(n_candidates):
        seed = seed_base + i
        plan = plan_scene(spec, seed)
        report_path = candidates_dir / f"cand_{seed}_report.json"
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                report = _run_blender(plan, "check", width=360, height=640, samples=1, report_path=report_path)
        else:
            report = _run_blender(plan, "check", width=360, height=640, samples=1, report_path=report_path)
        reject_reasons = hard_reject(report)
        results.append({"seed": seed, "plan": plan, "report": report,
                        "rejected": bool(reject_reasons), "reject_reasons": reject_reasons})
    timings["structural_check_sec"] = round(time.time() - t0, 1)

    survivors = [r for r in results if not r["rejected"]]
    rejected = [r for r in results if r["rejected"]]

    # ---- 2. VISUAL score (geometry-only) -> top_visual ---- #
    t1 = time.time()
    for r in survivors:
        r["visual"] = visual_score(r["report"], r["plan"], preview_image_path=None)
    survivors.sort(key=lambda r: r["visual"]["total_score"], reverse=True)
    stage_visual = survivors[:top_visual]
    timings["geometry_visual_score_sec"] = round(time.time() - t1, 1)

    if not stage_visual:
        raise RuntimeError(f"ALL {n_candidates} candidates were structurally rejected -- no survivor to visually "
                          f"rank. Reasons seen: {sorted(set(reason for r in rejected for reason in r['reject_reasons']))}")

    # ---- 3. 360x640 lighting preview for the visual top-N, re-score with luminance ---- #
    t2 = time.time()
    for r in stage_visual:
        preview_path = candidates_dir / f"cand_{r['seed']}_light_preview.png"
        report_path = candidates_dir / f"cand_{r['seed']}_light_preview_report.json"
        if not preview_path.exists():
            _run_blender(r["plan"], "render", width=360, height=640, samples=16,
                        report_path=report_path, output_path=preview_path)
        r["light_preview_path"] = str(preview_path)
        r["visual"] = visual_score(r["report"], r["plan"], preview_image_path=str(preview_path))
    stage_visual.sort(key=lambda r: r["visual"]["total_score"], reverse=True)
    top_lighting = stage_visual[:top_final]
    timings["lighting_preview_and_score_sec"] = round(time.time() - t2, 1)

    # ---- 4. 540x960 medium preview for the finalists, final re-score ---- #
    t3 = time.time()
    for r in top_lighting:
        preview_path = candidates_dir / f"cand_{r['seed']}_medium_preview.png"
        report_path = candidates_dir / f"cand_{r['seed']}_medium_preview_report.json"
        if not preview_path.exists():
            _run_blender(r["plan"], "render", width=540, height=960, samples=32,
                        report_path=report_path, output_path=preview_path)
        r["medium_preview_path"] = str(preview_path)
        r["visual"] = visual_score(r["report"], r["plan"], preview_image_path=str(preview_path))
    top_lighting.sort(key=lambda r: r["visual"]["total_score"], reverse=True)
    timings["medium_preview_and_score_sec"] = round(time.time() - t3, 1)

    winner = top_lighting[0]

    # ---- 5. final full-res render of the winner only ---- #
    t4 = time.time()
    final_path = job_dir / "final_hero.png"
    final_report_path = job_dir / "final_report.json"
    if not final_path.exists():
        _run_blender(winner["plan"], "render", width=1080, height=1920, samples=96,
                    report_path=final_report_path, output_path=final_path, timeout=600)
    timings["final_render_sec"] = round(time.time() - t4, 1)
    timings["total_sec"] = round(time.time() - t0, 1)

    return {
        "spec": spec, "n_candidates": n_candidates, "n_structurally_rejected": len(rejected),
        "n_structural_survivors": len(survivors),
        "n_visual_finalists": len(stage_visual),
        "top_visual": [{"seed": r["seed"], "score": r["visual"], "preview_path": r.get("light_preview_path")}
                      for r in stage_visual],
        "top_final": [{"seed": r["seed"], "score": r["visual"], "preview_path": r.get("medium_preview_path")}
                     for r in top_lighting],
        "winner_seed": winner["seed"], "winner_plan": winner["plan"], "winner_score": winner["visual"],
        "structurally_rejected_summary": [{"seed": r["seed"], "reasons": r["reject_reasons"]} for r in rejected],
        "final_path": str(final_path), "timings": timings,
        "all_candidates": [{"seed": r["seed"], "rejected": r["rejected"],
                            "reject_reasons": r.get("reject_reasons", []),
                            "visual_total_score": r.get("visual", {}).get("total_score")} for r in results],
    }


def run_director_v3(spec: dict, job_dir: Path, n_candidates: int = 24, seed_base: int = 5000,
                    top_visual: int = 6, top_final: int = 3, composition_veto_threshold: float = 6.0):
    """K70 V5.2 -- adds three gates V5.1 didn't have, on top of the SAME
    unchanged structural gate (hard_reject) and the SAME golden-hour
    lighting system (setup_golden_hour_v2) V5.1 proved:

      1. establishing_shot_reject() -- a HARD GATE (not a soft score) for
         shot breadth (visible sky, visible ground, hero not oversized).
         V5.1's own scoring could and did converge on an even tighter
         crop than V5 because nothing REQUIRED breadth, only rewarded it
         softly.
      2. composition_hard_veto() -- any candidate whose COMPOSITION_
         BALANCE falls below `composition_veto_threshold` is dropped from
         the ranking pool outright, so a badly-unbalanced frame (V5.1's
         winner scored 4.43 there) can no longer win purely by being
         strong elsewhere.
      3. visual_score_v52()'s REAL_DEPTH -- camera-space measured
         distance, not kind-based classification, so a close object
         merely CLASSIFIED as "background" can't score as if a deep city
         were genuinely visible.

    Pipeline is otherwise the same staged structural -> geometry-visual
    -> lighting-visual -> medium-visual flow as run_director_v2."""
    job_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir = job_dir / "candidates"
    candidates_dir.mkdir(exist_ok=True)

    spec = resolve_shot_spec(spec)
    timings = {}
    t0 = time.time()

    # ---- 1. generate + STRUCTURAL check, THEN the establishing-shot hard gate ---- #
    results = []
    for i in range(n_candidates):
        seed = seed_base + i
        plan = plan_scene(spec, seed)
        report_path = candidates_dir / f"cand_{seed}_report.json"
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                report = _run_blender(plan, "check", width=360, height=640, samples=1, report_path=report_path)
        else:
            report = _run_blender(plan, "check", width=360, height=640, samples=1, report_path=report_path)
        reasons = hard_reject(report)
        if not reasons:
            reasons = establishing_shot_reject(report["visibility"], report)
        results.append({"seed": seed, "plan": plan, "report": report,
                        "rejected": bool(reasons), "reject_reasons": reasons})
    timings["structural_and_framing_check_sec"] = round(time.time() - t0, 1)

    survivors = [r for r in results if not r["rejected"]]
    rejected = [r for r in results if r["rejected"]]

    # ---- 2. VISUAL score (geometry-only, V5.2) + composition/hero-prominence hard-vetoes ---- #
    t1 = time.time()
    veto_rejected = []
    ranking_pool = []
    for r in survivors:
        r["visual"] = visual_score_v52(r["report"], r["plan"], preview_image_path=None)
        vetoed = (composition_hard_veto(r["visual"]["categories"], composition_veto_threshold)
                 or hero_prominence_hard_veto(r["report"]["visibility"]))
        if vetoed:
            veto_rejected.append(r)
        else:
            ranking_pool.append(r)
    ranking_pool.sort(key=lambda r: r["visual"]["total_score"], reverse=True)
    stage_visual = ranking_pool[:top_visual]
    timings["geometry_visual_score_sec"] = round(time.time() - t1, 1)

    if not stage_visual:
        # veto emptied the pool -- fall back to the least-bad vetoed
        # candidates rather than crashing, but flag it plainly. Sort by
        # the MINIMUM of the two veto-relevant categories (composition
        # balance, hero prominence), not composition alone -- an earlier
        # version sorted by COMPOSITION_BALANCE only, which let a
        # candidate vetoed for catastrophic HERO_PROMINENCE (ratio 2x+)
        # win the fallback purely because its composition score was fine.
        def _worst_veto_category(r):
            cats = r["visual"]["categories"]
            return min(cats.get("COMPOSITION_BALANCE", 0.0), cats.get("HERO_PROMINENCE", 0.0))
        veto_rejected.sort(key=_worst_veto_category, reverse=True)
        stage_visual = veto_rejected[:top_visual]
        if not stage_visual:
            raise RuntimeError(f"ALL {n_candidates} candidates were structurally/framing rejected -- no survivor. "
                              f"Reasons seen: {sorted(set(reason for r in rejected for reason in r['reject_reasons']))}")

    # ---- 3. 360x640 lighting preview for the visual top-N, re-score with luminance ---- #
    t2 = time.time()
    for r in stage_visual:
        preview_path = candidates_dir / f"cand_{r['seed']}_light_preview.png"
        report_path = candidates_dir / f"cand_{r['seed']}_light_preview_report.json"
        if not preview_path.exists():
            _run_blender(r["plan"], "render", width=360, height=640, samples=16,
                        report_path=report_path, output_path=preview_path)
        r["light_preview_path"] = str(preview_path)
        r["visual"] = visual_score_v52(r["report"], r["plan"], preview_image_path=str(preview_path))
    stage_visual.sort(key=lambda r: r["visual"]["total_score"], reverse=True)
    top_lighting = stage_visual[:top_final]
    timings["lighting_preview_and_score_sec"] = round(time.time() - t2, 1)

    # ---- 4. 540x960 medium preview for the finalists, final re-score ---- #
    t3 = time.time()
    for r in top_lighting:
        preview_path = candidates_dir / f"cand_{r['seed']}_medium_preview.png"
        report_path = candidates_dir / f"cand_{r['seed']}_medium_preview_report.json"
        if not preview_path.exists():
            _run_blender(r["plan"], "render", width=540, height=960, samples=32,
                        report_path=report_path, output_path=preview_path)
        r["medium_preview_path"] = str(preview_path)
        r["visual"] = visual_score_v52(r["report"], r["plan"], preview_image_path=str(preview_path))
    top_lighting.sort(key=lambda r: r["visual"]["total_score"], reverse=True)
    timings["medium_preview_and_score_sec"] = round(time.time() - t3, 1)

    winner = top_lighting[0]

    # ---- 5. final full-res render of the winner only ---- #
    t4 = time.time()
    final_path = job_dir / "final_hero.png"
    final_report_path = job_dir / "final_report.json"
    if not final_path.exists():
        _run_blender(winner["plan"], "render", width=1080, height=1920, samples=96,
                    report_path=final_report_path, output_path=final_path, timeout=600)
    timings["final_render_sec"] = round(time.time() - t4, 1)
    timings["total_sec"] = round(time.time() - t0, 1)

    return {
        "spec": spec, "n_candidates": n_candidates, "n_structurally_rejected": len(rejected),
        "n_structural_survivors": len(survivors), "n_composition_vetoed": len(veto_rejected),
        "n_visual_finalists": len(stage_visual),
        "top_visual": [{"seed": r["seed"], "score": r["visual"], "preview_path": r.get("light_preview_path")}
                      for r in stage_visual],
        "top_final": [{"seed": r["seed"], "score": r["visual"], "preview_path": r.get("medium_preview_path")}
                     for r in top_lighting],
        "winner_seed": winner["seed"], "winner_plan": winner["plan"], "winner_score": winner["visual"],
        "structurally_rejected_summary": [{"seed": r["seed"], "reasons": r["reject_reasons"]} for r in rejected],
        "composition_vetoed_summary": [{"seed": r["seed"],
                                        "composition_balance": r["visual"]["categories"].get("COMPOSITION_BALANCE")}
                                       for r in veto_rejected],
        "final_path": str(final_path), "timings": timings,
        "all_candidates": [{"seed": r["seed"], "rejected": r["rejected"],
                            "reject_reasons": r.get("reject_reasons", []),
                            "visual_total_score": r.get("visual", {}).get("total_score")} for r in results],
    }
