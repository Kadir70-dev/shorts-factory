#!/usr/bin/env python3
"""Offline Phase 7 Brand Manager overhead benchmark."""
from __future__ import annotations

import json
import resource
import statistics
import time

from app.brand import theme_for
from app.config import settings
from app.schemas.scene import Scene, SceneGraph, SceneMeta


def graph() -> SceneGraph:
    return SceneGraph(meta=SceneMeta(video_id="brand-bench", channel_id="k70_business",
        niche="finance", title="Brand benchmark", hook="Brand benchmark"),
        scenes=[Scene(id="s1", narration="Revenue grew.")])


def measure(enabled: bool, iterations: int = 10_000) -> list[float]:
    settings().brand_identity_enabled = enabled
    g = graph()
    samples = []
    for i in range(iterations):
        started = time.perf_counter_ns()
        theme_for(g, ("motion_graphics", "threejs", "ai_broll", "captions")[i % 4])
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return samples


def main() -> None:
    legacy = measure(False)
    managed = measure(True)
    print(json.dumps({
        "iterations_per_path": len(managed),
        "disabled_median_ms": round(statistics.median(legacy), 5),
        "enabled_median_ms": round(statistics.median(managed), 5),
        "enabled_p95_ms": round(statistics.quantiles(managed, n=20)[18], 5),
        "median_overhead_ms": round(statistics.median(managed) - statistics.median(legacy), 5),
        "peak_process_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "network": "none",
    }, indent=2))


if __name__ == "__main__":
    main()
