#!/usr/bin/env python3
"""Render a composed 1080x1920 fixture and run the blocking Phase 8 audit."""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> int:
    from app.brand import theme_for
    from app.config import settings
    from app.pipeline import qa
    from app.schemas.scene import (AudioTrack, Caption, Scene, SceneGraph, SceneMeta,
                                   Visual)

    out = ROOT / "output" / "phase8_visual_qa"
    out.mkdir(parents=True, exist_ok=True)
    audio = out / "NON_PRODUCTION_TEST_AUDIO.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "sine=frequency=330:sample_rate=48000", "-t", "3", "-af",
        "volume=-8dB", "-ar", "48000", "-ac", "1", "-y", str(audio)], check=True)

    narration = "Revenue rose ten percent as margins improved."
    graph = SceneGraph(meta=SceneMeta(video_id="phase8_production_sample",
        channel_id="k70_business", niche="finance", title="Revenue and Margins",
        hook="THE NUMBER MOVED", description="A K70 Finance production QA sample.",
        tags=["finance", "revenue", "shorts"], hashtags=["#finance", "#shorts"],
        thumbnail_text="THE NUMBER MOVED"), fps=30, width=1080, height=1920,
        scenes=[Scene(id="s1", narration=narration, duration_sec=3,
            visual=Visual(type="motion_gfx"), beat_role="evidence")],
        captions=[Caption(start=0, end=1.45, text="REVENUE ROSE TEN PERCENT"),
                  Caption(start=1.5, end=2.85, text="AS MARGINS IMPROVED")],
        audio=AudioTrack(voiceover_path=str(audio)), brand_id="k70")
    settings().brand_identity_enabled = True
    settings().visual_qa_engine_enabled = True
    theme = theme_for(graph, "compositor")
    started = time.perf_counter()
    final_mp4 = out / "phase8-production-sample.mp4"
    thumb = out / "thumbnail.jpg"
    metadata = out / "metadata.json"
    # Local moving fixture with the K70 safe-area bars; it exercises the complete
    # export contract without invoking or substituting any production voice.
    vf = ("drawbox=x=0:y=0:w=iw:h=150:color=0x0b1220@0.88:t=fill,"
          "drawbox=x=60:y=170:w=960:h=7:color=0xf5b301:t=fill,"
          f"drawtext=text='K70 FINANCE':fontfile={theme.display.path}:fontsize=46:"
          "fontcolor=0xf5b301:x=60:y=62,"
          f"drawtext=text='REVENUE MOMENTUM':fontfile={theme.display.path}:fontsize=76:"
          "fontcolor=0xf4f6fb:x=(w-text_w)/2:y=500,"
          f"drawtext=text='10%':fontfile={theme.mono.path}:expansion=none:fontsize=260:"
          "fontcolor=0xf5b301:x=(w-text_w)/2:y=730,"
          f"drawtext=text='MARGIN EXPANSION':fontfile={theme.body.path}:fontsize=52:"
          "fontcolor=0xa8b3c7:x=(w-text_w)/2:y=1050")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "gradients=size=1080x1920:rate=30:c0=0x0b1220:c1=0x141d31:"
              "c2=0x22304d:nb_colors=3:speed=0.08:type=radial", "-i", str(audio), "-t", "3",
        "-vf", vf,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=7", "-c:v", "libx264", "-preset",
        "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-ar", "48000", "-b:a", "192k", "-movflags", "+faststart", "-y", str(final_mp4)], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "0.6",
        "-i", str(final_mp4), "-frames:v", "1", "-y", str(thumb)], check=True)
    metadata.write_text(graph.meta.model_dump_json(indent=2))
    report_path = out / "phase8-production-sample.qa.json"
    report = qa.production_analyze(graph, str(final_mp4), thumbnail=str(thumb),
        metadata_path=str(metadata), report_path=str(report_path))
    print(f"sample={final_mp4}")
    print(f"report={report_path}")
    print(f"status={report.status}")
    print(f"checks={len(report.checks)}")
    print(f"qa_runtime_ms={report.runtime_ms:.1f}")
    print(f"total_runtime_seconds={time.perf_counter()-started:.3f}")
    print("audio=NON-PRODUCTION timing fixture; production voice untouched")
    if report.status == "FAIL":
        print(qa.format_production_report(report))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
