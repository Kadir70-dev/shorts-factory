"""ffmpeg/ffprobe helpers used across pipeline stages."""
from __future__ import annotations

import subprocess
from pathlib import Path


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def ffmpeg_concat_audio(clips: list[Path], out: Path) -> None:
    """Concat same-codec audio clips. Re-encode to a uniform wav to be safe."""
    listfile = out.parent / "concat.txt"
    listfile.write_text("\n".join(f"file '{c}'" for c in clips))
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat",
         "-safe", "0", "-i", str(listfile), "-ar", "44100", "-ac", "1",
         "-y", str(out)],
        check=True,
    )
