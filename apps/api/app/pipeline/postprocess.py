"""
Post stage (FFmpeg). Remotion already burned captions + overlays + muxed VO and
music. Here we do platform-grade finishing that's cheaper/safer in ffmpeg:
  - EBU R128 loudnorm to -14 LUFS (YouTube/TikTok target)
  - final H.264 yuv420p main profile (max device compatibility)
  - thumbnail extraction (best frame heuristic: ~0.6s, the hook moment)
  - metadata package (title/description/tags) from the Director's meta
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..config import ChannelConfig, settings
from ..schemas.scene import SceneGraph


async def finalize(graph: SceneGraph, raw_mp4: str, channel: ChannelConfig) -> dict:
    work = Path(raw_mp4).parent
    final = work / "final.mp4"
    thumb = work / "thumbnail.jpg"

    # loudnorm + compatibility re-encode
    await _ff(
        "-i", raw_mp4,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-y", str(final),
    )

    # thumbnail from the hook moment
    await _ff("-ss", "0.6", "-i", raw_mp4, "-frames:v", "1", "-q:v", "2",
              "-y", str(thumb))

    metadata = _build_metadata(graph, channel)
    meta_path = work / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    return {"mp4": str(final), "thumbnail": str(thumb),
            "metadata_json": json.dumps(metadata)}


def _build_metadata(graph: SceneGraph, channel: ChannelConfig) -> dict:
    m = graph.meta
    hashtags = m.hashtags or ["#shorts"]
    desc = (m.description or f"{m.hook}\n\n{channel.cta}").strip()
    return {
        "title": (m.title or m.hook)[:95],
        "description": f"{desc}\n\n{' '.join(hashtags)}",
        "tags": m.tags or [graph.meta.niche, "shorts", "news", channel.id],
        "hashtags": hashtags,
        "thumbnail_text": m.thumbnail_text or m.hook,
        "category": "News & Politics",
        "made_for_kids": False,
    }


async def _ff(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", *args,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {err.decode()[:500]}")
