#!/usr/bin/env python3
"""Render all six Phase 4 templates through one reusable browser worker."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def templates():
    from app.schemas.scene import StoryboardScene
    base = dict(scene_id="s1.b1", source_scene_id="s1", duration_estimate=.8,
                primary_entity="K70 Finance", recommended_visual_type="dataviz",
                motion_graphics_needed=True, threejs_candidate=True,
                asset_priority=["local_graphics"], visual_confidence_score=.95)
    cases = [
        ("number_counter", "Revenue reached $4.2 billion.", ["$4.2 billion"], None),
        ("comparison_towers", "Revenue compared with profit: $10M and $4M.", ["$10M", "$4M"], None),
        ("share_ownership", "Founders own a 35% stake and investors own 65%.", ["35%", "65%"], None),
        ("dividend_cashflow", "Dividend cash flow reached $2 million.", ["$2 million"], None),
        ("timeline_flythrough", "Since 1985 the company crossed five milestones.", [], 1985),
        ("compound_growth", "Ten percent compounded growth doubles capital over time.", ["10 percent"], None),
    ]
    return [(name, StoryboardScene(**base, narration=text, visual_objective=text,
                                   financial_numbers=values, year=year))
            for name, text, values, year in cases]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    from app.config import settings
    from app.pipeline import threejs_engine
    from app.schemas.scene import Scene, SceneGraph, SceneMeta

    rows = []
    deterministic = False
    with tempfile.TemporaryDirectory(prefix="threejs-benchmark-") as temp:
        settings().data_dir = Path(temp)
        settings().threejs_render_timeout_s = 180
        cases = templates()
        first_hash = ""
        for index, (expected, beat) in enumerate(cases):
            scene = Scene(id="s1", narration=beat.narration, duration_sec=.8)
            graph = SceneGraph(meta=SceneMeta(
                video_id=f"benchmark_{expected}", channel_id="k70_business",
                niche="usa_finance", title=expected, hook=expected),
                width=1080, height=1920, fps=30, scenes=[scene])
            result = await threejs_engine.render(
                graph, scene, beat, quality="preview", seed=700 + index)
            if result.status == "unresolved" or result.template != expected:
                raise RuntimeError(f"{expected}: {result.error or result.template}")
            rows.append({"template": expected, "render_ms": round(result.render_ms, 1),
                         "process_tree_rss_mb": round(result.peak_rss_mb, 1),
                         "bytes": Path(result.render_path).stat().st_size})
            if index == 0:
                first_hash = hashlib.sha256(Path(result.render_path).read_bytes()).hexdigest()
        # Render the warm-up template into a fresh cache root with the same seed.
        # Equality verifies actual encoded output, not merely cache-key stability.
        expected, beat = cases[0]
        settings().data_dir = Path(temp) / "determinism-repeat"
        scene = Scene(id="s1", narration=beat.narration, duration_sec=.8)
        graph = SceneGraph(meta=SceneMeta(
            video_id=f"benchmark_{expected}", channel_id="k70_business",
            niche="usa_finance", title=expected, hook=expected),
            width=1080, height=1920, fps=30, scenes=[scene])
        repeated = await threejs_engine.render(
            graph, scene, beat, quality="preview", seed=700)
        deterministic = (repeated.status == "rendered" and first_hash ==
                         hashlib.sha256(Path(repeated.render_path).read_bytes()).hexdigest())
        await threejs_engine.close_worker()
    summary = {
        "mode": "preview", "resolution": "360x640", "fps": 30,
        "duration_per_template_sec": .8, "templates": rows,
        "deterministic_encoded_output": deterministic,
        "median_render_ms": round(statistics.median(r["render_ms"] for r in rows), 1),
        "peak_process_tree_rss_mb": max(r["process_tree_rss_mb"] for r in rows),
    }
    print(json.dumps(summary, indent=2) if args.json else summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
