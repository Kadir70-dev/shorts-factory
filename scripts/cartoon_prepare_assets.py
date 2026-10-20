"""Prepare ChatGPT-generated, separately drawn character parts for CPU animation.

Usage: python scripts/cartoon_prepare_assets.py --spec sheet_spec.json --out data/hero
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api'))
from app.pipeline.cartoon_asset_prep import prepare_assets


def main():
    p = argparse.ArgumentParser(description='Cut named PNG parts / clean sprite sheet into a CPU cartoon rig')
    p.add_argument('--spec', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    manifest, preview = prepare_assets(a.spec, a.out)
    print('Rig:', manifest)
    print('Preview:', preview)
    print('Edit anchors/pivots in cartoon.json after inspecting preview.png')


if __name__ == '__main__':
    main()
