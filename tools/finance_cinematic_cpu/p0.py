"""P0 presentation utilities for completed K70 finance SceneGraphs.

No model/API calls. Does not mutate assets, narration, the frozen pipeline, or
the graph. F3 may opt in to timeline-balanced AI still selection.
"""
from __future__ import annotations
from collections import Counter
from typing import Any


def spread_items(graph: Any, candidates: list[dict], limit: int = 8) -> list[dict]:
    """Pick image prompts evenly over the *whole* film rather than the first N.

    Candidate eligibility must already be checked by F3's own safety rules.
    Deterministic, independent of scene IDs and Python hash randomization.
    """
    if not 1 <= limit <= 24:
        raise ValueError("limit must be between 1 and 24")
    if not candidates:
        return []
    mids: dict[str, float] = {}
    time = 0.0
    for scene in graph.scenes:
        duration = float(scene.duration_sec)
        mids[scene.id] = time + duration / 2
        time += duration
    remaining = [item for item in candidates if item.get("scene_id") in mids]
    chosen = []
    if not remaining:
        return []
    count = min(limit, len(remaining))
    for index in range(count):
        # Equal-length chapters ensure eligible illustrations aren't spent on
        # the cold open alone. Avoid picking a second shot close to a selected one.
        target = time * (index + .5) / count
        def rank(item):
            at = mids[item["scene_id"]]
            sep = min((abs(at-mids[s["scene_id"]]) for s in chosen), default=float("inf"))
            penalty = max(0.0, (time / count) * .55 - sep) * 3
            return (abs(at-target)+penalty, at, item["scene_id"])
        pick = min(remaining, key=rank)
        remaining.remove(pick)
        chosen.append(pick)
    return sorted(chosen, key=lambda item: mids[item["scene_id"]])


def timeline_report(graph: Any, *, segments: int = 4) -> dict:
    """Grounded plan-vs-delivery mix; no unsupported availability assertions."""
    if not 2 <= segments <= 12:
        raise ValueError("segments must be between 2 and 12")
    duration = sum(float(s.duration_sec) for s in graph.scenes)
    counts = Counter(s.visual.type for s in graph.scenes)
    planned = Counter(s.visual.budget_channel for s in graph.scenes)
    zones = [{"segment": i+1, "start_sec": round(i*duration/segments, 2),
              "end_sec": round((i+1)*duration/segments, 2),
              "cinematic_count": 0, "threejs_count": 0,
              "motion_card_count": 0} for i in range(segments)]
    now = 0.0
    for scene in graph.scenes:
        midpoint = now + float(scene.duration_sec)/2
        now += float(scene.duration_sec)
        zone = zones[min(segments-1, int(midpoint/max(duration, 1e-6)*segments))]
        if scene.visual.type in ("ai_image", "ai_video"):
            zone["cinematic_count"] += 1
        if scene.visual.type == "threejs":
            zone["threejs_count"] += 1
        if scene.visual.type in ("motion_gfx", "branded"):
            zone["motion_card_count"] += 1
    return {"total_duration_sec": round(duration, 2), "scene_count": len(graph.scenes),
            "actual_types": dict(counts), "allocated_channels": dict(planned),
            "zones": zones}
