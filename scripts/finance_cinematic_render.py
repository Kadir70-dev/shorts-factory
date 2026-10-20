"""CLI: python scripts/finance_cinematic_render.py --spec shot.json --out shot.mp4"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.finance_cinematic_cpu import render_clip


def main() -> None:
    parser = argparse.ArgumentParser(description="F1 CPU 2.5D finance cinematic clip renderer")
    parser.add_argument("--spec", type=Path, required=True, help="JSON spec with relative local images")
    parser.add_argument("--out", type=Path, required=True, help="silent H.264 MP4")
    parser.add_argument("--cache-dir", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(render_clip(args.spec, args.out, cache_dir=args.cache_dir), indent=2))


if __name__ == "__main__":
    main()
