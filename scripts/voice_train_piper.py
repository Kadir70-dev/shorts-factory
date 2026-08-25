#!/usr/bin/env python3
"""
Fine-tune a Piper voice on your recordings — the permanent, free, local clone.

Why Piper is the workhorse for this channel:
  * MIT licence on both code and the base checkpoints, so monetised output is
    unambiguously fine. (XTTS and F5 are better zero-shot, and both ship under
    non-commercial model licences — a problem you find out about at scale.)
  * Fine-tunes to a convincing clone from 20–40 minutes of clean single-speaker
    audio, which is exactly one recording session.
  * Inference is many times faster than real time on a CPU with no GPU, and costs
    nothing per render. At thousands of Shorts that is the difference between a
    viable pipeline and a bill.

TRAINING needs a GPU; INFERENCE does not. This script detects what you have:
  * CUDA available locally → runs the fine-tune here.
  * No GPU → writes a self-contained Colab notebook and a training bundle you
    upload. Free Colab finishes a fine-tune of this size comfortably.

    python scripts/voice_train_piper.py --identity k70_host_v1
    python scripts/voice_train_piper.py --identity k70_host_v1 --run   # force local

The base checkpoint choice matters: fine-tuning from a HIGH-quality single-speaker
English model converges far faster and sounds better than training from scratch or
from a multi-speaker base.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# lessac-high is the usual recommendation for fine-tuning an American English
# voice: single speaker, 22.05 kHz, clean, and it adapts quickly.
BASE_CKPT_URL = ("https://huggingface.co/datasets/rhasspy/piper-checkpoints/"
                 "resolve/main/en/en_US/lessac/high/epoch%3D2218-step%3D838782.ckpt")
BASE_CKPT_NAME = "en_US-lessac-high.ckpt"

DEFAULT_EPOCHS = 2000
DEFAULT_BATCH = 12


def has_cuda() -> bool:
    try:
        import torch                                  # noqa: PLC0415
        return bool(torch.cuda.is_available())
    except Exception:                                 # noqa: BLE001
        return False


def has_piper_train() -> bool:
    try:
        import piper_train                            # noqa: F401,PLC0415
        return True
    except Exception:                                 # noqa: BLE001
        return shutil.which("piper_train") is not None


NOTEBOOK_CELLS = [
    ("markdown", """# Fine-tune a Piper voice — {identity}

Upload `{identity}_training.zip` (produced by `scripts/voice_train_piper.py`) to
this Colab session, then run every cell in order.

Runtime → Change runtime type → **T4 GPU** before you start. A ~25 minute dataset
takes roughly 1–3 hours for a good result; you can stop early and still get a
usable voice, quality just keeps improving.
"""),
    ("code", """!nvidia-smi
!pip -q install piper-tts piper-phonemize 'torch>=2.0' torchaudio \\
    pytorch-lightning==1.9.5 onnx onnxruntime
!git clone -q https://github.com/rhasspy/piper.git /content/piper
%cd /content/piper/src/python
!pip -q install -e ."""),
    ("code", """from google.colab import files
import zipfile, os
os.makedirs('/content/work', exist_ok=True)
up = files.upload()                     # choose {identity}_training.zip
name = list(up)[0]
zipfile.ZipFile(name).extractall('/content/work')
print(sorted(os.listdir('/content/work')))"""),
    ("code", """# Preprocess the LJSpeech-format corpus into Piper's training format
!python -m piper_train.preprocess \\
  --language en-us \\
  --input-dir /content/work/dataset \\
  --output-dir /content/work/training \\
  --dataset-format ljspeech \\
  --single-speaker \\
  --sample-rate 22050"""),
    ("code", """# Fetch the base checkpoint we fine-tune FROM. Starting from a clean
# single-speaker English model converges far faster than training from scratch.
!wget -q -O /content/work/base.ckpt "{base_url}"
!ls -la /content/work/base.ckpt"""),
    ("code", """!python -m piper_train \\
  --dataset-dir /content/work/training \\
  --accelerator gpu --devices 1 \\
  --batch-size {batch} \\
  --validation-split 0.0 --num-test-examples 0 \\
  --max_epochs {epochs} \\
  --resume_from_checkpoint /content/work/base.ckpt \\
  --checkpoint-epochs 25 \\
  --precision 32"""),
    ("code", """# Export the trained checkpoint to the .onnx Piper actually runs
import glob, os
ckpts = sorted(glob.glob('/content/work/training/lightning_logs/*/checkpoints/*.ckpt'),
               key=os.path.getmtime)
print('using', ckpts[-1])
!python -m piper_train.export_onnx "{{ckpts[-1]}}" /content/work/{identity}.onnx
!cp /content/work/training/config.json /content/work/{identity}.onnx.json
from google.colab import files
files.download('/content/work/{identity}.onnx')
files.download('/content/work/{identity}.onnx.json')"""),
    ("markdown", """## Install the finished voice

Put both downloaded files here in your repo:

```
data/models/piper/{identity}/{identity}.onnx
data/models/piper/{identity}/{identity}.onnx.json
```

Then point the profile at it (`config/voice/profile.yaml`):

```yaml
engines:
  piper:
    enabled: true
    model_path: "data/models/piper/{identity}/{identity}.onnx"
```

And check it:

```bash
python scripts/voice_verify.py --identity {identity}
```
"""),
]


def write_notebook(identity: str, out: Path, epochs: int, batch: int) -> None:
    cells = []
    for kind, src in NOTEBOOK_CELLS:
        text = src.format(identity=identity, base_url=BASE_CKPT_URL,
                          epochs=epochs, batch=batch)
        cells.append({
            "cell_type": kind,
            "metadata": {},
            "source": text.splitlines(keepends=True),
            **({"outputs": [], "execution_count": None} if kind == "code" else {}),
        })
    nb = {
        "nbformat": 4, "nbformat_minor": 0,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": [], "gpuType": "T4"},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
        },
        "cells": cells,
    }
    out.write_text(json.dumps(nb, indent=1))


def bundle(voice_dir: Path, identity: str) -> Path:
    """Zip the dataset for upload."""
    dataset = voice_dir / "dataset"
    if not (dataset / "metadata.csv").exists():
        raise SystemExit(
            f"✗ no dataset at {dataset}\n"
            f"  Run: python scripts/voice_build_dataset.py --identity {identity}")
    out = voice_dir / f"{identity}_training"
    archive = shutil.make_archive(str(out), "zip", root_dir=voice_dir,
                                  base_dir="dataset")
    return Path(archive)


def train_locally(voice_dir: Path, identity: str, epochs: int, batch: int) -> int:
    dataset = voice_dir / "dataset"
    training = voice_dir / "training"
    training.mkdir(parents=True, exist_ok=True)
    base = voice_dir / BASE_CKPT_NAME

    if not base.exists():
        print(f"   downloading base checkpoint → {base.name}")
        r = subprocess.run(["curl", "-fL", "--retry", "2", "-o", str(base),
                            BASE_CKPT_URL])
        if r.returncode != 0 or not base.exists():
            print("✗ could not fetch the base checkpoint; fine-tuning from "
                  "scratch is far worse, so stopping here.")
            return 1

    print("   preprocessing …")
    r = subprocess.run([sys.executable, "-m", "piper_train.preprocess",
                        "--language", "en-us", "--input-dir", str(dataset),
                        "--output-dir", str(training), "--dataset-format",
                        "ljspeech", "--single-speaker", "--sample-rate", "22050"])
    if r.returncode != 0:
        return r.returncode

    print(f"   training ({epochs} epochs, batch {batch}) …")
    r = subprocess.run([
        sys.executable, "-m", "piper_train",
        "--dataset-dir", str(training), "--accelerator", "gpu", "--devices", "1",
        "--batch-size", str(batch), "--validation-split", "0.0",
        "--num-test-examples", "0", "--max_epochs", str(epochs),
        "--resume_from_checkpoint", str(base), "--checkpoint-epochs", "25",
        "--precision", "32",
    ])
    if r.returncode != 0:
        return r.returncode

    ckpts = sorted(training.glob("lightning_logs/*/checkpoints/*.ckpt"),
                   key=lambda p: p.stat().st_mtime)
    if not ckpts:
        print("✗ training produced no checkpoint")
        return 1

    model_dir = ROOT / "data" / "models" / "piper" / identity
    model_dir.mkdir(parents=True, exist_ok=True)
    onnx = model_dir / f"{identity}.onnx"
    r = subprocess.run([sys.executable, "-m", "piper_train.export_onnx",
                        str(ckpts[-1]), str(onnx)])
    if r.returncode != 0:
        return r.returncode
    cfg = training / "config.json"
    if cfg.exists():
        shutil.copy2(cfg, onnx.with_suffix(".onnx.json"))

    print(f"\n   ✓ voice model: {onnx}")
    print(f"   Point config/voice/profile.yaml at it:")
    print(f"     engines.piper.model_path: "
          f"\"data/models/piper/{identity}/{identity}.onnx\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", default="k70_host_v1")
    ap.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--run", action="store_true",
                    help="train locally even if no CUDA device is detected")
    args = ap.parse_args()

    voice_dir = ROOT / "data" / "voice" / args.identity
    if not voice_dir.exists():
        print(f"✗ no voice session at {voice_dir}\n"
              f"  Run: python scripts/voice_record_plan.py --identity {args.identity}")
        return 1

    cuda, trainer = has_cuda(), has_piper_train()
    print(f"● Piper fine-tune · identity={args.identity}")
    print(f"   CUDA: {'yes' if cuda else 'no'} · piper_train installed: "
          f"{'yes' if trainer else 'no'}")

    if (cuda and trainer) or args.run:
        if not trainer:
            print("✗ piper_train is not installed. Install it with:\n"
                  "    pip install piper-tts piper-phonemize\n"
                  "    git clone https://github.com/rhasspy/piper && "
                  "pip install -e piper/src/python")
            return 1
        return train_locally(voice_dir, args.identity, args.epochs, args.batch)

    # No GPU: produce everything needed to train elsewhere for free.
    zip_path = bundle(voice_dir, args.identity)
    nb = voice_dir / f"train_{args.identity}_colab.ipynb"
    write_notebook(args.identity, nb, args.epochs, args.batch)

    print("\n   No local GPU — prepared a free-Colab training package instead.")
    print(f"   📦 upload   : {zip_path}  ({zip_path.stat().st_size / 1e6:.1f} MB)")
    print(f"   📓 notebook : {nb}")
    print()
    print("   1. Open the notebook at https://colab.research.google.com "
          "(File → Upload notebook)")
    print("   2. Runtime → Change runtime type → T4 GPU")
    print("   3. Run all cells; upload the zip when prompted")
    print("   4. Download the .onnx + .onnx.json into "
          f"data/models/piper/{args.identity}/")
    print(f"   5. python scripts/voice_verify.py --identity {args.identity}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
