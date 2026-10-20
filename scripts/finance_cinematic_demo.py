"""F1 CPU skyline demo: procedural stills -> real moving 2.5D silent MP4.

This test art is stylized, NOT a real location, original AI video or archival film.
Replace stills with high-quality original/licensed AI-generated finance images.
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.finance_cinematic_cpu import render_clip


def create_example(folder: Path, width: int = 640,
                   height: int = 360, duration: float = 5) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    rand = random.Random(100)
    sky = Image.new("RGB", (width, height))
    pix = sky.load()
    for y in range(height):
        q = y / max(1, height-1)
        for x in range(width):
            halo = max(0, 1-abs(x/width-.75)*2)*.15
            pix[x, y] = (int(8+48*q+60*halo),
                         int(18+40*q+47*halo), int(37+53*q+58*halo))
    d = ImageDraw.Draw(sky)
    for i in range(68):
        w = rand.randint(13, 27)
        x = i*11-30
        y = rand.randint(round(height*.39), round(height*.68))
        d.rectangle((x, y, x+w, height), fill=(21, 37, 56))
        for wx in range(x+4, x+w-2, 7):
            for wy in range(y+8, height, 14):
                if rand.random() > .57:
                    d.rectangle((wx, wy, wx+2, wy+3), fill=(97, 137, 168))
    sky.save(folder/"background.png")

    foreground = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(foreground)
    for i, (x, w, top) in enumerate(((12, 96, 123), (107, 84, 150),
                                    (480, 94, 143), (573, 75, 116))):
        d.rectangle((x, top, x+w, height),
                    fill=(15+4*i, 30+4*i, 50+6*i, 255))
        d.rectangle((x+8, top+14, x+w-8, height),
                    fill=(30+6*i, 50+4*i, 73+5*i, 255))
        for xx in range(x+12, x+w-9, 12):
            for yy in range(top+23, height-10, 15):
                c = (219, 179, 105, 170) if rand.random() > .67 else (93, 147, 167, 175)
                d.rectangle((xx, yy, xx+6, yy+7), fill=c)
    foreground.save(folder/"foreground.png")

    spec = {"background": "background.png",
            "layers": [{"path": "foreground.png", "depth": 0.95, "opacity": 0.92}],
            "width": width, "height": height, "fps": 18,
            "duration_sec": duration, "camera": "dolly_in",
            "camera_strength": 0.12, "seed": 123,
            "effects": {"clouds": True, "dust": True, "light_glow": True}}
    path = folder/"shot.json"
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("data/finance_f1_demo"))
    args = parser.parse_args()
    spec = create_example(args.out_dir)
    print("Spec:", spec)
    print(json.dumps(render_clip(spec, args.out_dir/"demo.mp4",
                                 cache_dir=args.out_dir/"cache"), indent=2))


if __name__ == "__main__":
    main()
