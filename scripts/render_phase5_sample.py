#!/usr/bin/env python3
"""Four-template Phase 5 sample with explicit non-production timing audio."""
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
    from app.pipeline import broll, render_ffmpeg
    from app.schemas.scene import Scene, SceneGraph, SceneMeta
    from app.schemas.video_spec import Niche, VideoSpec

    out = ROOT / "output" / "phase5_finance_motion"
    out.mkdir(parents=True, exist_ok=True)
    lines = [
        "Revenue reached $4.2 billion.",
        "Before revenue was $4 million and after it was $9 million.",
        "The 2024 SEC annual report document showed $8 million.",
        "Price inflation moved from $2 to $3.",
    ]
    scenes = [Scene(id=f"s{i + 1}", narration=line, duration_sec=.8,
                    beat_role="evidence") for i, line in enumerate(lines)]
    for scene in scenes:
        scene.visual.visual_intent = scene.narration
        scene.visual.scene_visual_type = "data_viz"
    graph = SceneGraph(meta=SceneMeta(
        video_id="phase5_motion_sample", channel_id="k70_business",
        niche="usa_finance", title="Four Finance Motion Templates",
        hook="Make every number visible"), width=360, height=640, fps=30,
        scenes=scenes, brand_id="k70")
    settings().visual_intelligence_enabled = True
    settings().storyboard_engine_enabled = True
    settings().multi_source_asset_engine_enabled = False
    settings().threejs_visual_engine_enabled = True
    settings().motion_graphics_engine_enabled = True
    settings().motion_graphics_quality = "preview"
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.finance, topic=graph.meta.title,
        allow_ai_image=False, allow_ai_video=False))
    templates = {record.template for record in graph.motion_graphics_provenance
                 if record.status in ("rendered", "cache_hit")}
    if len(templates) < 4 or any(scene.visual.type != "motion_gfx" for scene in scenes):
        detail = [(record.scene_id, record.template, record.status)
                  for record in graph.motion_graphics_provenance]
        raise RuntimeError(f"expected four distinct 2D templates, got {detail}")
    if graph.threejs_provenance:
        raise RuntimeError("Three.js ran despite an equally clear 2D mapping")

    audio = out / "NON_PRODUCTION_TEST_AUDIO.wav"
    fixture = ROOT / "data" / "assets" / "sfx" / "riser.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(fixture), "-t",
        str(graph.total_duration_sec), "-ar", "44100", "-ac", "1", "-y",
        str(audio)], check=True)
    graph.audio.voiceover_path = str(audio)
    target = out / "phase5-motion-sample.mp4"
    started = time.perf_counter()
    await render_ffmpeg.render(graph, target)
    if not target.is_file() or target.stat().st_size < 10_000:
        raise RuntimeError("sample render missing or empty")
    print(f"sample={target}")
    print(f"templates={','.join(sorted(templates))}")
    print(f"render_seconds={time.perf_counter() - started:.3f}")
    print("audio=NON-PRODUCTION SFX timing fixture; production TTS untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
