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


def normalize_narration_joins(clips: list[Path], *, pad_sec: float = 0.10) -> None:
    """Add one small, CONSISTENT breath-gap to the end of every per-scene TTS
    clip — in place.

    Measured root cause: each scene is synthesised as its own isolated
    utterance, and `ffmpeg_concat_audio` butts the raw clips together with
    ZERO gap between them (confirmed: `silencedetect` finds no measurable
    silence anywhere in delivered voiceover.wav — there was never a pause to
    remove). Two independently-synthesised clips glued at 0.000s apart lose
    the natural micro-breath a continuous reading has between clauses/
    sentences, which reads as an abrupt, "assembly-line" splice rather than
    continuous speech — the actual complaint, despite there being no long
    silence to point to.

    This only ADDS silence (`apad`), never trims — there is no risk of
    clipping an onset or trailing phoneme, only of the pad itself being too
    long, which is why it's kept short and uniform rather than adaptive.
    """
    for clip in clips:
        tmp = clip.with_suffix(".pad.wav")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(clip),
             "-af", f"apad=pad_dur={pad_sec}", str(tmp)],
            check=True,
        )
        tmp.replace(clip)


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
