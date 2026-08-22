#!/usr/bin/env python3
"""
Kokoro TTS worker (kokoro-onnx, CPU-only) — the primary FREE local narration voice.

Run as an isolated subprocess by the pipeline so onnxruntime never loads into the
API worker and a failure here can't crash the render. Two modes:

  single : python tts_kokoro.py --model M --voices V --voice am_michael \
               --speed 0.98 --out out.wav --text "..."
  batch  : python tts_kokoro.py --model M --voices V --manifest jobs.json
           jobs.json = [{"text": "...", "out": "scene_00.wav",
                         "voice": "am_michael", "speed": 0.98}, ...]

Batch mode loads the 325 MB model ONCE and renders every scene of a short in a
single process — the key win for 500-short automated batches (vs reloading the
model per scene). WAVs are written 24 kHz mono via the stdlib `wave` module (no
soundfile/libsndfile dependency).

Per-item failures don't abort the batch: each successful WAV is still written, and
the exit code is non-zero only if NONE succeeded, so the caller can cascade just
the missing scenes to Piper. Kept dependency-light and deterministic.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import wave

# Keep CPU usage sane on a 4-core laptop and silence onnxruntime chatter.
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("ORT_LOGGING_LEVEL", "3")


def _write_wav(path: str, samples, sr: int) -> bool:
    import numpy as np
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        return False
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--voices", required=True)
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--lang", default="en-us")
    ap.add_argument("--out", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--manifest", default="")
    args = ap.parse_args()

    # Build the job list (single or batch).
    if args.manifest:
        jobs = json.loads(open(args.manifest).read())
    else:
        text = args.text.strip() or sys.stdin.read().strip()
        jobs = [{"text": text, "out": args.out,
                 "voice": args.voice, "speed": args.speed}]
    jobs = [j for j in jobs if (j.get("text") or "").strip() and j.get("out")]
    if not jobs:
        print("kokoro: no jobs", file=sys.stderr)
        return 2

    try:
        from kokoro_onnx import Kokoro
    except Exception as e:  # noqa: BLE001
        print(f"kokoro: import failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    try:
        kokoro = Kokoro(args.model, args.voices)        # load model ONCE
    except Exception as e:  # noqa: BLE001
        print(f"kokoro: model load failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    ok = 0
    for j in jobs:
        try:
            samples, sr = kokoro.create(
                j["text"].strip(),
                voice=j.get("voice") or args.voice,
                speed=max(0.5, min(2.0, float(j.get("speed", args.speed)))),
                lang=args.lang,
            )
            if _write_wav(j["out"], samples, sr):
                ok += 1
            else:
                print(f"kokoro: empty samples for {j['out']}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"kokoro: synth failed for {j['out']}: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)

    print(f"kokoro: {ok}/{len(jobs)} scenes synthesised")
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
