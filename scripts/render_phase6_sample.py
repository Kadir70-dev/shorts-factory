#!/usr/bin/env python3
"""Mixed official/2D/Three.js/AI sample with non-production timing audio."""
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
    from app.pipeline import ai_broll, broll, render_ffmpeg, threejs_engine
    from app.schemas.scene import (AssetCandidate, Scene, SceneGraph, SceneMeta,
                                   StoryboardData, StoryboardScene)
    from app.schemas.video_spec import Niche, VideoSpec

    out = ROOT / "output" / "phase6_ai_broll"
    out.mkdir(parents=True, exist_ok=True)
    official = out / "official_fixture.jpg"
    synthetic = out / "synthetic_fixture.jpg"
    for path, color in ((official, "0x1f4e79"), (synthetic, "0x5a3d73")):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f",
            "lavfi", "-i", f"color=c={color}:s=360x640", "-frames:v", "1",
            "-y", str(path)], check=True)

    lines = [
        "The Treasury published the official 2024 figures.",
        "Revenue reached $4.2 billion.",
        "Ten percent compounded growth changes the curve.",
        "A supply-chain bottleneck can freeze an otherwise healthy business.",
    ]
    scenes = [Scene(id=f"s{i + 1}", narration=line, duration_sec=.8,
                    beat_role="evidence") for i, line in enumerate(lines)]
    graph = SceneGraph(meta=SceneMeta(
        video_id="phase6_mixed_sample", channel_id="k70_business",
        niche="usa_finance", title="Four Visual Sources",
        hook="Use the right visual source"), width=360, height=640, fps=30,
        scenes=scenes, brand_id="k70")
    common = dict(duration_estimate=.8, recommended_visual_type="real",
                  asset_priority=["exact_footage", "local_graphics", "ai_recreation"],
                  visual_confidence_score=.9)
    graph.storyboard = StoryboardData(scenes=[
        StoryboardScene(scene_id="s1.b1", source_scene_id="s1", narration=lines[0],
            visual_objective="Show the official Treasury release", year=2024,
            primary_entity="US Treasury", company="", location="United States",
            **common),
        StoryboardScene(scene_id="s2.b1", source_scene_id="s2", narration=lines[1],
            visual_objective="Make the revenue number immediately readable",
            financial_numbers=["$4.2 billion"], motion_graphics_needed=True,
            threejs_candidate=True, **common),
        StoryboardScene(scene_id="s3.b1", source_scene_id="s3", narration=lines[2],
            visual_objective="Show compound growth bending upward",
            financial_numbers=["10 percent"], motion_graphics_needed=True,
            threejs_candidate=True, **common),
        StoryboardScene(scene_id="s4.b1", source_scene_id="s4", narration=lines[3],
            visual_objective="Original cinematic metaphor of a port bottleneck",
            primary_entity="Supply chain", secondary_entities=["Port", "Factory"],
            emotion="tense", recommended_visual_type="ai_image",
            ai_broll_candidate=True, **{k: v for k, v in common.items()
                                       if k != "recommended_visual_type"}),
    ])

    async def source_search(provider, query, candidate):
        if provider == "government_public_domain" and candidate.source_scene_id == "s1":
            return [AssetCandidate(
                source_url=official.as_uri(), provider_institution=provider,
                asset_type="image", license="Public Domain",
                commercial_use_status="allowed", retrieval_date=date.today().isoformat(),
                scene_id=candidate.scene_id, relevance_score=.98, confidence=.98,
                subject_specificity=.98, visual_quality=.8, originality=.9,
                mobile_readability=.9)]
        return []

    async def source_download(candidate, target):
        shutil.copy2(Path(candidate.source_url.removeprefix("file://")), target)
        return target

    class FixtureAI:
        name = "phase6_test_fixture"
        def available(self): return True
        def model(self): return "local-fixture-v1"
        async def generate(self, prompt, scene, quality):
            return ai_broll.GeneratedAsset(str(synthetic), self.model(), "image")

    ai_broll.register_provider(FixtureAI())
    broll.multi_source_candidates = source_search
    broll.download_asset_candidate = source_download
    settings().multi_source_asset_engine_enabled = True
    settings().motion_graphics_engine_enabled = True
    settings().motion_graphics_quality = "preview"
    settings().threejs_visual_engine_enabled = True
    settings().threejs_quality = "preview"
    settings().ai_broll_engine_enabled = True
    settings().ai_broll_provider_priority = "phase6_test_fixture"
    await broll.resolve_assets(graph, VideoSpec(
        channel_id="k70_business", niche=Niche.finance, topic=graph.meta.title,
        allow_ai_image=True, allow_ai_video=False))
    await threejs_engine.close_worker()
    expected = ["image", "motion_gfx", "threejs", "ai_image"]
    actual = [scene.visual.type for scene in scenes]
    if actual != expected:
        raise RuntimeError(f"priority ladder mismatch: {actual}")

    audio = out / "NON_PRODUCTION_TEST_AUDIO.wav"
    fixture = ROOT / "data" / "assets" / "sfx" / "riser.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(fixture), "-t",
        str(graph.total_duration_sec), "-ar", "44100", "-ac", "1", "-y",
        str(audio)], check=True)
    graph.audio.voiceover_path = str(audio)
    target = out / "phase6-mixed-sample.mp4"
    started = time.perf_counter()
    await render_ffmpeg.render(graph, target)
    if not target.is_file() or target.stat().st_size < 10_000:
        raise RuntimeError("sample render missing or empty")
    print(f"sample={target}")
    print(f"sources={','.join(actual)}")
    print(f"render_seconds={time.perf_counter() - started:.3f}")
    print("audio=NON-PRODUCTION SFX timing fixture; production TTS untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
