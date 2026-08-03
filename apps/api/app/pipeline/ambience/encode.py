"""
Encoding: render the loop once, then multiply it out to full length.

This is the strategy the whole package exists to enable. Rendering 2 hours of
4K60 directly is 432,000 frames — roughly 40 hours of CPU on this box. Instead:

    1. render exactly ONE loop period (5,400 frames at 90 s) and encode it;
    2. `-stream_loop N` + `-c:v copy` to reach 2 hours.

Step 2 does no video re-encoding at all — it demuxes and remuxes packets, so the
2-hour master costs I/O rather than CPU, and the output is bit-identical to the
loop on every repetition. Verified empirically before building on it: a 5 s clip
looped 12x produced exactly 60.000000 s and exactly 3600 frames, no drift.

The loop is encoded with a closed GOP whose length divides the loop exactly, so
every repetition starts on an IDR frame and the copy is always splice-clean.

Audio is handled differently on purpose. AAC frames are 1024 samples and would
almost never line up with the loop boundary, so concatenating encoded audio
would leave a priming gap — an audible tick every 90 seconds. Instead ffmpeg
loops the DECODED wav and encodes the full two hours as ONE continuous AAC
stream, which has no internal joins at all.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EncodeConfig:
    crf: int = 19
    preset: str = "faster"
    pix_fmt: str = "yuv420p"
    audio_bitrate: str = "320k"
    threads: int = 2                      # leave cores for the renderer
    tune: str = "grain"                   # preserves the film grain we added


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def open_frame_writer(
    out: Path, width: int, height: int, fps: int, cfg: EncodeConfig
) -> subprocess.Popen:
    """Start ffmpeg reading raw RGB frames on stdin.

    Piping raw frames avoids ever materialising 5,400 PNGs on disk (~90 GB) and
    keeps the renderer and the encoder busy on different cores at the same time.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "pipe:0",
        "-an",
        "-c:v", "libx264",
        "-preset", cfg.preset,
        "-tune", cfg.tune,
        "-crf", str(cfg.crf),
        "-pix_fmt", cfg.pix_fmt,
        # Closed GOP of exactly 1 second, aligned to the loop boundary, so every
        # repetition in the stream-copy starts on an IDR.
        "-g", str(fps), "-keyint_min", str(fps), "-sc_threshold", "0",
        # Memory, not speed, is the binding constraint here: this box has 3.8 GB
        # and the renderer already holds ~1.3 GB. x264 at 4K buffers whole frames
        # for lookahead/refs/b-frames (~12 MB each), and the defaults pushed it
        # to 1.7 GB — enough to OOM the job hours in. These caps hold it near
        # 500 MB at negligible quality cost for content this soft.
        "-x264-params", "open-gop=0:rc-lookahead=12:ref=2:bframes=2:sync-lookahead=0",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-movflags", "+faststart",
        str(out),
    ]
    if cfg.threads:
        cmd.insert(-1, "-threads")
        cmd.insert(-1, str(cfg.threads))
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)


def build_master(
    loop_video: Path,
    loop_audio: Path,
    out: Path,
    *,
    total_seconds: float,
    loop_seconds: float,
    cfg: EncodeConfig,
) -> None:
    """Multiply the loop out to `total_seconds` and mux the continuous audio."""
    repeats = int(round(total_seconds / loop_seconds))
    if abs(repeats * loop_seconds - total_seconds) > 1e-6:
        raise ValueError(
            f"loop_seconds={loop_seconds} does not divide total_seconds={total_seconds}; "
            "an exact whole number of loops is required for a seamless master"
        )

    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-stream_loop", str(repeats - 1), "-i", str(loop_video),
        "-stream_loop", str(repeats - 1), "-i", str(loop_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",                       # no video re-encode: this is the win
        "-c:a", "aac", "-b:a", cfg.audio_bitrate, "-ar", "48000", "-ac", "2",
        "-t", f"{total_seconds:.6f}",
        "-movflags", "+faststart",
        str(out),
    ])


def probe(path: Path) -> dict[str, str]:
    """Duration / stream facts, used by the QA step to verify the master."""
    out = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration,size:stream=codec_name,width,height,"
                          "r_frame_rate,channels,sample_rate,nb_frames",
         "-of", "default=noprint_wrappers=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    info: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info.setdefault(k, v)
    return info
