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

    # loudnorm — an AUDIO filter, so the video is STREAM-COPIED.
    #
    # This pass used to re-encode the whole video with libx264 in order to apply
    # an audio filter. That cost a full re-compress (38s on a 45s short) and,
    # worse, made the delivered file a THIRD lossy generation on top of the scene
    # clips and the finish pass. The H.264 export contract it was enforcing here
    # (Main profile, yuv420p, CFR at graph.fps) is now set where the video is
    # actually encoded — render_ffmpeg._finish — so copying preserves it exactly
    # and the delivered frames are bit-identical to the rendered master.
    # AAC-LC at 48 kHz is part of the DELIVERY contract, not an optimizer
    # feature. It only ever applied on the optimizer branch, so with the
    # optimizer off the encoder chose its own rate — a 44.1 kHz master was
    # landing at 96 kHz stereo. Both branches now pin it.
    finish = ["-i", raw_mp4, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "copy",
              "-c:a", "aac", "-profile:a", "aac_low", "-ar", "48000", "-b:a", "192k"]
    if settings().production_optimizer_enabled:
        finish += ["-avoid_negative_ts", "make_zero"]
    finish += ["-movflags", "+faststart", "-y", str(final)]
    await _ff(*finish)

    # thumbnail from the hook moment
    await _ff("-ss", "0.6", "-i", raw_mp4, "-frames:v", "1", "-q:v", "2",
              "-y", str(thumb))

    metadata = _build_metadata(graph, channel)
    meta_path = work / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    return {"mp4": str(final), "thumbnail": str(thumb),
            "metadata_path": str(meta_path), "metadata_json": json.dumps(metadata)}


def _build_metadata(graph: SceneGraph, channel: ChannelConfig) -> dict:
    from . import compliance

    m = graph.meta
    hashtags = m.hashtags or ["#shorts"]
    base = (m.description or f"{m.hook}\n\n{channel.cta}").strip()
    # The disclaimer goes ABOVE the fold, before the hashtags — a disclosure a
    # reviewer has to expand the description to find is one they will not see.
    desc = compliance.description_block(graph, base)

    meta = {
        "title": (m.title or m.hook)[:95],
        "description": f"{desc}\n\n{' '.join(hashtags)}",
        "tags": m.tags or [graph.meta.niche, "shorts", "news", channel.id],
        "hashtags": hashtags,
        "thumbnail_text": m.thumbnail_text or m.hook,
        "category": "News & Politics",
        "made_for_kids": False,
        # --- publishing state the uploader must act on ----------------------- #
        "disclaimer": m.disclaimer,
        "story_structure": m.structure_id,
        "variety": graph.variety,
        # YouTube's "Altered or Synthetic Content" flag. The pipeline CANNOT set
        # this for you — it is a per-upload declaration in Studio — so it is
        # surfaced here and in the console at the end of the render.
        "requires_ai_disclosure": m.requires_ai_disclosure,
        "ai_disclosure_reasons": m.ai_disclosure_reasons,
        "compliance_notes": m.compliance_notes,
    }
    if m.requires_ai_disclosure:
        print("\n" + "\n".join(compliance.publish_checklist(graph)), flush=True)
    return meta


async def _ff(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error", *args,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {err.decode()[:500]}")
