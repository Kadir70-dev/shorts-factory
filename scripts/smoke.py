"""
End-to-end smoke test with ZERO paid keys. Runs the full pipeline inline
(no redis/arq) using the offline Director, local TTS fallback, script-based
captions, solid/broll assets, and the pure-ffmpeg renderer.

    DIRECTOR_MODE=mock python scripts/smoke.py

Produces data/jobs/<id>/final.mp4 + thumbnail.jpg + metadata.json and prints
the SceneGraph timeline.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("DIRECTOR_MODE", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.config import load_channel                       # noqa: E402
from app.director import get_director                     # noqa: E402
from app.pipeline import broll, captions, music, postprocess, render, sfx, tts  # noqa: E402
from app.schemas.video_spec import Niche, VideoSpec       # noqa: E402


async def main() -> None:
    spec = VideoSpec(channel_id="usa_finance", niche=Niche.finance,
                     topic="why inflation came in hot this month")
    channel = load_channel(spec.channel_id)

    print(f"[1/6] director ({os.environ['DIRECTOR_MODE']})")
    graph = await get_director(channel).build_scene_graph(spec)

    print("[2/6] tts")
    graph = await tts.synthesize(graph, spec, channel)

    print("[3/6] captions")
    graph = await captions.transcribe(graph)

    print("[4/6] assets")
    graph = await broll.resolve_assets(graph, spec)
    graph = await music.add_music(graph, channel)
    graph = await sfx.add_sound_design(graph)
    print(f"      music: {graph.audio.music_mood} "
          f"({len(graph.audio.music_envelope)} kf) | sfx cues: {len(graph.sfx)} "
          f"({', '.join(sorted({c.role for c in graph.sfx})) or 'none'})")

    print("[5/6] render (ffmpeg fallback)")
    raw = await render.render_remotion(graph)

    print("[6/6] post")
    final = await postprocess.finalize(graph, raw, channel)

    print("\n=== TIMELINE ===")
    for s in graph.scenes:
        print(f"  {s.id}  {s.duration_sec:5.2f}s  {s.visual.type:6}  {s.narration[:48]}")
    print(f"  total: {graph.total_duration_sec:.2f}s  captions: {len(graph.captions)}")
    print(f"\nMP4: {final['mp4']}")
    print(f"THUMB: {final['thumbnail']}")


if __name__ == "__main__":
    asyncio.run(main())
