#!/usr/bin/env python3
"""Offline latency and query-specificity benchmark for Phase 3."""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def run_benchmark(iterations: int) -> dict:
    from app.pipeline import asset_engine, scene_director, storyboard
    from app.schemas.scene import AssetCandidate, SceneGraph
    from app.schemas.video_spec import Niche, VideoSpec

    rows = []
    with tempfile.TemporaryDirectory(prefix="phase3-bench-") as temp:
      cache_dir = Path(temp)

      async def fetch(provider, query, beat):
        if provider != "government_public_domain":
            return []
        return [AssetCandidate(
            source_url=f"https://fixture.gov/{beat.scene_id}.jpg",
            provider_institution=provider, asset_type="image",
            license="Public Domain", commercial_use_status="allowed",
            retrieval_date="2026-08-03", scene_id=beat.scene_id,
            relevance_score=.9, confidence=.9, subject_specificity=.9,
            visual_quality=.8, originality=.8, mobile_readability=.9)]

      async def download(candidate, target):
        target.write_bytes(b"offline benchmark fixture")
        return target

      for path in sorted((ROOT / "data" / "demos").glob("fin_*.json")):
        base = SceneGraph.model_validate_json(path.read_text())
        spec = VideoSpec(channel_id=base.meta.channel_id,
                         niche=Niche(base.meta.niche), topic=base.meta.title,
                         allow_ai_image=False, allow_ai_video=False)
        report = scene_director._decide_existing(base.model_copy(deep=True), spec)
        base.storyboard = storyboard.generate_semantic(base, report)
        elapsed, fact_hits = [], []
        for _ in range(iterations):
            graph = base.model_copy(deep=True)
            started = time.perf_counter()
            await asset_engine.resolve(graph, fetch, download, cache_dir)
            elapsed.append((time.perf_counter() - started) * 1000)
            for beat, record in zip(graph.storyboard.scenes, graph.asset_provenance):
                facts = [beat.company, beat.location, str(beat.year or ""),
                         *beat.financial_numbers]
                facts = [fact.lower() for fact in facts if fact]
                fact_hits.append(sum(fact in record.query.lower() for fact in facts)
                                 / len(facts) if facts else 1.0)
        ordered = sorted(elapsed)
        rows.append({
            "fixture": path.name, "beats": len(base.storyboard.scenes),
            "median_ms": round(statistics.median(elapsed), 3),
            "p95_ms": round(ordered[int((len(ordered) - 1) * .95)], 3),
            "structured_fact_coverage": round(statistics.mean(fact_hits), 3),
        })
    return {
        "iterations": iterations, "fixtures": rows,
        "mean_median_ms": round(statistics.mean(r["median_ms"] for r in rows), 3),
        "mean_fact_coverage": round(statistics.mean(
            r["structured_fact_coverage"] for r in rows), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")

    result = asyncio.run(run_benchmark(args.iterations))
    print(json.dumps(result, indent=2) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
