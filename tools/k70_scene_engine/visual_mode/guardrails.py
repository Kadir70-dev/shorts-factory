"""Storyboard visual-diversity guardrails (production-fix brief section
10). The mortgage video audit found MOTION_GRAPHIC + DATA_CHART reaching
78.73% of a video's runtime with no structural check catching it before
render. This module is that check -- called against a fully-authored
beat list BEFORE assets are generated, so a bad mix fails fast instead of
being discovered by manually inspecting the finished video.

Not wired into any BEATS list yet (see FINAL_REPORT.md) -- this is the
enforcement mechanism; applying it to `scripts/build_*_ep01.py` files is
a follow-up integration step.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .modes import VisualMode

# Default target ranges, expressed as (min, max) fractions of total runtime.
# "Motion graphics + data charts combined: maximum 20% by default" is the
# one HARD ceiling named explicitly in the brief; the others are soft
# targets a storyboard should aim for but can miss with justification.
DEFAULT_TARGETS: dict[str, tuple[float, float]] = {
    "real_footage": (0.30, 0.40),          # REAL_STOCK + REAL_IMAGE
    "engine_storytelling": (0.25, 0.40),   # 3D_CHARACTER + 3D_ENVIRONMENT + PROCEDURAL_CITY + VOXEL_STORY
    "graphics_cards": (0.0, 0.20),         # MOTION_GRAPHIC + DATA_CHART -- HARD ceiling
}

_REAL_FOOTAGE = {VisualMode.REAL_STOCK, VisualMode.REAL_IMAGE}
_ENGINE = {VisualMode.THREE_D_CHARACTER, VisualMode.THREE_D_ENVIRONMENT,
          VisualMode.PROCEDURAL_CITY, VisualMode.VOXEL_STORY}
_GRAPHICS = {VisualMode.MOTION_GRAPHIC, VisualMode.DATA_CHART}


@dataclass
class BeatPlan:
    """Minimal shape a storyboard beat needs for guardrail checking --
    deliberately not tied to any specific SceneGraph/Scene schema so this
    can validate a plain list of (mode, duration, template_id, ...)
    tuples before a full Scene object even exists."""
    beat_id: str
    mode: VisualMode
    duration_sec: float
    template_id: str = ""     # e.g. "mgfx_dark_card" -- for repeated-template detection
    camera_angle: str = ""    # for repeated-camera-angle detection
    character_id: str = ""    # for repeated-character-pose detection
    environment_id: str = ""  # for repeated-environment detection


@dataclass
class GuardrailViolation:
    rule: str
    detail: str
    severity: str  # "hard" (must fix) | "soft" (flagged, can proceed with justification)


@dataclass
class GuardrailReport:
    violations: list[GuardrailViolation] = field(default_factory=list)
    mix_percent: dict[str, float] = field(default_factory=dict)

    @property
    def hard_failures(self) -> list[GuardrailViolation]:
        return [v for v in self.violations if v.severity == "hard"]

    @property
    def passed(self) -> bool:
        return len(self.hard_failures) == 0

    def format(self) -> str:
        lines = [f"Storyboard guardrails: {'PASS' if self.passed else 'FAIL'}"]
        for k, v in self.mix_percent.items():
            lines.append(f"  {k}: {v*100:.1f}%")
        for viol in self.violations:
            lines.append(f"  [{viol.severity.upper()}] {viol.rule}: {viol.detail}")
        return "\n".join(lines)


def check(beats: list[BeatPlan], targets: dict[str, tuple[float, float]] | None = None,
         max_consecutive_cards: int = 3, max_template_repeat_frac: float = 0.35,
         max_same_camera_angle_run: int = 3) -> GuardrailReport:
    targets = targets or DEFAULT_TARGETS
    total = sum(b.duration_sec for b in beats) or 1.0
    report = GuardrailReport()

    real_sec = sum(b.duration_sec for b in beats if b.mode in _REAL_FOOTAGE)
    engine_sec = sum(b.duration_sec for b in beats if b.mode in _ENGINE)
    graphics_sec = sum(b.duration_sec for b in beats if b.mode in _GRAPHICS)
    report.mix_percent = {
        "real_footage": real_sec / total, "engine_storytelling": engine_sec / total,
        "graphics_cards": graphics_sec / total,
    }

    # HARD ceiling: motion graphics + charts combined
    lo, hi = targets["graphics_cards"]
    if graphics_sec / total > hi:
        report.violations.append(GuardrailViolation(
            "graphics_cards_ceiling",
            f"{graphics_sec/total*100:.1f}% is motion-graphic/chart cards, ceiling is {hi*100:.0f}% "
            f"(this exact failure mode reached 78.73% in the mortgage video)",
            "hard"))

    # soft targets: real footage and engine storytelling ranges
    for key in ("real_footage", "engine_storytelling"):
        lo, hi = targets[key]
        pct = report.mix_percent[key]
        if pct < lo:
            report.violations.append(GuardrailViolation(
                f"{key}_below_target", f"{pct*100:.1f}% is below the {lo*100:.0f}-{hi*100:.0f}% target range",
                "soft"))

    # consecutive graphics-card beats
    run = 0
    for b in beats:
        if b.mode in _GRAPHICS:
            run += 1
            if run > max_consecutive_cards:
                report.violations.append(GuardrailViolation(
                    "consecutive_cards", f"beat '{b.beat_id}' extends a run of {run} "
                    f"consecutive motion-graphic/chart beats (max {max_consecutive_cards})",
                    "hard"))
        else:
            run = 0

    # same card template dominating runtime
    template_sec: dict[str, float] = {}
    for b in beats:
        if b.template_id:
            template_sec[b.template_id] = template_sec.get(b.template_id, 0.0) + b.duration_sec
    for tmpl, sec in template_sec.items():
        frac = sec / total
        if frac > max_template_repeat_frac:
            report.violations.append(GuardrailViolation(
                "template_dominance", f"template '{tmpl}' is {frac*100:.1f}% of runtime "
                f"(max {max_template_repeat_frac*100:.0f}%) -- the mortgage video's single dark-card "
                "template alone was 43% of the video", "hard"))

    # repeated camera angle run (for character/environment beats)
    run_angle, run_len = None, 0
    for b in beats:
        if b.camera_angle:
            if b.camera_angle == run_angle:
                run_len += 1
            else:
                run_angle, run_len = b.camera_angle, 1
            if run_len > max_same_camera_angle_run:
                report.violations.append(GuardrailViolation(
                    "repeated_camera_angle", f"beat '{b.beat_id}' extends a run of {run_len} "
                    f"beats at camera angle '{b.camera_angle}'", "soft"))

    return report
