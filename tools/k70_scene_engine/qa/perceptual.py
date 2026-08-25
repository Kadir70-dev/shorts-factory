"""Perceptual visual QA (production-fix brief section 11) -- measures the
DELIVERED final video, separately from `visual_mode/guardrails.py` (which
checks the PLAN before rendering). A video can pass guardrails on paper
and still need this: guardrails trusts the beat list's own duration/mode
labels, this module re-derives the mix from the actual scene_graph.json +
asset_plan.json that produced a specific final.mp4, and adds a real
contact-sheet image for human inspection -- exactly the workflow used by
hand throughout this session's audits, now packaged as reusable code.

Explicitly NOT a replacement for `apps/api/app/pipeline/qa.py` (technical
QA: black frames, audio presence, resolution, duration). This is the
perceptual half the brief asked to be kept separate.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..visual_mode.modes import VisualMode

_LABEL = {
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


@dataclass
class PerceptualReport:
    total_seconds: float
    mix_seconds: dict[str, float]
    mix_percent: dict[str, float]
    scene_count: int
    average_shot_seconds: float
    longest_card_run_seconds: float
    longest_card_run_beats: int
    real_world_or_spatial_percent: float  # REAL_STOCK+REAL_IMAGE+3D_*+PROCEDURAL+VOXEL
    template_repeat_percent: dict[str, float]  # template_id -> % of runtime, for repeated-card detection
    contact_sheet_path: str | None = None
    warnings: list[str] = field(default_factory=list)

    def format(self) -> str:
        lines = [f"Perceptual QA -- {self.total_seconds:.1f}s, {self.scene_count} scenes"]
        lines.append("  Visual mix:")
        for k, v in sorted(self.mix_percent.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {k:<20} {self.mix_seconds[k]:7.2f}s  {v*100:5.1f}%")
        lines.append(f"  Average shot length: {self.average_shot_seconds:.2f}s")
        lines.append(f"  Longest card/chart run: {self.longest_card_run_seconds:.1f}s "
                     f"({self.longest_card_run_beats} beats)")
        lines.append(f"  Real-world/spatial coverage: {self.real_world_or_spatial_percent*100:.1f}%")
        if self.template_repeat_percent:
            lines.append("  Template repetition:")
            for tmpl, pct in sorted(self.template_repeat_percent.items(), key=lambda kv: -kv[1]):
                lines.append(f"    {tmpl:<20} {pct*100:5.1f}%")
        if self.contact_sheet_path:
            lines.append(f"  Contact sheet: {self.contact_sheet_path}")
        for w in self.warnings:
            lines.append(f"  [WARN] {w}")
        status = "FAIL" if self.warnings else "PASS (mechanical checks only -- still requires human visual inspection of the contact sheet)"
        lines.append(f"  PERCEPTUAL QA: {status}")
        return "\n".join(lines)


def analyze_from_job(*, scene_graph_path: Path, asset_plan_path: Path,
                     template_id_fn=None) -> PerceptualReport:
    """Re-derives the visual mix from a produced job's own scene_graph.json
    + asset_plan.json -- the same data source the mortgage-video audit used
    by hand. `template_id_fn(scene, plan_entry) -> str` lets a caller
    identify repeated card templates (e.g. by headline style/theme); if
    omitted, template-repetition is left empty rather than guessed."""
    graph = json.loads(scene_graph_path.read_text(encoding="utf-8"))
    plan_list = json.loads(asset_plan_path.read_text(encoding="utf-8"))
    plan = {p["scene_id"]: p for p in plan_list}

    mix_seconds: dict[str, float] = {}
    template_seconds: dict[str, float] = {}
    durations: list[float] = []
    total = 0.0
    longest_run_sec, longest_run_n = 0.0, 0
    run_sec, run_n = 0.0, 0
    _CARD_MODES = {VisualMode.MOTION_GRAPHIC, VisualMode.DATA_CHART}

    for scene in graph["scenes"]:
        p = plan.get(scene["id"], {})
        mode = _LABEL.get(p.get("vis", ""), VisualMode.MOTION_GRAPHIC)
        dur = scene["duration_sec"]
        mix_seconds[mode.value] = mix_seconds.get(mode.value, 0.0) + dur
        durations.append(dur)
        total += dur

        if mode in _CARD_MODES:
            run_sec += dur
            run_n += 1
        else:
            if run_sec > longest_run_sec:
                longest_run_sec, longest_run_n = run_sec, run_n
            run_sec, run_n = 0.0, 0

        if template_id_fn:
            tid = template_id_fn(scene, p)
            if tid:
                template_seconds[tid] = template_seconds.get(tid, 0.0) + dur
    if run_sec > longest_run_sec:
        longest_run_sec, longest_run_n = run_sec, run_n

    total = total or 1.0
    mix_percent = {k: v / total for k, v in mix_seconds.items()}
    real_spatial = sum(v for k, v in mix_percent.items()
                       if k not in (VisualMode.MOTION_GRAPHIC.value, VisualMode.DATA_CHART.value,
                                   VisualMode.AI_IMAGE.value, VisualMode.AI_VIDEO.value))

    warnings = []
    graphics_pct = mix_percent.get(VisualMode.MOTION_GRAPHIC.value, 0) + \
        mix_percent.get(VisualMode.DATA_CHART.value, 0)
    if graphics_pct > 0.20:
        warnings.append(f"motion-graphic+chart share is {graphics_pct*100:.1f}%, over the 20% guardrail ceiling")
    if longest_run_sec > 30:
        warnings.append(f"longest uninterrupted card/chart run is {longest_run_sec:.1f}s ({longest_run_n} beats)")

    return PerceptualReport(
        total_seconds=total, mix_seconds=mix_seconds, mix_percent=mix_percent,
        scene_count=len(graph["scenes"]),
        average_shot_seconds=sum(durations) / len(durations) if durations else 0.0,
        longest_card_run_seconds=longest_run_sec, longest_card_run_beats=longest_run_n,
        real_world_or_spatial_percent=real_spatial,
        template_repeat_percent={k: v / total for k, v in template_seconds.items()},
        warnings=warnings,
    )


def build_contact_sheet(video_path: Path, out_path: Path, *, cols: int = 8, rows: int = 5,
                        tile_w: int = 320, tile_h: int = 180) -> Path:
    """ffmpeg-based contact sheet (the exact tool used by hand throughout
    this session's manual QA passes), packaged so future jobs get one
    automatically instead of a human re-deriving the ffmpeg command each
    time."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    n = cols * rows
    interval = duration / n
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-vf", f"fps=1/{interval:.4f},scale={tile_w}:{tile_h},tile={cols}x{rows}",
         "-frames:v", "1", "-q:v", "3", str(out_path)],
        capture_output=True, text=True,
    )
    if not out_path.exists():
        raise RuntimeError(f"contact sheet generation failed for {video_path}")
    return out_path
