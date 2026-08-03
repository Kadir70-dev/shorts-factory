#!/usr/bin/env python3
"""Render a small Phase 1 sample without invoking production narration.

The audio is an explicit NON-PRODUCTION timing fixture made from an existing SFX
asset. It is wired only into this developer script and cannot activate through
the API worker, CLI producer, or TTS module.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def test_audio(path: Path, seconds: float) -> None:
    source = ROOT / "data" / "assets" / "sfx" / "riser.wav"
    if not source.is_file():
        raise RuntimeError(
            "NON-PRODUCTION test fixture source is missing: data/assets/sfx/riser.wav")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1",
        "-i", str(source), "-t", f"{seconds:.3f}", "-af",
        "loudnorm=I=-26:TP=-6:LRA=4", "-ar", "44100", "-ac", "1",
        "-c:a", "pcm_s16le", "-y", str(path),
    ], check=True)


async def main() -> int:
    from app.brand import load_theme
    from app.config import settings
    from app.pipeline import dataviz, motiongfx, render_ffmpeg, scene_director as sd
    from app.schemas.scene import DataPoint, DataViz, Scene, SceneGraph, SceneMeta
    from app.schemas.video_spec import Niche, VideoSpec

    out_dir = ROOT / "output" / "phase1_visual_intelligence"
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = SceneGraph(
        meta=SceneMeta(video_id="phase1_visual_sample", channel_id="k70_business",
                       niche="usa_business", title="Phase 1 Visual Intelligence",
                       hook="The number behind the headline"),
        width=360, height=640, fps=24, brand_id="k70",
        scenes=[
            Scene(id="s1", narration="Revenue rose from two to four billion dollars.",
                  duration_sec=1.8, beat_role="evidence",
                  data=DataViz(kind="bar_compare", title="Revenue",
                               points=[DataPoint(label="Before", value=2),
                                       DataPoint(label="After", value=4, highlight=True)],
                               prefix="$", suffix="B", source="Test fixture")),
            Scene(id="s2", narration="The mechanism was hidden in plain sight.",
                  duration_sec=1.8, beat_role="mechanism"),
            Scene(id="s3", narration="Follow for the systems behind the numbers.",
                  duration_sec=1.8, beat_role="cta"),
        ],
    )
    graph.scenes[1].visual.scene_visual_type = "abstract"
    graph.scenes[2].visual.scene_visual_type = "subtle"
    spec = VideoSpec(channel_id="k70_business", niche=Niche.business,
                     topic=graph.meta.title, allow_ai_image=False,
                     allow_ai_video=False)
    settings().visual_intelligence_enabled = True
    report = sd.decide(graph, spec)
    if report.comparison is None:
        raise RuntimeError("Phase 1 comparison did not run")

    theme = load_theme("k70")
    for index, scene in enumerate(graph.scenes):
        asset = out_dir / f"visual_{index:02d}.mp4"
        if scene.visual.type == "dataviz":
            await dataviz.render(scene.data, theme, asset, graph.width, graph.height,
                                 graph.fps, scene.duration_sec)
        elif scene.visual.type == "motion_gfx":
            await motiongfx.kinetic(
                theme, asset, graph.width, graph.height, graph.fps,
                scene.duration_sec, scene.narration, seed=index)
        else:
            await motiongfx.plate(theme, asset, graph.width, graph.height,
                                  graph.fps, scene.duration_sec, seed=index)
            scene.visual.type = "branded"
        scene.visual.asset_path = str(asset)

    fixture = out_dir / "NON_PRODUCTION_TEST_AUDIO.wav"
    test_audio(fixture, graph.total_duration_sec)
    graph.audio.voiceover_path = str(fixture)
    final = out_dir / "phase1-sample.mp4"
    started = time.perf_counter()
    await render_ffmpeg.render(graph, final)
    elapsed = time.perf_counter() - started
    if not final.is_file() or final.stat().st_size < 10_000:
        raise RuntimeError("sample render is missing or empty")
    print(f"sample={final}")
    print(f"render_seconds={elapsed:.3f}")
    print(f"decision_score={report.comparison.existing.score:.2f}→"
          f"{report.comparison.enhanced.score:.2f}")
    print("audio=NON-PRODUCTION SFX timing fixture; production TTS untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
