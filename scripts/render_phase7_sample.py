#!/usr/bin/env python3
"""Phase 7 branded mixed-engine sample using non-production timing audio."""
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
    from app.pipeline import ai_broll, finance_motion, render_ffmpeg, threejs_engine
    from app.schemas.scene import (Caption, Overlay, Scene, SceneGraph, SceneMeta,
                                   StoryboardScene)

    out = ROOT / "output" / "phase7_brand_identity"
    out.mkdir(parents=True, exist_ok=True)
    synthetic = out / "synthetic_fixture.jpg"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "color=c=0x17223a:s=360x640", "-frames:v", "1", "-y", str(synthetic)],
        check=True)

    lines = ["Three milestones changed the market.", 'The investor said, "Discipline compounds over time."',
             "Ten percent compound growth bends the curve.",
             "A supply chain can freeze without warning.",
             "Follow K70 Finance for the systems behind the numbers."]
    scenes = [Scene(id=f"s{i+1}", narration=line,
                    duration_sec=1.5 if i == 4 else .9,
                    beat_role="cta" if i == 4 else "evidence")
              for i, line in enumerate(lines)]
    scenes[3].overlays = [Overlay(type="lower_third", text="SUPPLY CHAIN RISK",
                                  sub="K70 MARKET BRIEF", y=.615)]
    graph = SceneGraph(meta=SceneMeta(video_id="phase7_brand_sample",
        channel_id="k70_business", niche="usa_finance", title="One Visual Identity",
        hook="Every frame belongs to K70"), width=360, height=640, fps=30,
        scenes=scenes, brand_id="k70")

    common = dict(duration_estimate=.9, primary_entity="Market", company="K70",
        recommended_visual_type="motion_gfx", recommended_camera_movement="none",
        asset_priority=["local_graphics", "ai_recreation"],
        visual_confidence_score=.95)
    beats = [
        StoryboardScene(scene_id="s1.b1", source_scene_id="s1", narration=lines[0],
            visual_objective="Timeline of finance milestones", year=2024,
            secondary_entities=["2019", "2021", "2024"], motion_graphics_needed=True,
            overlay_text=["2019", "2021", "2024"], **common),
        StoryboardScene(scene_id="s2.b1", source_scene_id="s2", narration=lines[1],
            visual_objective="Editorial quote card", motion_graphics_needed=True,
            overlay_text=["Discipline compounds over time"], **common),
        StoryboardScene(scene_id="s3.b1", source_scene_id="s3", narration=lines[2],
            visual_objective="Compound growth curve", financial_numbers=["10 percent"],
            threejs_candidate=True, overlay_text=["10% COMPOUND GROWTH"], **common),
        StoryboardScene(scene_id="s4.b1", source_scene_id="s4", narration=lines[3],
            visual_objective="Cinematic port bottleneck metaphor", emotion="tense",
            ai_broll_candidate=True, overlay_text=["SUPPLY CHAIN RISK"],
            **{**common, "recommended_visual_type": "ai_image"}),
    ]
    settings().brand_identity_enabled = True
    settings().motion_graphics_engine_enabled = True
    settings().threejs_visual_engine_enabled = True
    settings().ai_broll_engine_enabled = True
    settings().data_dir = out / "cache_data"

    for index in (0, 1):
        result = await finance_motion.render(graph, scenes[index], beats[index], "preview", index + 1)
        if result.status == "unresolved": raise RuntimeError(result.error)
        scenes[index].visual.type, scenes[index].visual.asset_path = "motion_gfx", result.render_path
        graph.motion_graphics_provenance.append(result)
    result3 = await threejs_engine.render(graph, scenes[2], beats[2], "preview", 70)
    await threejs_engine.close_worker()
    if result3.status == "unresolved": raise RuntimeError(result3.error)
    scenes[2].visual.type, scenes[2].visual.asset_path = "threejs", result3.render_path
    graph.threejs_provenance.append(result3)

    class FixtureAI:
        name = "phase7_test_fixture"
        def available(self): return True
        def model(self): return "local-brand-fixture-v1"
        async def generate(self, prompt, scene, quality):
            return ai_broll.GeneratedAsset(str(synthetic), self.model(), "image")
    ai_broll.register_provider(FixtureAI())
    settings().ai_broll_provider_priority = "phase7_test_fixture"
    result4 = await ai_broll.generate(graph, scenes[3], beats[3], "preview")
    if result4.status == "unresolved": raise RuntimeError(result4.error)
    scenes[3].visual.type, scenes[3].visual.asset_path = "ai_image", result4.render_path
    graph.ai_broll_provenance.append(result4)

    caption_text = ["THREE MILESTONES", "DISCIPLINE COMPOUNDS",
                    "TEN PERCENT GROWTH", "SUPPLY CHAIN FREEZE"]
    graph.captions = [Caption(start=i*.9, end=(i+1)*.9-.05, text=text)
                      for i, text in enumerate(caption_text)]
    graph.captions.append(Caption(start=3.6, end=5.05, text="FOLLOW K70 FINANCE"))
    graph.variety = {"caption_animation": "keyword_flash", "grade": "neutral_doc"}
    audio = out / "NON_PRODUCTION_TEST_AUDIO.wav"
    fixture = ROOT / "data" / "assets" / "sfx" / "riser.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1",
        "-i", str(fixture), "-t", str(graph.total_duration_sec), "-ar", "44100", "-ac", "1",
        "-y", str(audio)], check=True)
    graph.audio.voiceover_path = str(audio)
    target = out / "phase7-brand-identity-sample.mp4"
    started = time.perf_counter()
    await render_ffmpeg.render(graph, target)
    if not target.is_file() or target.stat().st_size < 10_000:
        raise RuntimeError("sample render missing or empty")
    receipt = graph.brand_identity_provenance
    print(f"sample={target}")
    print("features=motion_graphics,threejs,ai_broll,captions,lower_third,timeline,quote_card")
    print(f"brand_modules={','.join(receipt.modules)}")
    print(f"consistency={receipt.consistency_checks}")
    print(f"render_seconds={time.perf_counter() - started:.3f}")
    print("audio=NON-PRODUCTION SFX timing fixture; production TTS untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
