#!/usr/bin/env python3
"""
Check the cloned voice before it narrates a thousand videos.

Renders the same fixed passage through every engine holding your identity and
reports what each one did. Two things it is actually checking:

  1. AVAILABILITY — is the identity lock satisfiable? If the pipeline would refuse
     to render, you want to know here, not at 3am in the middle of a batch.
  2. CONSISTENCY — do the tiers agree? A premium tier that speaks 30% faster than
     the local one means viewers hear a different narrator depending on whether
     credits were available that day, which defeats the entire point of cloning a
     voice. Duration and loudness are compared across tiers and flagged.

The passage is deliberately full of the things this channel says — percentages,
magnitudes, agencies, years — because those are what a clone gets wrong.

    python scripts/voice_verify.py --identity k70_host_v1
    python scripts/voice_verify.py --keep       # keep the wavs to listen to
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

PASSAGE = (
    "According to the BLS, the Consumer Price Index rose 3.4% year over year, "
    "the fastest pace since 2022. The company reported $4.2B in revenue, and its "
    "margin expanded from 11% to 19% in three years. That is the number to watch."
)

# Tolerances between tiers. Beyond these, a viewer would notice the difference.
MAX_DURATION_SPREAD = 0.18      # 18% — pacing drift becomes audible
MAX_LOUDNESS_SPREAD = 3.0       # dB


def _duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _loudness(p: Path) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(p), "-af",
                        "ebur128=framelog=quiet", "-f", "null", "-"],
                       capture_output=True, text=True)
    for line in reversed(r.stderr.splitlines()):
        if "I:" in line and "LUFS" in line:
            try:
                return float(line.split("I:")[1].split("LUFS")[0].strip())
            except (IndexError, ValueError):
                continue
    return 0.0


async def run(identity: str, keep: bool) -> int:
    from app.voice import load_profile, speakable
    from app.voice import engines as eng

    profile = load_profile()
    if not profile.exists:
        print("✗ no config/voice/profile.yaml\n"
              "  cp config/voice/profile.example.yaml config/voice/profile.yaml")
        return 1

    print(f"● Voice identity: {profile.identity or '(unnamed)'} "
          f"— {profile.display_name}")
    print(f"   locked={profile.locked} · stock fallback="
          f"{profile.allow_stock_fallback} · speed={profile.speed}")
    print("\n   Engines:")
    for line in profile.diagnostics():
        print(line)

    cascade = profile.cascade()
    if not cascade:
        print("\n✗ NO engine holds this voice. With locked: true every render "
              "will fail.\n"
              "  Build the local clone first — it is free and permanent:\n"
              f"    python scripts/voice_record_plan.py --identity {identity}\n"
              f"    python scripts/voice_build_dataset.py --identity {identity}\n"
              f"    python scripts/voice_train_piper.py --identity {identity}")
        return 1

    print(f"\n   Cascade: {' → '.join(cascade)}")
    spoken = speakable(PASSAGE, profile)
    print(f"\n   Written : {PASSAGE}")
    print(f"   Spoken  : {spoken}\n")

    out_dir = ROOT / "data" / "voice" / identity / "verify"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, Path, float, float]] = []
    for name in cascade:
        wav = out_dir / f"{name}.wav"
        try:
            # Force a single engine by testing its adapter directly, so one
            # working tier can't mask another that is broken.
            single = _only(profile, name)
            used = await eng.synthesize(spoken, wav, single)
            dur, lufs = _duration(wav), _loudness(wav)
            results.append((used, wav, dur, lufs))
            print(f"   ✓ {name:12} {dur:5.2f}s  {lufs:6.1f} LUFS  {wav}")
        except Exception as e:                        # noqa: BLE001
            print(f"   ✗ {name:12} {type(e).__name__}: {str(e)[:110]}")

    if not results:
        print("\n✗ every engine failed — the pipeline cannot narrate.")
        return 1

    print()
    if len(results) > 1:
        durs = [d for *_, d, _ in results]
        lufs = [l for *_, l in results]
        spread = (max(durs) - min(durs)) / max(durs)
        loud_spread = max(lufs) - min(lufs)
        print(f"   Cross-tier consistency: duration spread {spread * 100:.0f}%, "
              f"loudness spread {loud_spread:.1f} dB")
        if spread > MAX_DURATION_SPREAD:
            print(f"   ⚠ Tiers differ in pacing by more than "
                  f"{MAX_DURATION_SPREAD * 100:.0f}%. Viewers would hear a "
                  "different narrator depending on which tier ran.\n"
                  "     Adjust prosody.speed, or the per-engine settings, until "
                  "they converge.")
        if loud_spread > MAX_LOUDNESS_SPREAD:
            print(f"   ⚠ Loudness differs by {loud_spread:.1f} dB across tiers. "
                  "The post stage normalises the final mix, so this is minor, "
                  "but large gaps can change perceived delivery.")
        if spread <= MAX_DURATION_SPREAD and loud_spread <= MAX_LOUDNESS_SPREAD:
            print("   ✓ Tiers are consistent — a fallback changes fidelity, not "
                  "identity.")
    else:
        print("   Only one tier is available. Build the local Piper clone too so "
              "a credit outage can't stop the channel.")

    if keep:
        print(f"\n   🎧 Listen and compare: {out_dir}")
    else:
        for _, p, *_ in results:
            p.unlink(missing_ok=True)
    return 0


def _only(profile, name: str):
    """A copy of the profile exposing exactly one engine."""
    import copy                                       # noqa: PLC0415
    p = copy.copy(profile)
    p.engines = {name: profile.engines[name]}
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", default="k70_host_v1")
    ap.add_argument("--keep", action="store_true",
                    help="keep the rendered wavs so you can listen to them")
    args = ap.parse_args()
    return asyncio.run(run(args.identity, args.keep))


if __name__ == "__main__":
    sys.exit(main())
