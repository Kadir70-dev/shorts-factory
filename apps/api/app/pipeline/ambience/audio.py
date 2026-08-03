"""
Original fireplace audio: a seamless, exactly-periodic stereo crackle bed.

Everything is synthesised from seeded noise. No sample library, no recording, no
third-party asset — which is what makes the result unambiguously copyright-safe
and monetisation-safe, the same reason the visuals are procedural.

Seamlessness is again structural, not a crossfade:

  * the continuous bed is white noise shaped by MULTIPLYING ITS FFT and
    transforming back. Circular convolution makes the result periodic to the
    sample, so the join is mathematically invisible;
  * every transient is written with `np.add.at` on indices taken mod N, so a
    crackle that starts 40 ms before the end wraps around and finishes at the
    start. Nothing is truncated at the boundary.

Loudness is deliberately boring: a constant noise floor, transients that peak
well below full scale, one fixed normalisation gain for the whole file and a
soft-knee limiter that only ever touches isolated pops. There is no compressor
riding the level and no fades, so the brief's "no sudden volume changes" holds
across all two hours rather than just within one loop.
"""
from __future__ import annotations

import struct
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48_000


@dataclass
class AudioConfig:
    seconds: float = 90.0
    sample_rate: int = SAMPLE_RATE
    seed: int = 31
    crackles_per_sec: float = 7.0
    pops_per_sec: float = 0.28
    bed_level: float = 0.085
    target_peak: float = 0.89


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _circular_filtered_noise(n: int, rng: np.random.Generator,
                             shape: np.ndarray) -> np.ndarray:
    """White noise shaped by `shape` in the frequency domain.

    Because this is a circular (FFT) convolution rather than a sliding filter,
    the output is exactly periodic over n samples — sample n-1 leads back into
    sample 0 with no discontinuity, which a time-domain IIR could never give us.
    """
    spec = np.fft.rfft(rng.standard_normal(n).astype(np.float32))
    return np.fft.irfft(spec * shape, n).astype(np.float32)


def _bed_shape(n: int, sr: int, tilt: float, low_hz: float, high_hz: float) -> np.ndarray:
    """Spectral envelope for the continuous bed: pink-ish with soft shelves."""
    f = np.fft.rfftfreq(n, 1.0 / sr).astype(np.float32)
    f = np.maximum(f, 1.0)
    shape = f ** (-tilt)                                    # pink/brown tilt
    shape *= 1.0 / (1.0 + (low_hz / f) ** 4)                # highpass shelf
    shape *= 1.0 / (1.0 + (f / high_hz) ** 2)               # gentle LP rolloff
    return shape.astype(np.float32)


def _grain_bank(rng: np.random.Generator, sr: int, count: int = 48) -> list[np.ndarray]:
    """A bank of short crackle transients.

    Pre-building a bank and reusing it is what keeps this fast: a per-event IIR
    filter in Python would be thousands of sample-rate loops. Each grain is
    noise shaped in the frequency domain and multiplied by a sharp attack /
    exponential decay envelope, which is exactly what a resin pocket popping in
    burning wood sounds like.
    """
    grains: list[np.ndarray] = []
    for _ in range(count):
        dur = float(rng.uniform(0.008, 0.20))
        n = max(64, int(dur * sr))
        centre = float(rng.uniform(900.0, 6500.0))
        width = float(rng.uniform(0.5, 1.9))

        f = np.fft.rfftfreq(n, 1.0 / sr).astype(np.float32)
        f = np.maximum(f, 1.0)
        # log-normal bandpass around `centre`
        shape = np.exp(-0.5 * (np.log(f / centre) / width) ** 2).astype(np.float32)

        g = np.fft.irfft(np.fft.rfft(rng.standard_normal(n).astype(np.float32)) * shape, n)
        t = np.arange(n, dtype=np.float32) / sr
        attack = 1.0 - np.exp(-t / max(0.00035, dur * 0.012))
        decay = np.exp(-t / max(0.004, dur * 0.30))
        g = (g * attack * decay).astype(np.float32)

        peak = float(np.abs(g).max()) or 1.0
        grains.append((g / peak).astype(np.float32))
    return grains


def _pop_bank(rng: np.random.Generator, sr: int, count: int = 16) -> list[np.ndarray]:
    """Rarer, lower, woodier thumps — the occasional loud crack in a log."""
    pops: list[np.ndarray] = []
    for _ in range(count):
        dur = float(rng.uniform(0.06, 0.34))
        n = max(256, int(dur * sr))
        t = np.arange(n, dtype=np.float32) / sr
        centre = float(rng.uniform(110.0, 420.0))

        f = np.maximum(np.fft.rfftfreq(n, 1.0 / sr).astype(np.float32), 1.0)
        shape = np.exp(-0.5 * (np.log(f / centre) / 0.85) ** 2).astype(np.float32)
        body = np.fft.irfft(np.fft.rfft(rng.standard_normal(n).astype(np.float32)) * shape, n)

        # a touch of damped resonance gives it a hollow, woody ring
        ring = np.sin(2 * np.pi * centre * 1.9 * t) * np.exp(-t / (dur * 0.16))
        g = (body * 0.85 + ring * 0.35) * np.exp(-t / max(0.01, dur * 0.26))
        g = g.astype(np.float32)
        peak = float(np.abs(g).max()) or 1.0
        pops.append((g / peak).astype(np.float32))
    return pops


def _scatter(dst: np.ndarray, grain: np.ndarray, start: int, gain: float) -> None:
    """Add `grain` at `start`, WRAPPING around the end of the buffer.

    The wrap is the whole trick: a transient straddling the loop point continues
    into the head of the buffer, so when the file repeats it completes naturally
    instead of being cut off at the seam.
    """
    n = dst.shape[0]
    idx = (np.arange(grain.shape[0]) + start) % n
    np.add.at(dst, idx, grain * gain)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def render_audio(cfg: AudioConfig) -> np.ndarray:
    """Return a seamless stereo loop, shape (n, 2), float32 in [-1, 1]."""
    sr = cfg.sample_rate
    n = int(round(cfg.seconds * sr))
    rng = np.random.default_rng(cfg.seed)

    # --- continuous bed --------------------------------------------------
    # Two decorrelated noise sources (one per channel) is what gives a wide,
    # natural stereo image without any artificial widening.
    hiss = _bed_shape(n, sr, tilt=0.55, low_hz=180.0, high_hz=9000.0)
    roar = _bed_shape(n, sr, tilt=1.25, low_hz=32.0, high_hz=420.0)

    out = np.zeros((n, 2), dtype=np.float32)
    for ch in range(2):
        b = _circular_filtered_noise(n, rng, hiss)
        b /= max(float(np.abs(b).std()), 1e-9)
        r = _circular_filtered_noise(n, rng, roar)
        r /= max(float(np.abs(r).std()), 1e-9)
        out[:, ch] = b * cfg.bed_level + r * (cfg.bed_level * 0.75)

    # --- transients ------------------------------------------------------
    grains = _grain_bank(rng, sr)
    pops = _pop_bank(rng, sr)

    n_crack = int(cfg.seconds * cfg.crackles_per_sec)
    n_pop = max(1, int(cfg.seconds * cfg.pops_per_sec))

    for _ in range(n_crack):
        g = grains[int(rng.integers(len(grains)))]
        start = int(rng.integers(n))
        # amplitude is heavily skewed: many faint ticks, few loud snaps
        amp = float(rng.uniform(0.04, 0.62) ** 2.1) * 1.55
        pan = float(rng.uniform(-0.75, 0.75))
        # equal-power pan keeps perceived loudness constant across the image
        lg = np.cos((pan + 1.0) * np.pi / 4.0)
        rg = np.sin((pan + 1.0) * np.pi / 4.0)
        _scatter(out[:, 0], g, start, amp * lg)
        _scatter(out[:, 1], g, start, amp * rg)

    for _ in range(n_pop):
        g = pops[int(rng.integers(len(pops)))]
        start = int(rng.integers(n))
        amp = float(rng.uniform(0.10, 0.42))
        pan = float(rng.uniform(-0.45, 0.45))
        lg = np.cos((pan + 1.0) * np.pi / 4.0)
        rg = np.sin((pan + 1.0) * np.pi / 4.0)
        _scatter(out[:, 0], g, start, amp * lg)
        _scatter(out[:, 1], g, start, amp * rg)

    # --- level -----------------------------------------------------------
    # ONE fixed gain for the whole file. No compressor, no riding, no fades:
    # anything time-varying here would be audible as pumping over two hours.
    peak = float(np.abs(out).max()) or 1.0
    out *= cfg.target_peak / peak

    # Soft-knee limiter, only biting on isolated pops. tanh above the knee keeps
    # them from clipping without touching the bed at all.
    knee = 0.72
    over = np.abs(out) > knee
    out[over] = np.sign(out[over]) * (
        knee + (1.0 - knee) * np.tanh((np.abs(out[over]) - knee) / (1.0 - knee))
    )
    return out.astype(np.float32)


def write_wav(path: Path, audio: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    """Write 24-bit stereo PCM. 24-bit because the bed sits low and 16-bit
    quantisation noise would be audible under it in a quiet room."""
    a = np.clip(audio, -1.0, 1.0)
    ints = (a * 8_388_607.0).astype(np.int32)
    b = ints.reshape(-1).astype("<i4").tobytes()
    packed = bytearray()
    for i in range(0, len(b), 4):                 # drop the high byte -> 24-bit LE
        packed += b[i:i + 3]

    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(3)
        w.setframerate(sr)
        w.writeframes(bytes(packed))


def seam_error(audio: np.ndarray, sr: int = SAMPLE_RATE) -> float:
    """Max |sample| discontinuity across the loop join, as a QA number.

    Compares the last samples against the first: for a correctly periodic signal
    the step across the join is no larger than a step anywhere else in the file.
    """
    tail = audio[-1]
    head = audio[0]
    join = float(np.abs(head - tail).max())
    typical = float(np.abs(np.diff(audio[: sr * 2], axis=0)).max())
    return join / max(typical, 1e-9)
