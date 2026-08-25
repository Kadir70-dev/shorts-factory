#!/usr/bin/env python3
"""
Turn a raw recording session into everything the cloning engines need.

Produces, from the same source audio:

  dataset/        LJSpeech-format corpus (wav/ + metadata.csv) — what Piper
                  fine-tuning consumes.
  reference/      the three cleanest 8–12 second clips — what zero-shot engines
                  (Chatterbox, XTTS) and the ElevenLabs enrolment use.
  elevenlabs/     concatenated, loudness-matched audio ready to upload as a
                  Professional Voice Clone.
  QUALITY.md      an honest report on whether this session is good enough.

That last one matters more than it sounds. Clone quality is decided almost
entirely at recording time, and a bad session produces a bad clone that you then
use on every video forever. Finding out now — while re-recording costs 25 minutes
— is worth far more than finding out after a hundred uploads.

    python scripts/voice_build_dataset.py --identity k70_host_v1

Processing is deliberately conservative: DC offset removal, a gentle high-pass to
drop rumble, light broadband denoise, silence trimming, and peak normalisation to
a consistent level. No compression, no EQ shaping, no gating — every one of those
teaches the clone an artifact instead of a voice.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGET_SR = 22050          # Piper's training rate; also fine for reference clips
MIN_TAKE_SEC = 1.0
MAX_TAKE_SEC = 30.0
TARGET_PEAK_DB = -3.0

# Session-quality thresholds. Below these the clone will be audibly compromised.
MIN_TOTAL_MINUTES = 12.0
GOOD_TOTAL_MINUTES = 20.0
MAX_CLIPPED_FRACTION = 0.001
MIN_SNR_DB = 20.0
GOOD_SNR_DB = 30.0


@dataclass
class Take:
    take_id: str
    text: str
    src: Path
    out: Path | None = None
    seconds: float = 0.0
    peak_db: float = 0.0
    noise_db: float = 0.0
    speech_db: float = 0.0
    clipped: float = 0.0

    @property
    def snr_db(self) -> float:
        return self.speech_db - self.noise_db


# --------------------------------------------------------------------------- #
# ffmpeg / ffprobe helpers
# --------------------------------------------------------------------------- #
def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def _duration(path: Path) -> float:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _measure(path: Path) -> tuple[float, float]:
    """(peak dBFS, RMS dBFS) via astats."""
    r = _run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
              "astats=metadata=1:reset=0", "-f", "null", "-"])
    peak, rms = -99.0, -99.0
    for line in r.stderr.splitlines():
        if "Peak level dB" in line:
            peak = _num(line, peak)
        elif "RMS level dB" in line:
            rms = _num(line, rms)
    return peak, rms


def _num(line: str, default: float) -> float:
    try:
        return float(line.split(":")[-1].strip())
    except ValueError:
        return default


def _noise_floor(path: Path) -> float:
    """RMS of the quietest half-second — the room tone the mic is picking up."""
    dur = _duration(path)
    if dur < 1.5:
        return -60.0
    best = 0.0
    # sample a few windows rather than every one; this runs per take
    for frac in (0.02, 0.25, 0.5, 0.75, 0.96):
        start = max(0.0, min(dur - 0.5, dur * frac))
        r = _run(["ffmpeg", "-hide_banner", "-ss", f"{start:.2f}", "-t", "0.5",
                  "-i", str(path), "-af", "astats=metadata=1:reset=0",
                  "-f", "null", "-"])
        for line in r.stderr.splitlines():
            if "RMS level dB" in line:
                v = _num(line, 0.0)
                best = min(best, v) if best else v
    return best or -60.0


def _clipped_fraction(path: Path) -> float:
    """Share of samples at full scale. Any meaningful amount means the take is
    unusable: the clone learns the distortion, not the voice."""
    r = _run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
              "astats=metadata=1:reset=0", "-f", "null", "-"])
    flat, total = 0.0, 0.0
    for line in r.stderr.splitlines():
        if "Number of samples" in line:
            total = max(total, _num(line, 0.0))
        elif "Flat factor" in line or "Number of clipped samples" in line:
            flat = max(flat, _num(line, 0.0))
    return (flat / total) if total else 0.0


# --------------------------------------------------------------------------- #
# Source discovery
# --------------------------------------------------------------------------- #
def load_manifest(voice_dir: Path) -> dict:
    mf = voice_dir / "manifest.json"
    if not mf.exists():
        raise SystemExit(
            f"✗ no manifest at {mf}\n"
            f"  Run: python scripts/voice_record_plan.py --identity "
            f"{voice_dir.name}")
    return json.loads(mf.read_text())


def split_continuous(session: Path, raw_dir: Path, expected: int) -> list[Path]:
    """Split one long recording on silence into per-take files.

    Anyone who records 25 minutes in a single pass would otherwise have to
    hand-cut 70 clips, which is the step where people give up.
    """
    print(f"   splitting {session.name} on silence …")
    out_dir = raw_dir / "_split"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    r = _run(["ffmpeg", "-hide_banner", "-i", str(session), "-af",
              "silencedetect=noise=-38dB:d=0.7", "-f", "null", "-"])

    marks: list[tuple[float, float]] = []
    start = 0.0
    for line in r.stderr.splitlines():
        if "silence_start" in line:
            try:
                end = float(line.split("silence_start:")[1].strip())
            except (IndexError, ValueError):
                continue
            if end - start >= MIN_TAKE_SEC:
                marks.append((start, end))
        elif "silence_end" in line:
            try:
                start = float(line.split("silence_end:")[1].split("|")[0].strip())
            except (IndexError, ValueError):
                continue
    total = _duration(session)
    if total - start >= MIN_TAKE_SEC:
        marks.append((start, total))

    print(f"   found {len(marks)} segments (expected ~{expected})")
    out: list[Path] = []
    for i, (a, b) in enumerate(marks, 1):
        p = out_dir / f"{i:03d}.wav"
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{a:.3f}",
              "-t", f"{b - a:.3f}", "-i", str(session), "-y", str(p)])
        if p.exists():
            out.append(p)
    return out


def collect(voice_dir: Path, manifest: dict) -> list[Take]:
    raw = voice_dir / "raw"
    takes_meta = {t["id"]: t["text"] for t in manifest["takes"]}
    session = next((p for p in (raw / "session.wav", raw / "session.WAV",
                                raw / "session.m4a", raw / "session.mp3")
                    if p.exists()), None)

    if session:
        parts = split_continuous(session, raw, len(takes_meta))
        ids = sorted(takes_meta)
        return [Take(take_id=ids[i], text=takes_meta[ids[i]], src=p)
                for i, p in enumerate(parts) if i < len(ids)]

    found: list[Take] = []
    for tid, text in sorted(takes_meta.items()):
        for ext in (".wav", ".WAV", ".flac", ".m4a", ".mp3"):
            p = raw / f"{tid}{ext}"
            if p.exists():
                found.append(Take(take_id=tid, text=text, src=p))
                break
    return found


# --------------------------------------------------------------------------- #
# Processing
# --------------------------------------------------------------------------- #
def process(take: Take, out_dir: Path) -> bool:
    """Clean one take into the training corpus. Returns False if unusable."""
    out = out_dir / f"{take.take_id}.wav"
    # Conservative chain, in order:
    #   highpass  — remove rumble/handling below the voice
    #   afftdn    — light broadband denoise (nr=10 is gentle; higher smears speech)
    #   silenceremove — trim leading/trailing silence, keep a little padding
    #   dynaudnorm off; loudness handled by a single peak normalise
    chain = (
        "highpass=f=70,"
        "afftdn=nr=10:nf=-28,"
        "silenceremove=start_periods=1:start_silence=0.12:start_threshold=-45dB:"
        "detection=peak,"
        "areverse,"
        "silenceremove=start_periods=1:start_silence=0.20:start_threshold=-45dB:"
        "detection=peak,"
        "areverse,"
        f"volume={TARGET_PEAK_DB}dB:precision=float,"
        f"aresample={TARGET_SR}:resampler=soxr"
    )
    r = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(take.src),
              "-af", chain, "-ac", "1", "-ar", str(TARGET_SR),
              "-c:a", "pcm_s16le", "-y", str(out)])
    if r.returncode != 0 or not out.exists():
        return False

    take.out = out
    take.seconds = _duration(out)
    if not (MIN_TAKE_SEC <= take.seconds <= MAX_TAKE_SEC):
        out.unlink(missing_ok=True)
        take.out = None
        return False

    take.peak_db, take.speech_db = _measure(out)
    take.noise_db = _noise_floor(take.src)
    take.clipped = _clipped_fraction(take.src)
    return True


def write_dataset(takes: list[Take], dataset: Path) -> None:
    """LJSpeech layout: wavs/<id>.wav plus metadata.csv of `id|text|text`."""
    (dataset / "wavs").mkdir(parents=True, exist_ok=True)
    rows = []
    for t in takes:
        if not t.out:
            continue
        dst = dataset / "wavs" / f"{t.take_id}.wav"
        shutil.copy2(t.out, dst)
        rows.append(f"{t.take_id}|{t.text}|{t.text}")
    (dataset / "metadata.csv").write_text("\n".join(rows) + "\n")


def write_reference(takes: list[Take], ref_dir: Path, count: int = 3) -> list[Path]:
    """The cleanest medium-length takes: best SNR, 8–12s, for zero-shot cloning."""
    ref_dir.mkdir(parents=True, exist_ok=True)
    for old in ref_dir.glob("ref_*.wav"):
        old.unlink()
    ideal = [t for t in takes if t.out and 7.0 <= t.seconds <= 14.0]
    ideal.sort(key=lambda t: -t.snr_db)
    out: list[Path] = []
    for i, t in enumerate(ideal[:count], 1):
        dst = ref_dir / f"ref_{i:02d}.wav"
        shutil.copy2(t.out, dst)
        out.append(dst)
    return out


def write_elevenlabs(takes: list[Take], el_dir: Path) -> Path | None:
    """One concatenated, loudness-normalised file for a Professional Voice Clone.

    ElevenLabs wants a long continuous sample rather than dozens of fragments, and
    consistent loudness across it — otherwise the clone learns to vary its level.
    """
    usable = [t for t in takes if t.out]
    if not usable:
        return None
    el_dir.mkdir(parents=True, exist_ok=True)
    listing = el_dir / "_concat.txt"
    listing.write_text("\n".join(f"file '{t.out.resolve()}'" for t in usable))
    out = el_dir / "professional_clone_source.wav"
    r = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat",
              "-safe", "0", "-i", str(listing), "-af",
              "loudnorm=I=-19:TP=-2.0:LRA=9,aresample=44100:resampler=soxr",
              "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", "-y", str(out)])
    listing.unlink(missing_ok=True)
    return out if r.returncode == 0 and out.exists() else None


# --------------------------------------------------------------------------- #
# Quality report
# --------------------------------------------------------------------------- #
def quality_report(takes: list[Take], identity: str, total_min: float) -> tuple[str, bool]:
    usable = [t for t in takes if t.out]
    snrs = sorted(t.snr_db for t in usable) or [0.0]
    median_snr = snrs[len(snrs) // 2]
    clipped = [t for t in usable if t.clipped > MAX_CLIPPED_FRACTION]
    quiet = [t for t in usable if t.snr_db < MIN_SNR_DB]

    problems: list[str] = []
    warnings: list[str] = []

    if total_min < MIN_TOTAL_MINUTES:
        problems.append(
            f"Only {total_min:.1f} minutes of usable audio. Piper fine-tuning "
            f"needs at least {MIN_TOTAL_MINUTES:.0f}, and an ElevenLabs "
            f"professional clone wants ~30. Record more takes.")
    elif total_min < GOOD_TOTAL_MINUTES:
        warnings.append(
            f"{total_min:.1f} minutes is workable but thin. {GOOD_TOTAL_MINUTES:.0f}+ "
            "produces a noticeably more natural clone.")

    if median_snr < MIN_SNR_DB:
        problems.append(
            f"Median signal-to-noise is {median_snr:.0f} dB. Below "
            f"{MIN_SNR_DB:.0f} dB the clone learns your room's hiss along with "
            "your voice. Record somewhere quieter or closer to the mic — this "
            "cannot be fixed later.")
    elif median_snr < GOOD_SNR_DB:
        warnings.append(
            f"Median SNR {median_snr:.0f} dB is acceptable; {GOOD_SNR_DB:.0f}+ is "
            "where clones stop sounding slightly veiled.")

    if clipped:
        problems.append(
            f"{len(clipped)} take(s) clipped: {', '.join(t.take_id for t in clipped[:6])}. "
            "Clipping is permanent distortion — re-record these with more headroom.")
    if quiet:
        warnings.append(
            f"{len(quiet)} take(s) below {MIN_TOTAL_MINUTES:.0f} dB SNR were kept "
            "but are the weakest material in the set.")

    lines = [
        f"# Voice dataset quality — {identity}", "",
        f"- usable takes: **{len(usable)}** of {len(takes)}",
        f"- total speech: **{total_min:.1f} minutes**",
        f"- median SNR: **{median_snr:.0f} dB**",
        f"- clipped takes: **{len(clipped)}**", "",
    ]
    if problems:
        lines += ["## Must fix", ""] + [f"- {p}" for p in problems] + [""]
    if warnings:
        lines += ["## Worth improving", ""] + [f"- {w}" for w in warnings] + [""]
    if not problems and not warnings:
        lines += ["## Verdict", "",
                  "Clean session. Good enough for both a Piper fine-tune and an "
                  "ElevenLabs professional clone.", ""]

    lines += ["## Per-take", "",
              "| take | sec | SNR dB | peak dB | clipped |",
              "|------|-----|--------|---------|---------|"]
    for t in takes:
        if not t.out:
            lines.append(f"| {t.take_id} | — | — | — | REJECTED |")
        else:
            lines.append(f"| {t.take_id} | {t.seconds:.1f} | {t.snr_db:.0f} | "
                         f"{t.peak_db:.1f} | {t.clipped:.4f} |")
    return "\n".join(lines), not problems


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", default="k70_host_v1")
    ap.add_argument("--force", action="store_true",
                    help="build the dataset even if the quality gate fails")
    args = ap.parse_args()

    voice_dir = ROOT / "data" / "voice" / args.identity
    manifest = load_manifest(voice_dir)
    takes = collect(voice_dir, manifest)
    if not takes:
        print(f"✗ no recordings found in {voice_dir / 'raw'}\n"
              f"  Expected <take-id>.wav files, or a single session.wav.")
        return 1

    print(f"● Building voice dataset '{args.identity}' from {len(takes)} recording(s)")
    work = voice_dir / "_clean"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    kept = 0
    for i, t in enumerate(takes, 1):
        ok = process(t, work)
        kept += int(ok)
        if i % 10 == 0 or i == len(takes):
            print(f"   processed {i}/{len(takes)} ({kept} usable)")

    usable = [t for t in takes if t.out]
    total_min = sum(t.seconds for t in usable) / 60.0
    report, passed = quality_report(takes, args.identity, total_min)
    (voice_dir / "QUALITY.md").write_text(report)

    if not passed and not args.force:
        print()
        print(report.split("## Per-take")[0])
        print(f"   📄 full report: {voice_dir / 'QUALITY.md'}")
        print("\n✗ Quality gate failed. Fix the issues above and re-run, or pass "
              "--force to build anyway.\n  Re-recording now costs 25 minutes; a "
              "weak clone costs every video you make from here.")
        return 1

    dataset = voice_dir / "dataset"
    if dataset.exists():
        shutil.rmtree(dataset)
    write_dataset(usable, dataset)
    refs = write_reference(usable, voice_dir / "reference")
    el = write_elevenlabs(usable, voice_dir / "elevenlabs")
    shutil.rmtree(work, ignore_errors=True)

    print()
    print(f"   ✓ dataset    : {dataset}  ({len(usable)} clips · {total_min:.1f} min)")
    print(f"   ✓ reference  : {len(refs)} clip(s) in {voice_dir / 'reference'}")
    if el:
        print(f"   ✓ ElevenLabs : {el}  ({el.stat().st_size / 1e6:.1f} MB)")
    print(f"   📄 quality    : {voice_dir / 'QUALITY.md'}")
    print()
    print("   Next:")
    print(f"     · local clone (free, permanent)  → python scripts/voice_train_piper.py "
          f"--identity {args.identity}")
    print(f"     · premium clone (paid)           → python scripts/voice_enroll_elevenlabs.py "
          f"--identity {args.identity}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
