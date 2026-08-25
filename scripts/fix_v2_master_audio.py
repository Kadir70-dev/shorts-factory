#!/usr/bin/env python3
"""Fast remediation: re-synthesize narration (the key-bug fix applied to
build_v2_master_60s.py) and rebuild ONLY the audio mix + final mux,
reusing the already-rendered video_only.mp4 and per-segment clips instead
of re-running the full ~40-minute render pipeline.

    .venv-win/Scripts/python.exe scripts/fix_v2_master_audio.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(ROOT / "scripts"))
from build_v2_master_60s import build_segment_plan, MUSIC_BED, XFADE_DUR, JOB_DIR, AUDIO_DIR

FPS = 24


async def main():
    from app.voice.manager import VoiceManager
    plan = build_segment_plan()
    voice = VoiceManager()
    voice.require_voice()
    narration_paths = []
    for i, ln in enumerate(plan):
        out = AUDIO_DIR / f"line_{i:02d}.wav"
        engine, qa = await voice.synthesize(ln["narration"], out)
        print(f"  [voice] line_{i:02d} ({engine}, {qa.duration_sec:.2f}s): {ln['narration'][:55]!r}")
        narration_paths.append(out)

    durations = [s["duration"] for s in plan]
    video_only = JOB_DIR / "video_only.mp4"
    final_video_duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_only)],
        capture_output=True, text=True).stdout.strip())
    print(f"  video_only duration = {final_video_duration:.3f}s")

    narr_offsets = []
    cum = 0.0
    for i, d_ in enumerate(durations):
        narr_offsets.append(cum)
        cum += d_ - (XFADE_DUR if i < len(durations) - 1 else 0)

    audio_inputs = []
    audio_filter = []
    amix_labels = []
    for i, (p, off) in enumerate(zip(narration_paths, narr_offsets)):
        audio_inputs += ["-i", str(p)]
        lbl = f"a{i}"
        delay_ms = int(max(0, off) * 1000)
        audio_filter.append(f"[{i}:a]adelay=delays={delay_ms}:all=1,volume=1.7[{lbl}]")
        amix_labels.append(f"[{lbl}]")
    music_idx = len(narration_paths)
    audio_inputs += ["-stream_loop", "-1", "-i", str(MUSIC_BED)]
    audio_filter.append(f"[{music_idx}:a]atrim=0:{final_video_duration:.3f},volume=0.14[music]")
    amix_labels.append("[music]")
    audio_filter.append(f"{''.join(amix_labels)}amix=inputs={len(amix_labels)}:duration=longest:normalize=0[aout]")

    final_audio = JOB_DIR / "audio_mix.mp3"
    subprocess.run(
        ["ffmpeg", "-y", *audio_inputs, "-filter_complex", ";".join(audio_filter),
         "-map", "[aout]", "-t", f"{final_video_duration:.3f}", str(final_audio)],
        capture_output=True, text=True, check=True,
    )
    print(f"  audio mix -> {final_audio}")

    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_only), "-i", str(final_audio),
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_mp4)],
        capture_output=True, text=True, check=True,
    )
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)],
                         capture_output=True, text=True).stdout.strip()
    print(f"FINAL (with narration): {final_mp4} ({dur}s)")

    meta_path = JOB_DIR / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["duration_sec"] = float(dur) if dur else meta.get("duration_sec")
    meta["narration_status"] = "FIXED -- real narration synthesized and mixed (was music-only due to a " \
                               "dict-key bug in the first run: synthesize_narration() read ln['text'] but " \
                               "the segment dicts use 'narration'; fixed and confirmed via this rebuild)."
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
