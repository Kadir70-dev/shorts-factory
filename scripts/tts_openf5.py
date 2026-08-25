#!/usr/bin/env python3
"""Isolated OpenF5 worker. Only locally installed Apache-2.0 weights are used."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-text", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--vocab", type=Path, required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--nfe-step", type=int, default=32)
    args = parser.parse_args()
    for path in (args.reference, args.model, args.config, args.vocab):
        if not path.is_file():
            parser.error(f"required local file missing: {path}")
    cli = Path(sys.executable).with_name("f5-tts_infer-cli")
    command = [
        str(cli), "-mc", str(args.config),
        "-p", str(args.model), "-v", str(args.vocab),
        "--ref_audio", str(args.reference), "--ref_text", args.reference_text,
        "--gen_text", args.text, "--output_dir", str(args.out.parent),
        "--output_file", args.out.name, "--speed", str(args.speed),
        "--nfe_step", str(args.nfe_step),
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
