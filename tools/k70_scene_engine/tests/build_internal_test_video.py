"""Builds the brief's section-20 internal test video: John / cash / inflation
/ investment / compound growth. NOT for publishing -- output lives under
tools/k70_scene_engine/.test_renders/, gitignored.

Demonstrates, in one short video: a recurring K70 character (3D_CHARACTER),
an original voxel-style transition (VOXEL_STORY), the existing pipeline's
motion-graphics/data-chart rendering reused unmodified (MOTION_GRAPHIC /
DATA_CHART), and Kokoro narration -- composited with plain ffmpeg rather
than the full produce.py job pipeline, since this is a 30-45s internal
smoke test, not a publishable job.

    .venv-win/Scripts/python.exe -m tools.k70_scene_engine.tests.build_internal_test_video
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

OUT_DIR = ROOT / "tools" / "k70_scene_engine" / ".test_renders" / "internal_test_video"
W, H, FPS = 1920, 1080, 30


async def main() -> None:
    import yaml, os
    preset = yaml.safe_load((ROOT / "config" / "presets" / "documentary_finance.yaml").read_text())
    for k, v in (preset.get("env") or {}).items():
        os.environ[k] = str(v)

    from app.brand.manager import theme_for
    from app.pipeline import motiongfx, dataviz
    from app.schemas.scene import SceneGraph, SceneMeta, DataViz
    from app.voice.manager import VoiceManager

    from tools.k70_scene_engine.blender import bpy_bridge, voxelizer
    from tools.k70_scene_engine.characters.roster import get as get_character
    from tools.k70_scene_engine.qa.validators import validate_still

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    stub_meta = SceneMeta(video_id="k70_scene_engine_internal_test", channel_id="k70_economy",
                          niche="usa_finance", structure_id="internal_test",
                          title="internal test", hook="internal test", description="internal test",
                          tags=[], hashtags=[], thumbnail_text="", disclaimer="")
    stub_graph = SceneGraph(meta=stub_meta, fps=FPS, width=W, height=H, brand_id="k70", scenes=[])
    theme = theme_for(stub_graph, "compositor")

    voice = VoiceManager()
    voice.require_voice()

    BEATS = [
        ("hook", "Meet John. John has ten thousand dollars, saved up over several years of work."),
        ("cash", "For now, he keeps all of it sitting in cash, in a regular checking account, earning nothing."),
        ("inflation", "But prices don't stand still. As inflation rises, year after year, the real value of that cash slowly falls."),
        ("invest", "So John decides to change his approach, and invests part of his savings into the system instead of letting it sit idle."),
        ("growth", "Over a longer stretch of time, compound growth changes the outcome -- the invested portion works much harder than the cash ever did."),
        ("close", "This has been an internal integration test for the K70 Scene Engine -- not for publishing."),
    ]

    print("=== 1. narration ===")
    wav_paths: dict[str, Path] = {}
    durations: dict[str, float] = {}
    for beat_id, text in BEATS:
        out = OUT_DIR / f"{beat_id}.wav"
        engine, _qa = await voice.synthesize(text, out)
        from app.pipeline.util import ffprobe_duration
        dur = ffprobe_duration(out)
        wav_paths[beat_id] = out
        durations[beat_id] = dur
        print(f"  {beat_id}: {dur:.2f}s via {engine} -- {text!r}")

    print("=== 2. John (3D_CHARACTER) ===")
    john = get_character("john")
    john_asset = str((ROOT / "tools" / "k70_scene_engine" / "vendor" /
                      "gobkit-free-assets" / f"{john.base_asset_id.split(':', 1)[1]}.glb").resolve())
    john_png = bpy_bridge.render_still(
        assets=[{"path": john_asset, "format": "glb", "tint": list(john.accent_color)}],
        camera={"auto_frame": True, "distance_multiplier": 1.7},
        lighting={"energy": 3.0, "rotation": (0.9, 0, 0.6)},
        width=W, height=H, out_dir=OUT_DIR, cache_key_extra="john_hero",
    )
    print(f"  {john_png} -- {validate_still(john_png).passed}")

    print("=== 3. voxel John (VOXEL_STORY) ===")
    voxel_png = voxelizer.voxelize_and_render(
        source_asset_path=john_asset, source_format="glb", block_size=0.08,
        width=W, height=H, out_dir=OUT_DIR,
    )
    print(f"  {voxel_png} -- {validate_still(voxel_png).passed}")

    print("=== 4. inflation (MOTION_GRAPHIC, existing pipeline reused unmodified) ===")
    inflation_mp4 = OUT_DIR / "inflation.mp4"
    await motiongfx.kinetic(theme, inflation_mp4, W, H, FPS, durations["inflation"],
                            headline="PURCHASING POWER FALLS AS PRICES RISE", seed=42)

    print("=== 5. growth (DATA_CHART, existing pipeline reused unmodified) ===")
    growth_mp4 = OUT_DIR / "growth.mp4"
    growth_viz = DataViz(kind="delta", title="Cash vs. invested (illustrative)",
                         points=[{"label": "Cash, 10 years", "value": 10000, "emphasis": "normal"},
                                 {"label": "Invested, 10 years", "value": 18000, "emphasis": "positive"}],
                         prefix="$", suffix="", decimals=0, abbreviate=False,
                         note="Illustrative example -- not a return guarantee")
    await dataviz.render(growth_viz, theme, growth_mp4, W, H, FPS, durations["growth"])

    print("=== 6. close card (MOTION_GRAPHIC) ===")
    close_mp4 = OUT_DIR / "close.mp4"
    await motiongfx.kinetic(theme, close_mp4, W, H, FPS, durations["close"],
                            headline="K70 SCENE ENGINE", kicker="INTERNAL INTEGRATION TEST", seed=7)

    print("=== 7. compositing ===")
    scene_clips: list[Path] = []
    for beat_id, still, is_video in [
        ("hook", john_png, False),
        ("cash", john_png, False),
        ("inflation", inflation_mp4, True),
        ("invest", voxel_png, False),
        ("growth", growth_mp4, True),
        ("close", close_mp4, True),
    ]:
        dur = durations[beat_id]
        clip = OUT_DIR / f"clip_{beat_id}.mp4"
        if is_video:
            subprocess.run(["ffmpeg", "-y", "-i", str(still), "-t", f"{dur:.3f}",
                            "-vf", f"scale={W}:{H},fps={FPS}", "-an", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True)
        else:
            subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", str(still), "-t", f"{dur:.3f}",
                            "-vf", (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                                    f"crop={W}:{H},zoompan=z='min(zoom+0.0008,1.08)':"
                                    f"d={int(dur * FPS)}:s={W}x{H}:fps={FPS}"),
                            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
                          check=True, capture_output=True)
        scene_clips.append(clip)
        print(f"  scene clip: {clip.name} ({dur:.2f}s)")

    concat_list = OUT_DIR / "concat.txt"
    concat_list.write_text("\n".join(f"file '{c.resolve()}'" for c in scene_clips), encoding="utf-8")
    silent_mp4 = OUT_DIR / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-c", "copy", str(silent_mp4)], check=True, capture_output=True)

    concat_wav_list = OUT_DIR / "concat_audio.txt"
    concat_wav_list.write_text("\n".join(f"file '{wav_paths[b].resolve()}'" for b, _ in BEATS),
                               encoding="utf-8")
    audio_wav = OUT_DIR / "narration.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_wav_list),
                    "-c", "copy", str(audio_wav)], check=True, capture_output=True)

    final_mp4 = OUT_DIR / "final_test.mp4"
    subprocess.run(["ffmpeg", "-y", "-i", str(silent_mp4), "-i", str(audio_wav),
                    "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_mp4)],
                  check=True, capture_output=True)

    total = sum(durations.values())
    print(f"\n=== DONE: {final_mp4} (~{total:.1f}s narration) ===")


if __name__ == "__main__":
    asyncio.run(main())
