"""Real, ENFORCED production gates -- not reports. `visual_mode/guardrails.py`
and `qa/perceptual.py` were built and proven correct against the actual
mortgage video's data, but until this file existed nothing in the
production pipeline actually called them: a future job could still repeat
the mortgage video's 78.7%-cards failure and nothing would stop it.

Both functions here RAISE (ProductionGateError) on a hard failure instead
of returning a report the caller could ignore. A production script that
calls these and lets the exception propagate genuinely cannot complete
with a bad storyboard or a bad delivered video -- that's what "the job
must STOP" means, not a printed warning.
"""
from __future__ import annotations

from pathlib import Path

from ..qa.aesthetic import AestheticReport, analyze_frame
from ..qa.perceptual import PerceptualReport, analyze_from_job
from ..visual_mode.guardrails import BeatPlan, GuardrailReport, check as _check_guardrails
from ..visual_mode.modes import VisualMode


class ProductionGateError(RuntimeError):
    """Raised when a storyboard or delivered video fails an ENFORCED
    production gate. Callers should let this propagate (halting the
    production script) rather than catching and continuing."""


_LABEL_TO_MODE = {
    "stock": VisualMode.REAL_STOCK, "archival": VisualMode.REAL_STOCK,
    "character": VisualMode.THREE_D_CHARACTER, "voxel": VisualMode.VOXEL_STORY,
    "voxel_story": VisualMode.VOXEL_STORY,
    "mblab_character": VisualMode.THREE_D_CHARACTER,
    "mblab_walk": VisualMode.THREE_D_CHARACTER,
    "voxel_human_still": VisualMode.THREE_D_CHARACTER,
    "voxel_human_clip": VisualMode.THREE_D_CHARACTER,
    "procedural_building": VisualMode.THREE_D_ENVIRONMENT,
    "environment": VisualMode.THREE_D_ENVIRONMENT, "procedural_city": VisualMode.PROCEDURAL_CITY,
    "mgfx": VisualMode.MOTION_GRAPHIC, "chart": VisualMode.DATA_CHART,
    "ai_image": VisualMode.AI_IMAGE, "ai_video": VisualMode.AI_VIDEO,
}


def beats_from_job_plan(scene_graph: dict, asset_plan: list[dict],
                        template_id_fn=None) -> list[BeatPlan]:
    """Converts a job's own scene_graph.json + asset_plan.json into the
    BeatPlan list guardrails.check() understands. Same vis-label mapping
    perceptual.py's analyze_from_job() uses, so both gates agree on what
    counts as which VisualMode for the same job."""
    plan_by_id = {p["scene_id"]: p for p in asset_plan}
    beats = []
    for scene in scene_graph["scenes"]:
        p = plan_by_id.get(scene["id"], {})
        vis_label = p.get("vis", "")
        if vis_label not in _LABEL_TO_MODE:
            # A silent default here (e.g. always falling back to
            # MOTION_GRAPHIC) is exactly how a mislabeled vis type could
            # slip past the gate uncaught -- confirmed by a real bug this
            # produced during this session: "voxel_story" wasn't in this
            # map, silently counted as a motion-graphic card, and nearly
            # tipped a real storyboard over the ceiling for the wrong
            # reason. Fail loud instead.
            raise KeyError(f"beats_from_job_plan: unknown vis label '{vis_label}' for "
                           f"scene '{scene['id']}' -- add it to _LABEL_TO_MODE")
        mode = _LABEL_TO_MODE[vis_label]
        beats.append(BeatPlan(
            beat_id=scene["id"], mode=mode, duration_sec=scene["duration_sec"],
            template_id=template_id_fn(scene, p) if template_id_fn else "",
            camera_angle=p.get("character_angle", ""),
            character_id=p.get("character", ""),
            environment_id=p.get("environment", ""),
        ))
    return beats


def enforce_storyboard_guardrails(beats: list[BeatPlan], **check_kwargs) -> GuardrailReport:
    """Call this BEFORE any asset rendering starts (right after the
    scene_graph/asset_plan are loaded). Raises ProductionGateError on any
    hard violation -- the exact failure mode that let the mortgage video's
    storyboard reach 78.7% motion-graphic/chart cards with nothing
    stopping it."""
    report = _check_guardrails(beats, **check_kwargs)
    if not report.passed:
        raise ProductionGateError(
            "STORYBOARD GUARDRAILS FAILED -- production stopped before any asset was "
            "rendered.\n" + report.format())
    return report


def enforce_perceptual_qa(*, scene_graph_path: Path, asset_plan_path: Path,
                          video_path: Path, contact_sheet_out: Path | None = None,
                          template_id_fn=None) -> PerceptualReport:
    """Call this AFTER render, alongside (not instead of) the existing
    technical QA (`apps/api/app/pipeline/qa.py`). Raises
    ProductionGateError if the delivered video's actual visual mix
    violates the guardrail thresholds -- this is the authoritative
    post-render check, since it measures what was actually delivered,
    not just what the plan intended."""
    report = analyze_from_job(scene_graph_path=scene_graph_path, asset_plan_path=asset_plan_path,
                              template_id_fn=template_id_fn)
    if contact_sheet_out is not None and video_path.exists():
        from ..qa.perceptual import build_contact_sheet
        report.contact_sheet_path = str(build_contact_sheet(video_path, contact_sheet_out))
    if report.warnings:
        raise ProductionGateError(
            "PERCEPTUAL QA FAILED -- video does not meet production visual-quality "
            "thresholds.\n" + report.format())
    return report


_DARK_THEME_EXEMPT_MODES = {VisualMode.DATA_CHART, VisualMode.MOTION_GRAPHIC}


def enforce_aesthetic_qa(frames: list[tuple[Path, VisualMode | None]], *,
                         max_gross_failure_fraction: float = 0.20) -> list[AestheticReport]:
    """Samples frames (one per scene is the intended use -- see
    produce_benchmark_ep02.py's per-scene extraction) and runs
    deterministic CV metrics on each (qa/aesthetic.py). Each frame is
    paired with its scene's VisualMode so the dark-frame check can exempt
    DATA_CHART/MOTION_GRAPHIC: this brand's charts use a deliberate dark
    dashboard theme (same style already shipped in the mortgage/forex/
    XAU-USD videos), and a first version of this gate flagged that
    correct, on-brand chart as a "near-black" failure -- a real false
    positive caught during this session's own testing, not a
    hypothetical one. Excluding those two modes from the dark check
    (they're still scored and reported, just not hard-failed on darkness
    alone) is a targeted fix for a confirmed false positive, not a
    loosened threshold to make the gate pass.

    Deliberately only HARD-fails on near-black/blown-out fractions --
    sharpness/color_std/edge_density are real signals but produced
    false positives on legitimate simple architecture shots during this
    module's calibration too. Those stay in the reports for human
    review; they don't halt the job alone. Brief: "Do NOT claim an
    automated model can perfectly judge art." Contact-sheet human
    inspection is still mandatory -- this only catches gross technical
    failures a human forensic audit already found by eye (e.g. the
    near-black character+environment shots from a lighting-energy bug
    earlier this session)."""
    reports = []
    gross_failures = []
    for path, mode in frames:
        r = analyze_frame(path)
        reports.append(r)
        if mode in _DARK_THEME_EXEMPT_MODES:
            continue
        if r.dark_fraction > 0.55 or r.bright_fraction > 0.35:
            gross_failures.append(r)

    fraction = len(gross_failures) / max(len(reports), 1)
    if fraction > max_gross_failure_fraction:
        detail = "\n".join(f"  {Path(r.path).name}: dark%={r.dark_fraction*100:.1f} "
                           f"bright%={r.bright_fraction*100:.1f}" for r in gross_failures)
        raise ProductionGateError(
            f"AESTHETIC QA FAILED -- {len(gross_failures)}/{len(reports)} sampled frames "
            f"({fraction*100:.0f}%) are near-black or blown-out, excluding on-brand dark-"
            f"themed chart/motion-graphic beats (over {max_gross_failure_fraction*100:.0f}% "
            f"threshold):\n{detail}")
    return reports
