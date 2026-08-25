"""The visual-mode vocabulary a long-form narration beat can be rendered
with (brief section 10). This is intentionally a superset of the existing
production pipeline's channels (`apps/api/app/pipeline/visual_budget.py`'s
CHANNELS) -- MOTION_GRAPHIC/DATA_CHART/REAL_STOCK/REAL_IMAGE/AI_IMAGE/
AI_VIDEO map straight onto the existing mgfx/chart/stock/archival/ai
channels so the existing storyboard keeps working untouched; the new
values (3D_CHARACTER, 3D_ENVIRONMENT, PROCEDURAL_CITY, VOXEL_STORY) are
what this engine adds.
"""
from __future__ import annotations

from enum import Enum


class VisualMode(str, Enum):
    REAL_STOCK = "REAL_STOCK"
    REAL_IMAGE = "REAL_IMAGE"
    THREE_D_CHARACTER = "3D_CHARACTER"
    THREE_D_ENVIRONMENT = "3D_ENVIRONMENT"
    PROCEDURAL_CITY = "PROCEDURAL_CITY"
    VOXEL_STORY = "VOXEL_STORY"
    MOTION_GRAPHIC = "MOTION_GRAPHIC"
    DATA_CHART = "DATA_CHART"
    AI_IMAGE = "AI_IMAGE"
    AI_VIDEO = "AI_VIDEO"

    # K70 Visual Engine V2 (multi-style documentary director, brief
    # 2026-08-23) -- one new mode per style NOT already covered by the
    # voxel/3D modes above. VOXEL_CINEMATIC itself reuses THREE_D_CHARACTER/
    # VOXEL_STORY/PROCEDURAL_CITY unchanged, no new enum needed for it.
    VECTOR_2D = "VECTOR_2D"
    PAPER_COLLAGE = "PAPER_COLLAGE"
    CLAY_MINIATURE = "CLAY_MINIATURE"
    ILLUSTRATED_2_5D = "ILLUSTRATED_2_5D"
    ISOMETRIC_MINIATURE = "ISOMETRIC_MINIATURE"
    SKETCH_HANDDRAWN = "SKETCH_HANDDRAWN"

    @property
    def requires_blender(self) -> bool:
        return self in (VisualMode.THREE_D_CHARACTER, VisualMode.THREE_D_ENVIRONMENT,
                        VisualMode.PROCEDURAL_CITY, VisualMode.VOXEL_STORY,
                        VisualMode.CLAY_MINIATURE, VisualMode.ILLUSTRATED_2_5D,
                        VisualMode.ISOMETRIC_MINIATURE)

    @property
    def existing_pipeline_channel(self) -> str | None:
        """The `apps/api/app/pipeline` channel this mode maps onto when it
        does NOT require the scene engine (i.e. the existing render path
        can produce it unmodified). None for the four new 3D/voxel modes."""
        return {
            VisualMode.REAL_STOCK: "stock",
            VisualMode.REAL_IMAGE: "official",
            VisualMode.MOTION_GRAPHIC: "motion_gfx",
            VisualMode.DATA_CHART: "charts",
            VisualMode.AI_IMAGE: "ai_broll",
            VisualMode.AI_VIDEO: "ai_broll",
        }.get(self)
