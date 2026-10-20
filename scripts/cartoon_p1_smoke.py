"""End-to-end P1 demo: asset sheet -> transparent cutouts -> rig -> moving MP4.

No API keys or GPU. Example images are programmatically drawn, NOT AI-generated.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api'))
from app.pipeline.cartoon_asset_prep import prepare_assets  # noqa: E402
from app.pipeline.cartoon_motion_cpu import render_manifest  # noqa: E402
from cartoon_cpu_demo import create_example  # noqa: E402

ORDER = ['head', 'body', 'arm_left', 'arm_right', 'leg_left', 'leg_right',
         'eyes_open', 'eyes_closed', 'mouth_open', 'mouth_closed']
NAME = {'arm_left': 'arm', 'arm_right': 'arm', 'leg_left': 'leg', 'leg_right': 'leg'}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, default=Path('data/cartoon_p1_smoke'))
    parser.add_argument('--duration', type=float, default=5)
    args = parser.parse_args()
    source = args.out_dir / 'source'
    create_example(source)
    sheet = Image.new('RGB', (800, 600), 'white')
    for i, part in enumerate(ORDER):
        img = Image.open(source / 'assets' / f'{NAME.get(part, part)}.png').convert('RGBA')
        row, col = divmod(i, 4)
        sheet.paste(img, (col * 200 + 30, row * 200 + 20), img)
    sheet.save(source / 'character_parts_sheet.png')
    (source / 'sheet_spec.json').write_text(json.dumps({
        'source': 'sheet', 'sheet': 'character_parts_sheet.png', 'grid': [3, 4],
        'fps': 12, 'width': 360, 'height': 640, 'duration_sec': args.duration,
        'motions': ['idle', 'wave', 'blink', 'talk', 'nod', 'walk'],
    }, indent=2))
    manifest, preview = prepare_assets(source / 'sheet_spec.json', args.out_dir / 'prepared')
    movie = render_manifest(manifest, args.out_dir / 'prepared' / 'demo.mp4')
    print('Sheet:', source / 'character_parts_sheet.png')
    print('Rig:', manifest)
    print('Preview:', preview)
    print('MP4:', movie)


if __name__ == '__main__':
    main()
