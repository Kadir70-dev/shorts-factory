#!/usr/bin/env python3
"""Benchmark Phase 1 policies without resolving assets or rendering video."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    from app.pipeline import scene_director as sd
    from app.schemas.scene import SceneGraph
    from app.schemas.video_spec import Niche, VideoSpec

    rows = []
    for path in sorted((ROOT / "data" / "demos").glob("fin_*.json")):
        graph = SceneGraph.model_validate_json(path.read_text())
        spec = VideoSpec(channel_id=graph.meta.channel_id,
                         niche=Niche(graph.meta.niche), topic=graph.meta.title,
                         allow_ai_image=False, allow_ai_video=False)
        runs = [sd.compare(graph, spec) for _ in range(args.iterations)]
        first = runs[0]
        rows.append({
            "fixture": path.name,
            "scenes": len(graph.scenes),
            "changed_scenes": list(first.changed_scenes),
            "existing_score": first.existing.score,
            "enhanced_score": first.enhanced.score,
            "score_delta": first.score_delta,
            "existing_median_ms": round(statistics.median(r.existing_ms for r in runs), 3),
            "enhanced_median_ms": round(statistics.median(r.enhanced_ms for r in runs), 3),
        })
    if not rows:
        raise RuntimeError("no fin_*.json benchmark fixtures found")
    summary = {
        "iterations": args.iterations,
        "fixtures": rows,
        "mean_score_delta": round(statistics.mean(row["score_delta"] for row in rows), 2),
        "mean_enhanced_ms": round(statistics.mean(row["enhanced_median_ms"] for row in rows), 3),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for row in rows:
            print(f"{row['fixture']}: {row['existing_score']:.1f} → "
                  f"{row['enhanced_score']:.1f} ({row['score_delta']:+.1f}); "
                  f"enhanced {row['enhanced_median_ms']:.3f}ms; "
                  f"changed={','.join(row['changed_scenes']) or 'none'}")
        print(f"mean delta {summary['mean_score_delta']:+.2f}; "
              f"mean enhanced latency {summary['mean_enhanced_ms']:.3f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
