"""Narration stage: local cloned voice only, with measured scene timing."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from ..config import ChannelConfig, settings
from ..schemas.scene import SceneGraph
from ..schemas.video_spec import VideoSpec
from ..voice import VoiceManager
from ..voice import engines as voice_engines
from .util import ffmpeg_concat_audio, ffprobe_duration, normalize_narration_joins


async def synthesize(graph: SceneGraph, spec: VideoSpec,
                     channel: ChannelConfig) -> SceneGraph:
    del spec, channel  # voice identity is deliberately not selected per video
    out = settings().data_dir / "jobs" / graph.meta.video_id / "vo"
    out.mkdir(parents=True, exist_ok=True)
    clips = [out / f"scene_{index:02d}.wav"
             for index in range(len(graph.scenes))]
    manager = VoiceManager()
    manager.require_voice()  # fail before producing a partial render
    profile = manager.profile
    lines = [manager.preprocess(scene.narration) for scene in graph.scenes]

    # Three passes, cheapest first. Every one of them writes the same normalized
    # WAV, so a scene resolved early is indistinguishable from one synthesised.
    produced: list[str | None] = [None] * len(clips)

    # 1. Cache. A visual-only re-render re-narrates nothing.
    cascade = profile.cascade() + profile.fallback_cascade()
    for index, text in enumerate(lines):
        hit = voice_engines.cache_lookup(text, profile, cascade)
        if hit is not None:
            shutil.copyfile(hit[0], clips[index])
            produced[index] = hit[1]
    hits = sum(1 for name in produced if name)

    # 2. Batch. One model load for everything still missing, instead of one per
    #    scene serialised behind the memory lock.
    pending = [i for i, name in enumerate(produced) if name is None]
    if pending and "kokoro" in cascade:
        batched: list[str | None] = [None] * len(pending)
        await voice_engines.batch_kokoro([lines[i] for i in pending],
                                         [clips[i] for i in pending],
                                         profile, batched)
        for slot, index in enumerate(pending):
            produced[index] = batched[slot]

    # 3. Per-scene cascade for whatever the batch could not produce.
    async def one(index: int) -> str:
        engine, _ = await manager.synthesize(graph.scenes[index].narration,
                                             clips[index])
        return engine

    remaining = [i for i, name in enumerate(produced) if name is None]
    for index, engine in zip(remaining,
                             await asyncio.gather(*(one(i) for i in remaining))):
        produced[index] = engine

    engines = [name for name in produced if name]
    counts = {name: engines.count(name) for name in dict.fromkeys(engines)}
    print(f"[tts] narration cache: {hits} hit, {len(clips) - hits} miss",
          flush=True)
    print("[tts] local cloned voice: " +
          ", ".join(f"{name}x{count}" for name, count in counts.items()),
          flush=True)

    normalize_narration_joins(clips)
    for scene, clip in zip(graph.scenes, clips):
        scene.duration_sec = round(ffprobe_duration(clip), 3)
    master = out / "voiceover.wav"
    ffmpeg_concat_audio(clips, master)
    graph.audio.voiceover_path = str(master)
    return graph
