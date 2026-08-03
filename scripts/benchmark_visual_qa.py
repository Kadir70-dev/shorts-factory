#!/usr/bin/env python3
"""Benchmark Phase 8 against a good and deliberately broken local fixture."""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.brand import theme_for
from app.config import settings
from app.pipeline import qa
from app.schemas.scene import AudioTrack, Caption, Scene, SceneGraph, SceneMeta, Visual


def graph(media: Path) -> SceneGraph:
    item = SceneGraph(meta=SceneMeta(video_id="qa_benchmark", channel_id="k70_business",
        niche="finance", title="QA Benchmark", hook="Revenue moved",
        description="Benchmark", tags=["finance"], thumbnail_text="REVENUE MOVED"),
        scenes=[Scene(id="s1", narration="Revenue moved ten percent.", duration_sec=1.2,
                      visual=Visual(type="solid"))],
        captions=[Caption(start=0, end=1.1, text="Revenue moved ten percent")],
        audio=AudioTrack(voiceover_path=str(media)))
    settings().brand_identity_enabled = True
    theme_for(item, "compositor")
    return item


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="phase8-qa-bench-") as temp:
        root = Path(temp); good = root/"good.mp4"; bad = root/"bad.mp4"
        thumb = root/"thumb.jpg"; meta = root/"metadata.json"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "testsrc2=size=1080x1920:rate=30", "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=48000", "-t", "1.2", "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=7", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "24", "-c:a", "aac", "-movflags", "+faststart", "-y", str(good)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=black:size=640x360:rate=24", "-t", "1.2", "-c:v", "libx264",
            "-y", str(bad)], check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "0.3",
            "-i", str(good), "-frames:v", "1", "-y", str(thumb)], check=True)
        meta.write_text(json.dumps({"title":"QA","description":"Benchmark",
            "tags":["finance"],"thumbnail_text":"REVENUE"}))
        timings=[]; statuses=[]
        for media in (good, good, good, bad):
            started=time.perf_counter()
            result=qa.production_analyze(graph(media), str(media), thumbnail=str(thumb),
                                         metadata_path=str(meta))
            timings.append((time.perf_counter()-started)*1000); statuses.append(result.status)
        print(json.dumps({"runs":len(timings), "median_ms":round(statistics.median(timings),1),
            "p95_ms":round(max(timings),1), "good_statuses":statuses[:3],
            "broken_status":statuses[-1], "checks_per_run":result.metrics["checks"],
            "network":"none"}, indent=2))


if __name__ == "__main__": main()
