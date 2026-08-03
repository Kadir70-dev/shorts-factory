"""Narration stage: local cloned voice only, with measured scene timing."""
from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import ChannelConfig, settings
from ..schemas.scene import SceneGraph
from ..schemas.video_spec import VideoSpec
from ..voice import VoiceManager
from .util import ffmpeg_concat_audio, ffprobe_duration


async def synthesize(graph: SceneGraph, spec: VideoSpec,
                     channel: ChannelConfig) -> SceneGraph:
    del spec, channel  # voice identity is deliberately not selected per video
    out = settings().data_dir / "jobs" / graph.meta.video_id / "vo"
    out.mkdir(parents=True, exist_ok=True)
    clips = [out / f"scene_{index:02d}.wav"
             for index in range(len(graph.scenes))]
    manager = VoiceManager()
    manager.require_voice()  # fail before producing a partial render

    async def one(index: int) -> str:
        engine, _ = await manager.synthesize(graph.scenes[index].narration,
                                             clips[index])
        return engine

    engines = await asyncio.gather(*(one(i) for i in range(len(clips))))
    counts = {name: engines.count(name) for name in dict.fromkeys(engines)}
    print("[tts] local cloned voice: " +
          ", ".join(f"{name}x{count}" for name, count in counts.items()),
          flush=True)

    for scene, clip in zip(graph.scenes, clips):
        scene.duration_sec = round(ffprobe_duration(clip), 3)
    master = out / "voiceover.wav"
    ffmpeg_concat_audio(clips, master)
    graph.audio.voiceover_path = str(master)
    return graph
