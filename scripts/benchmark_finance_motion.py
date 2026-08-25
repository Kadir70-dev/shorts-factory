#!/usr/bin/env python3
"""Offline preview benchmark for all ten validated finance motion templates."""
from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def cases():
    from app.schemas.scene import StoryboardScene
    base = dict(scene_id="s1.b1", source_scene_id="s1", duration_estimate=.8,
                primary_entity="Acme", company="Acme",
                recommended_visual_type="motion_gfx", motion_graphics_needed=True,
                threejs_candidate=True, asset_priority=["local_graphics"],
                visual_confidence_score=.95)
    data = [
        ("stat_card", "Revenue reached $4.2 billion.", ["$4.2 billion"], None, []),
        ("bar_chart_comparison", "Revenue compares at $10M and $6M.", ["$10M", "$6M"], None, []),
        ("percentage_split", "Founders own a 35% stake and investors own 65%.", ["35%", "65%"], None, []),
        ("timeline_events", "Since 1985 the timeline crossed milestones.", [], 1985, []),
        ("before_after", "Before $4M and after $9M.", ["$4M", "$9M"], None, []),
        ("revenue_profit_waterfall", "Revenue and profit waterfall: $10M and $4M.", ["$10M", "$4M"], None, []),
        ("price_inflation", "Price inflation moved from $2 to $3.", ["$2", "$3"], None, []),
        ("document_highlight", "The 2024 SEC annual report document showed $8M.", ["$8M"], 2024, []),
        ("quote_card", 'The CEO said “discipline compounds.”', [], None, []),
        ("company_ecosystem", "The company ecosystem links suppliers and its platform.", [], None,
         ["Supplier One", "Platform Two", "Retailers"]),
    ]
    return [(name, StoryboardScene(**base, narration=text, visual_objective=text,
                                   financial_numbers=values, year=year,
                                   secondary_entities=secondary))
            for name, text, values, year, secondary in data]


async def main() -> int:
    from app.config import settings
    from app.pipeline import finance_motion
    from app.schemas.scene import Scene, SceneGraph, SceneMeta

    rows = []
    with tempfile.TemporaryDirectory(prefix="motion-benchmark-") as temp:
        settings().data_dir = Path(temp)
        first_hash = ""
        all_cases = cases()
        for index, (expected, candidate) in enumerate(all_cases):
            scene = Scene(id="s1", narration=candidate.narration, duration_sec=.8)
            graph = SceneGraph(meta=SceneMeta(
                video_id=f"motion_{expected}", channel_id="k70_business",
                niche="usa_finance", title=expected, hook=expected),
                width=1080, height=1920, fps=30, scenes=[scene])
            result = await finance_motion.render(
                graph, scene, candidate, quality="preview", seed=500 + index)
            if result.status == "unresolved" or result.template != expected:
                raise RuntimeError(f"{expected}: {result.error or result.template}")
            output = Path(result.render_path)
            rows.append({"template": expected, "render_ms": round(result.render_ms, 1),
                         "process_rss_mb": round(result.peak_rss_mb, 1),
                         "bytes": output.stat().st_size})
            if index == 0:
                first_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        # Encoded determinism in a fresh cache root.
        expected, candidate = all_cases[0]
        settings().data_dir = Path(temp) / "repeat"
        scene = Scene(id="s1", narration=candidate.narration, duration_sec=.8)
        graph = SceneGraph(meta=SceneMeta(
            video_id=f"motion_{expected}", channel_id="k70_business",
            niche="usa_finance", title=expected, hook=expected),
            width=1080, height=1920, fps=30, scenes=[scene])
        repeat = await finance_motion.render(
            graph, scene, candidate, quality="preview", seed=500)
        deterministic = first_hash == hashlib.sha256(
            Path(repeat.render_path).read_bytes()).hexdigest()
    report = {
        "mode": "preview", "resolution": "360x640", "fps": 30,
        "duration_per_template_sec": .8, "templates": rows,
        "median_render_ms": round(statistics.median(row["render_ms"] for row in rows), 1),
        "peak_process_rss_mb": max(row["process_rss_mb"] for row in rows),
        "deterministic_encoded_output": deterministic,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
