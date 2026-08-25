#!/usr/bin/env python3
"""Offline Phase 6 prompt, adapter dispatch, cache, and memory benchmark."""
from __future__ import annotations

import asyncio
import json
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> int:
    from app.config import settings
    from app.pipeline import ai_broll
    from app.schemas.scene import Scene, SceneGraph, SceneMeta, StoryboardScene

    with tempfile.TemporaryDirectory(prefix="ai-broll-benchmark-") as temp:
        root = Path(temp); settings().data_dir = root
        source = root / "provider.png"; source.write_bytes(b"fixture synthetic image")

        class Adapter:
            name = "benchmark_adapter"
            def available(self): return True
            def model(self): return "benchmark-v1"
            async def generate(self, prompt, scene, quality):
                return ai_broll.GeneratedAsset(str(source), self.model(), "image")

        ai_broll.register_provider(Adapter())
        settings().ai_broll_provider_priority = "benchmark_adapter"
        beat = StoryboardScene(
            scene_id="s1.b1", source_scene_id="s1",
            narration="Show an original symbolic supply-chain bottleneck.",
            duration_estimate=.8, visual_objective="A port bottleneck slowing trade",
            primary_entity="Supply chain", secondary_entities=["Port", "Factory"],
            company="Acme", location="United States", year=2024,
            emotion="tense", recommended_visual_type="ai_image",
            ai_broll_candidate=True, asset_priority=["ai_recreation"],
            visual_confidence_score=.85)
        scene = Scene(id="s1", narration=beat.narration, duration_sec=.8)
        graph = SceneGraph(meta=SceneMeta(
            video_id="prompt_benchmark", channel_id="k70_business",
            niche="usa_finance", title="AI benchmark", hook="Supply chain"),
            width=360, height=640, fps=30, scenes=[scene])

        prompt_times = []
        for _ in range(1000):
            started = time.perf_counter()
            ai_broll.prompt_spec(graph, scene, beat)
            prompt_times.append((time.perf_counter() - started) * 1000)

        dispatch_times = []
        for index in range(50):
            graph.meta.video_id = f"dispatch_{index}"
            result = await ai_broll.generate(graph, scene, beat, quality="preview")
            dispatch_times.append(result.provider_dispatch_ms)

        graph.meta.video_id = "cache_benchmark"
        statuses = []
        for _ in range(100):
            statuses.append((await ai_broll.generate(
                graph, scene, beat, quality="preview")).status)
        hit_rate = statuses.count("cache_hit") / len(statuses)

    report = {
        "prompt_iterations": 1000,
        "prompt_median_ms": round(statistics.median(prompt_times), 4),
        "prompt_p95_ms": round(sorted(prompt_times)[949], 4),
        "dispatch_iterations": 50,
        "adapter_dispatch_median_ms": round(statistics.median(dispatch_times), 4),
        "adapter_dispatch_p95_ms": round(sorted(dispatch_times)[47], 4),
        "cache_requests": 100,
        "cache_hit_rate": round(hit_rate, 3),
        "peak_process_rss_mb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "network": "mocked/local fixture",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
