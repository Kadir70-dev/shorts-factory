#!/usr/bin/env python3
"""Offline Phase 3 render using only local assets and non-production audio."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> int:
    from app.config import settings
    from app.pipeline import broll, render_ffmpeg
    from app.schemas.scene import AssetCandidate, Scene, SceneGraph, SceneMeta
    from app.schemas.video_spec import Niche, VideoSpec

    out = ROOT / "output" / "phase3_multi_source"
    out.mkdir(parents=True, exist_ok=True)
    graph = SceneGraph(meta=SceneMeta(
        video_id="phase3_asset_sample", channel_id="k70_business",
        niche="usa_business", title="Phase 3 Asset Engine",
        hook="The price stayed fixed"), width=360, height=640, fps=24,
        scenes=[
            Scene(id="s1", narration="Costco kept its hot dog at $1.50 since 1985.",
                  duration_sec=2.2, beat_role="hook"),
            Scene(id="s2", narration="Membership renewals made the economics work.",
                  duration_sec=2.2, beat_role="mechanism"),
        ])
    for index, scene in enumerate(graph.scenes):
        scene.visual.visual_intent = scene.narration
        scene.visual.broll_keywords = [scene.narration]
        fixture = out / f"fixture_{index}.jpg"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f",
            "lavfi", "-i", f"color=c={'0x284b63' if index == 0 else '0x3c6e71'}:s=360x640",
            "-frames:v", "1", "-y", str(fixture)], check=True)

    async def fetch(provider, query, beat):
        if provider != "government_public_domain":
            return []
        index = 0 if beat.source_scene_id == "s1" else 1
        return [AssetCandidate(
            source_url=(out / f"fixture_{index}.jpg").as_uri(),
            provider_institution=provider, asset_type="image",
            license="Public Domain", commercial_use_status="allowed",
            retrieval_date=date.today().isoformat(), scene_id=beat.scene_id,
            relevance_score=.96, confidence=.95, subject_specificity=.95,
            visual_quality=.8, originality=.8, mobile_readability=.95)]

    async def download(candidate, target):
        source = Path(candidate.source_url.removeprefix("file://"))
        shutil.copy2(source, target)
        return target

    settings().visual_intelligence_enabled = True
    settings().storyboard_engine_enabled = True
    settings().multi_source_asset_engine_enabled = True
    broll.multi_source_candidates = fetch
    broll.download_asset_candidate = download
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.business, topic=graph.meta.title,
        allow_ai_image=False, allow_ai_video=False))
    if not all(p.status == "resolved" for p in graph.asset_provenance):
        raise RuntimeError("test fixture assets did not resolve")

    audio = out / "NON_PRODUCTION_TEST_AUDIO.wav"
    source_audio = ROOT / "data" / "assets" / "sfx" / "riser.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(source_audio), "-t",
        str(graph.total_duration_sec), "-ar", "44100", "-ac", "1", "-y",
        str(audio)], check=True)
    graph.audio.voiceover_path = str(audio)
    target = out / "phase3-sample.mp4"
    started = time.perf_counter()
    await render_ffmpeg.render(graph, target)
    if not target.is_file() or target.stat().st_size < 10_000:
        raise RuntimeError("sample render is missing or empty")
    print(f"sample={target}")
    print(f"render_seconds={time.perf_counter() - started:.3f}")
    print(f"provenance_records={len(graph.asset_provenance)}")
    print("audio=NON-PRODUCTION SFX timing fixture; production TTS untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
