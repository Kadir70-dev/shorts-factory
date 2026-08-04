"""ffmpeg/ffprobe helpers used across pipeline stages."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


# --------------------------------------------------------------------------- #
# Content-addressed cache for locally-rendered visuals
#
# Charts and motion graphics are pure functions of their inputs — same data,
# same brand, same geometry, same frames. Re-running a Short after an unrelated
# edit redrew every one of them from scratch. Keying on the content rather than
# on the scene means the entry survives scene reordering and is shared by two
# shorts that happen to use the same figure.
#
# Entries are immutable, so there is no invalidation: a changed input is simply
# a different key. `_CACHE_VERSION` in each engine bumps the whole namespace
# when the drawing code itself changes.
# --------------------------------------------------------------------------- #
def visual_cache_path(kind: str, key: str, suffix: str = ".mp4") -> Path:
    from ..config import settings
    path = settings().data_dir / "cache" / kind
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{key}{suffix}"


def visual_cache_store(cached: Path, produced: Path) -> None:
    """Publish a freshly rendered file into the cache, atomically."""
    if not produced.is_file() or produced.stat().st_size <= 1024:
        return
    tmp = cached.with_suffix(cached.suffix + ".tmp")
    try:
        shutil.copyfile(produced, tmp)
        tmp.replace(cached)      # no torn file for a concurrent reader
    except OSError as exc:       # a cache miss is always survivable
        tmp.unlink(missing_ok=True)
        print(f"[cache] store failed for {cached.name} "
              f"({type(exc).__name__}): {exc}", flush=True)


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
