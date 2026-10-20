"""Produce demo transparent sprite layers, an editable manifest, and 5s MP4.

Run from repository root: python scripts/cartoon_cpu_demo.py
No AI model, GPU or network is involved; real user art should replace sprites.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api'))
from app.pipeline.cartoon_motion_cpu import render_manifest  # noqa: E402


def _sprite(folder: Path, name: str, size: tuple[int, int], drawer) -> None:
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    drawer(ImageDraw.Draw(image))
    image.save(folder / f'{name}.png')


def create_example(folder: Path, *, landscape: bool = False) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    art = folder / 'assets'
    art.mkdir(exist_ok=True)
    _sprite(art, 'body', (110, 145), lambda d: d.rounded_rectangle((10, 5, 100, 142),
             radius=18, fill='#ffd54e', outline='#a65a36', width=3))
    def head(d):
        d.ellipse((8, 6, 112, 120), fill='#f6b97d', outline='#543d35', width=3)
        d.pieslice((7, -19, 111, 76), 180, 350, fill='#342e38')
    _sprite(art, 'head', (120, 128), head)
    def arm(d):
        d.rounded_rectangle((5, 4, 33, 103), radius=13, fill='#ffd54e', outline='#b67637', width=2)
        d.ellipse((7, 91, 32, 115), fill='#f6b97d', outline='#a66447', width=2)
    _sprite(art, 'arm', (38, 116), arm)
    def leg(d):
        d.rounded_rectangle((7, 3, 31, 107), radius=8, fill='#425fa5')
        d.rounded_rectangle((2, 102, 38, 127), radius=10, fill='#f9f9f9', outline='#45525e', width=2)
    _sprite(art, 'leg', (39, 130), leg)
    def eye(d):
        d.ellipse((2, 1, 20, 24), fill='white', outline='#513c32', width=2)
        d.ellipse((9, 6, 16, 19), fill='#30272a')
    _sprite(art, 'eye', (22, 25), eye)
    both = Image.new('RGBA', (59, 25), (0, 0, 0, 0))
    eye_png = Image.open(art / 'eye.png').convert('RGBA')
    both.alpha_composite(eye_png, (0, 0))
    both.alpha_composite(eye_png, (37, 0))
    both.save(art / 'eyes_open.png')
    _sprite(art, 'closed', (22, 25), lambda d: d.arc((2, 7, 20, 19), 0, 180,
                                                         fill='#45332e', width=3))
    both_closed = Image.new('RGBA', (59, 25), (0, 0, 0, 0))
    closed_png = Image.open(art / 'closed.png').convert('RGBA')
    both_closed.alpha_composite(closed_png, (0, 0))
    both_closed.alpha_composite(closed_png, (37, 0))
    both_closed.save(art / 'eyes_closed.png')
    _sprite(art, 'mouth_closed', (27, 21), lambda d: d.arc((2, 1, 24, 16), 5, 175,
                                                                fill='#713c46', width=3))
    _sprite(art, 'mouth_open', (27, 21), lambda d: d.ellipse((5, 1, 23, 20),
                                                                fill='#8b3654', outline='#602c45', width=2))
    width, height = (640, 360) if landscape else (360, 640)
    ox = 140 if landscape else 0
    oy = -120 if landscape else 0
    def p(x: int, y: int):
        return [x + ox, y + oy]
    def sprite(file: str, anchor: list[int], pivot: list[int]):
        return {'file': f'assets/{file}.png', 'anchor': anchor, 'pivot': pivot}
    manifest = {
        'width': width, 'height': height, 'fps': 12, 'duration_sec': 5,
        'background_color': '#b8e6fd',
        'motions': ['idle', 'wave', 'blink', 'talk', 'nod', 'walk'],
        'rig': {
            'body': sprite('body', p(180, 294), [55, 16]),
            'head': sprite('head', p(180, 256), [60, 114]),
            'arm_left': sprite('arm', p(132, 302), [19, 10]),
            'arm_right': sprite('arm', p(226, 302), [19, 10]),
            'leg_left': sprite('leg', p(157, 425), [18, 8]),
            'leg_right': sprite('leg', p(203, 425), [18, 8]),
            'eyes_open': sprite('eyes_open', [33, 58], [0, 0]),
            'eyes_closed': sprite('eyes_closed', [33, 58], [0, 0]),
            'mouth_open': sprite('mouth_open', [47, 90], [0, 0]),
            'mouth_closed': sprite('mouth_closed', [47, 90], [0, 0]),
        },
    }
    file = folder / 'cartoon.json'
    file.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path, default=Path('data/cartoon_demo'))
    parser.add_argument('--landscape', action='store_true')
    args = parser.parse_args()
    file = create_example(args.out_dir, landscape=args.landscape)
    out = args.out_dir / 'demo.mp4'
    print('MANIFEST', file)
    print('MP4', render_manifest(file, out))


if __name__ == '__main__':
    main()
