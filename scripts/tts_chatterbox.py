#!/usr/bin/env python3
"""
Isolated Chatterbox worker (zero-shot voice cloning, MIT licence).

Run as a SUBPROCESS by app/voice/engines.py, never imported. Chatterbox pulls in
torch and a multi-gigabyte model; keeping that out of the API worker's address
space means a CUDA/OOM crash kills one scene's synthesis instead of the service,
and the memory is genuinely returned when the process exits.

Chatterbox clones from a short reference clip with no training at all, which makes
it a useful third tier — but it wants a GPU to be practical, so it is disabled by
default in the profile.

    python scripts/tts_chatterbox.py --text "..." --out out.wav \
        --reference data/voice/<id>/reference/ref_01.wav
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--exaggeration", type=float, default=0.4)
    ap.add_argument("--cfg_weight", type=float, default=0.5)
    ap.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args, _unknown = ap.parse_known_args()

    ref = Path(args.reference)
    if not ref.exists():
        print(f"reference clip not found: {ref}", file=sys.stderr)
        return 2

    try:
        import torch                                      # noqa: PLC0415
        from chatterbox.tts import ChatterboxTTS          # noqa: PLC0415
    except ImportError as e:
        print(f"chatterbox not installed ({e}). pip install chatterbox-tts",
              file=sys.stderr)
        return 3

    device = ("cuda" if torch.cuda.is_available() else "cpu") \
        if args.device == "auto" else args.device
    if device == "cuda" and not torch.cuda.is_available():
        print("CUDA requested but unavailable", file=sys.stderr)
        return 4
    model = ChatterboxTTS.from_pretrained(device=device)
    wav = model.generate(
        args.text,
        audio_prompt_path=str(ref),
        exaggeration=args.exaggeration,
        cfg_weight=args.cfg_weight,
    )

    import torchaudio                                     # noqa: PLC0415
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(out), wav, model.sr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
