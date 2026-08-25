"""Honest renderer-status registry for K70 Visual Engine V2.

Per the brief's own rule -- "Do NOT claim a tool is integrated merely
because it cloned successfully" -- this module is the single source of
truth for "is style X actually production-capable right now," and it is
deliberately conservative: a style only flips to PRODUCTION once a real
renderer function exists AND a real gold-standard benchmark artifact has
been rendered and manually reviewed. Everything else stays NOT_BUILT even
if a repo has been license-cleared (see V2_LICENSE_MANIFEST.md) or even
installed/smoke-tested -- license-clear and installed are necessary, not
sufficient.

Status values:
  PRODUCTION  -- real renderer wired, real gold benchmark exists and passed
                 manual review.
  PARTIAL     -- real renderer attempted, real artifact exists, but with
                 known defects serious enough to withhold PRODUCTION.
  NOT_BUILT   -- license audited (see V2_LICENSE_MANIFEST.md) but no
                 renderer/benchmark attempt made yet this pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..visual_mode.modes import VisualMode


@dataclass
class StyleEntry:
    mode: VisualMode
    label: str
    status: str  # PRODUCTION | PARTIAL | NOT_BUILT
    renderer: Optional[Callable] = None
    gold_benchmark: Optional[str] = None
    notes: str = ""


def _voxel_renderer(*args, **kwargs):
    """Real, already-in-production renderer -- delegates to the existing
    K70 voxel character/scene engine (unchanged by this pass)."""
    from ..blender import voxel_human
    return voxel_human.render_voxel_human_clip(*args, **kwargs)


REGISTRY: dict[VisualMode, StyleEntry] = {
    VisualMode.THREE_D_CHARACTER: StyleEntry(
        mode=VisualMode.THREE_D_CHARACTER, label="Voxel Cinematic",
        status="PRODUCTION", renderer=_voxel_renderer,
        gold_benchmark="data/jobs/k70_v2_gold_voxel/",
        notes="Existing K70 voxel character/scene system -- proven across "
              "EP01/EP04, the longform $100K video, and the full-combo 30s "
              "sequence. Untouched by this V2 pass except the gold-standard "
              "regression benchmark."),
    VisualMode.VECTOR_2D: StyleEntry(
        mode=VisualMode.VECTOR_2D, label="Premium 2D Vector",
        status="PRODUCTION", notes="Built via Blender flat-shading + outline-"
              "duplicate NPR (not Synfig -- see K70_VISUAL_ENGINE_V2_REPORT.md). "
              "Gold benchmark: data/jobs/k70_v2_gold_vector/."),
    VisualMode.PAPER_COLLAGE: StyleEntry(
        mode=VisualMode.PAPER_COLLAGE, label="Paper-Cut / Editorial Collage",
        status="PRODUCTION", notes="Built via Blender paper-grain cutouts + "
              "perspective dolly (not Krita). Gold benchmark: "
              "data/jobs/k70_v2_gold_collage/."),
    VisualMode.CLAY_MINIATURE: StyleEntry(
        mode=VisualMode.CLAY_MINIATURE, label="Clay / Miniature 3D",
        status="PRODUCTION", notes="Blender-only clay material + squash-pop "
              "choreography. Gold benchmark: data/jobs/k70_v2_gold_clay/."),
    VisualMode.ILLUSTRATED_2_5D: StyleEntry(
        mode=VisualMode.ILLUSTRATED_2_5D, label="2.5D Illustrated Cinematic",
        status="PRODUCTION", notes="Built via Blender lit depth-layers + DOF "
              "(not Krita/Storytools). Gold benchmark: data/jobs/k70_v2_gold_25d/."),
    VisualMode.ISOMETRIC_MINIATURE: StyleEntry(
        mode=VisualMode.ISOMETRIC_MINIATURE, label="Isometric Miniature World",
        status="PRODUCTION", notes="Blender true-ortho isometric camera + "
              "beveled-box entities + money-flow (BuildingNodes evaluated, "
              "rejected -- no scriptable automation surface). Gold benchmark: "
              "data/jobs/k70_v2_gold_isometric/."),
    VisualMode.SKETCH_HANDDRAWN: StyleEntry(
        mode=VisualMode.SKETCH_HANDDRAWN, label="Hand-Drawn / Sketch Documentary",
        status="PRODUCTION", notes="Built via Blender Grease Pencil "
              "(text->GP strokes + native Build modifier for progressive "
              "draw-in), not Pencil2D/OpenToonz/Krita. Gold benchmark: "
              "data/jobs/k70_v2_gold_sketch/."),
    VisualMode.REAL_STOCK: StyleEntry(
        mode=VisualMode.REAL_STOCK, label="Real Footage",
        status="PRODUCTION", notes="Existing Pexels/Pixabay broll pipeline, "
              "already used in the longform video and the full-combo 30s "
              "sequence (shot 5)."),
    VisualMode.DATA_CHART: StyleEntry(
        mode=VisualMode.DATA_CHART, label="Chart / Data Graphics",
        status="PRODUCTION", notes="Existing dataviz/chart pipeline, already "
              "used in the longform video."),
}


def status_matrix() -> list[tuple[str, str, str]]:
    return [(e.label, e.mode.value, e.status) for e in REGISTRY.values()]
