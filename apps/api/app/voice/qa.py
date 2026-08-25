"""Fast, dependency-free gates for synthesized narration."""
from __future__ import annotations

import math
from array import array
import wave
from dataclasses import dataclass
from pathlib import Path


class VoiceQAError(RuntimeError):
    pass


@dataclass(frozen=True)
class QAResult:
    duration_sec: float
    rms: int


def inspect(path: Path, *, min_duration_sec: float = .12,
            min_rms: int = 20) -> QAResult:
    """Reject missing, malformed, empty, silent, or non-mono normalized WAVs."""
    if not path.is_file() or path.stat().st_size <= 256:
        raise VoiceQAError(f"voice output is missing or empty: {path}")
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            rate = wav.getframerate()
            width = wav.getsampwidth()
            frames = wav.getnframes()
            payload = wav.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise VoiceQAError(f"invalid WAV {path}: {exc}") from exc
    if channels != 1 or rate != 44100 or width != 2:
        raise VoiceQAError(
            f"unexpected WAV format for {path}: {channels}ch {rate}Hz {width * 8}-bit")
    duration = frames / rate if rate else 0.0
    samples = array("h")
    samples.frombytes(payload)
    rms = int(math.sqrt(sum(sample * sample for sample in samples) / len(samples))) \
        if samples else 0
    if duration < min_duration_sec:
        raise VoiceQAError(f"voice output is too short ({duration:.3f}s): {path}")
    if rms < min_rms:
        raise VoiceQAError(f"voice output is silent (RMS {rms}): {path}")
    return QAResult(duration_sec=duration, rms=rms)
