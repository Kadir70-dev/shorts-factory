"""Finance long-form: priority for sourced charts and already-discovered archives.

Opt-in via real long-form SceneGraph characteristics, never global visual budget.
No I/O, model calls, downloads, changing layer counts, or fabrication.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Keep in sync with the source resolver license policy (not a new license grant).
ARCHIVE_PROVIDERS = frozenset({"wikimedia_commons", "government_public_domain",
                               "sec_regulatory", "company_ir"})
RENDERABLE = frozenset({".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"})


def is_finance_longform(graph: Any) -> bool:
    """Conservative scope: finance, landscape, >=20 beats, >=4 minutes."""
    meta = getattr(graph, "meta", None)
    scenes = getattr(graph, "scenes", ())
    return (getattr(meta, "niche", "") == "usa_finance"
            and int(getattr(graph, "width", 0)) > int(getattr(graph, "height", 0))
            and len(scenes) >= 20
            and sum(float(s.duration_sec) for s in scenes) >= 240)


def authored_chart_ids(graph: Any) -> set[str]:
    """Pin explicit authored sourced charts only; never guess missing data."""
    if not is_finance_longform(graph):
        return set()
    return {s.id for s in graph.scenes
            if s.visual.type == "dataviz" and s.data is not None
            and s.data.valid() and bool(s.data.source.strip())}


def archive_choice(graph: Any, scene_id: str, path: str) -> dict | None:
    """Accept already-selected institutional/licensed media, not arbitrary stock.

    The multi-source engine performs actual discovery/license validation.
    We independently require selected URL, legal+commercial fields and scores.
    No candidate is accepted merely because it appears among search results.
    """
    if not is_finance_longform(graph) or not path:
        return None
    storyboard = getattr(graph, "storyboard", None)
    beat_ids = {beat.scene_id for beat in getattr(storyboard, "scenes", ())
                if beat.source_scene_id == scene_id}
    for record in getattr(graph, "asset_provenance", ()):
        if record.scene_id not in beat_ids or record.status != "resolved":
            continue
        for c in record.candidates:
            if (c.source_url != record.selected_source_url
                    or c.provider_institution not in ARCHIVE_PROVIDERS
                    or c.commercial_use_status != "allowed"
                    or not c.local_cache_path
                    or Path(c.local_cache_path) != Path(path)
                    or Path(path).suffix.lower() not in RENDERABLE
                    or c.relevance_score < 0.75
                    or c.subject_specificity < 0.65
                    or c.confidence < 0.5):
                continue
            # License legality comes from the established asset engine. Its
            # eligibility floor alone is weaker than our subject threshold.
            from .asset_engine import legal
            if not legal(c):
                continue
            return {"scene_id": scene_id, "source_url": c.source_url,
                    "license": c.license,
                    "attribution_requirement": c.attribution_requirement,
                    "provider": c.provider_institution}
    return None
