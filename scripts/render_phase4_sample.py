#!/usr/bin/env python3
"""Render three real Three.js templates with explicit non-production audio."""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> int:
    from app.config import settings
    from app.pipeline import broll, render_ffmpeg, threejs_engine
    from app.schemas.scene import Scene, SceneGraph, SceneMeta
    from app.schemas.video_spec import Niche, VideoSpec

    out = ROOT / "output" / "phase4_threejs"
    out.mkdir(parents=True, exist_ok=True)
    scenes = [
        Scene(id="s1", narration="Revenue reached $4.2 billion.",
              duration_sec=.8, beat_role="evidence"),
        Scene(id="s2", narration="Founders own a 35% stake while investors own 65%.",
              duration_sec=.8, beat_role="mechanism"),
        Scene(id="s3", narration="Ten percent compounded growth changes the curve.",
              duration_sec=.8, beat_role="reveal"),
    ]
    for scene in scenes:
        scene.visual.visual_intent = scene.narration
        scene.visual.scene_visual_type = "abstract"
    graph = SceneGraph(meta=SceneMeta(
        video_id="phase4_threejs_sample", channel_id="k70_business",
        niche="usa_finance", title="Three Finance Visuals",
        hook="See the numbers move"), width=360, height=640, fps=30,
        scenes=scenes, brand_id="k70")
    settings().visual_intelligence_enabled = True
    settings().storyboard_engine_enabled = True
    settings().multi_source_asset_engine_enabled = False
    settings().threejs_visual_engine_enabled = True
    settings().threejs_quality = "preview"
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.finance, topic=graph.meta.title,
        allow_ai_image=False, allow_ai_video=False))
    templates = {record.template for record in graph.threejs_provenance
                 if record.status in ("rendered", "cache_hit")}
    if len(templates) < 3 or any(scene.visual.type != "threejs" for scene in scenes):
        raise RuntimeError(f"expected three distinct Three.js visuals, got {templates}")

    audio = out / "NON_PRODUCTION_TEST_AUDIO.wav"
    fixture = ROOT / "data" / "assets" / "sfx" / "riser.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(fixture), "-t",
        str(graph.total_duration_sec), "-ar", "44100", "-ac", "1", "-y",
        str(audio)], check=True)
    graph.audio.voiceover_path = str(audio)
    target = out / "phase4-threejs-sample.mp4"
    started = time.perf_counter()
    await render_ffmpeg.render(graph, target)
    await threejs_engine.close_worker()
    if not target.is_file() or target.stat().st_size < 10_000:
        raise RuntimeError("sample render missing or empty")
    print(f"sample={target}")
    print(f"templates={','.join(sorted(templates))}")
    print(f"render_seconds={time.perf_counter() - started:.3f}")
    print("audio=NON-PRODUCTION SFX timing fixture; production TTS untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
