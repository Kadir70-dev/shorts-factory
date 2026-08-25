#!/usr/bin/env python3
"""Measure validated semantic-storyboard generation on fixed demo graphs."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    from app.pipeline import scene_director as sd
    from app.pipeline import storyboard
    from app.schemas.scene import SceneGraph
    from app.schemas.video_spec import Niche, VideoSpec

    fixtures = []
    for path in sorted((ROOT / "data" / "demos").glob("fin_*.json")):
        graph = SceneGraph.model_validate_json(path.read_text())
        spec = VideoSpec(channel_id=graph.meta.channel_id,
                         niche=Niche(graph.meta.niche), topic=graph.meta.title,
                         allow_ai_image=False, allow_ai_video=False)
        decisions = sd._decide_existing(graph.model_copy(deep=True), spec)
        elapsed: list[float] = []
        generated = None
        for _ in range(args.iterations):
            started = time.perf_counter()
            generated = storyboard.generate_semantic(graph, decisions)
            elapsed.append((time.perf_counter() - started) * 1000.0)
        complete = sum(
            bool(scene.scene_id and scene.narration and scene.visual_objective
                 and scene.asset_priority)
            for scene in generated.scenes)
        fixtures.append({
            "fixture": path.name,
            "source_scenes": len(graph.scenes),
            "semantic_beats": len(generated.scenes),
            "complete_beats": complete,
            "median_ms": round(statistics.median(elapsed), 3),
            "p95_ms": round(percentile(elapsed, .95), 3),
        })
    if not fixtures:
        raise RuntimeError("no fin_*.json benchmark fixtures found")
    summary = {
        "iterations": args.iterations,
        "fixtures": fixtures,
        "mean_median_ms": round(statistics.mean(row["median_ms"]
                                                 for row in fixtures), 3),
        "all_beats_complete": all(row["semantic_beats"] == row["complete_beats"]
                                  for row in fixtures),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for row in fixtures:
            print(f"{row['fixture']}: {row['source_scenes']} scenes → "
                  f"{row['semantic_beats']} beats; median {row['median_ms']:.3f}ms; "
                  f"p95 {row['p95_ms']:.3f}ms")
        print(f"mean median {summary['mean_median_ms']:.3f}ms; "
              f"complete={summary['all_beats_complete']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
