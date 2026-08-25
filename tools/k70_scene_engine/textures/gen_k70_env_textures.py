#!/usr/bin/env python3
"""K70 VOXEL V3 -- original pixel-art ENVIRONMENT material generator.
Small, stylized, deliberately non-photoreal tile textures (deterministic
pixel-level variation, not random noise), one square PNG per material,
meant to be sampled with nearest-neighbor filtering and mapped 0..1 across
each block face (see _k70_block_kit.simple_textured_box).

100% original K70 artwork -- no third-party textures.

    .venv-win/Scripts/python.exe tools/k70_scene_engine/textures/gen_k70_env_textures.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "tools" / "k70_scene_engine" / "vendor" / "k70_textures" / "environment"

N = 32  # native tile resolution


def _img():
    return Image.new("RGB", (N, N))


def _checker_speckle(img, base, alt, step, seed_shift=0):
    for y in range(N):
        for x in range(N):
            v = (x // step + y // step + seed_shift) % 2
            img.putpixel((x, y), alt if v == 0 else base)


def gen_concrete():
    img = _img()
    base = (168, 168, 162)
    for y in range(N):
        for x in range(N):
            shade = 6 if (x * 7 + y * 13) % 11 < 3 else (-6 if (x * 5 + y * 3) % 9 < 2 else 0)
            img.putpixel((x, y), tuple(max(0, min(255, c + shade)) for c in base))
    return img


def gen_road():
    img = _img()
    base = (48, 48, 50)
    for y in range(N):
        for x in range(N):
            shade = 5 if (x * 3 + y * 11) % 13 < 3 else 0
            img.putpixel((x, y), tuple(max(0, c + shade) for c in base))
    # lane-marking dash near vertical center
    for y in range(N // 4, 3 * N // 4, 6):
        for yy in range(y, min(y + 3, N)):
            for x in range(N // 2 - 1, N // 2 + 1):
                img.putpixel((x, yy), (210, 200, 150))
    return img


def gen_wood():
    img = _img()
    plank = [(120, 82, 48), (108, 72, 40), (132, 92, 54)]
    for y in range(N):
        band = (y // 5) % len(plank)
        for x in range(N):
            grain = -8 if (x * 3 + y) % 17 < 2 else 0
            base = plank[band]
            img.putpixel((x, y), tuple(max(0, c + grain) for c in base))
        if y % 5 == 0:
            for x in range(N):
                img.putpixel((x, y), tuple(max(0, c - 24) for c in plank[band]))
    return img


def gen_glass():
    img = Image.new("RGB", (N, N), (150, 190, 205))
    for y in range(N):
        for x in range(N):
            if (x + y) % 9 == 0:
                img.putpixel((x, y), (210, 230, 235))
    # frame border
    for i in range(2):
        for x in range(N):
            img.putpixel((x, i), (60, 64, 68)); img.putpixel((x, N - 1 - i), (60, 64, 68))
        for y in range(N):
            img.putpixel((i, y), (60, 64, 68)); img.putpixel((N - 1 - i, y), (60, 64, 68))
    return img


def gen_brick():
    img = _img()
    mortar = (170, 165, 155)
    brick = (150, 70, 55)
    brick_alt = (162, 80, 62)
    img.paste(mortar, (0, 0, N, N))
    row_h = 6
    for by, y0 in enumerate(range(0, N, row_h)):
        offset = 0 if by % 2 == 0 else 4
        for bx in range(-4, N, 8):
            x0 = bx + offset
            col = brick if (bx // 8) % 2 == 0 else brick_alt
            for y in range(y0, min(y0 + row_h - 1, N)):
                for x in range(max(0, x0), min(x0 + 7, N)):
                    img.putpixel((x, y), col)
    return img


def gen_grass():
    img = _img()
    base = (74, 128, 66)
    dark = (60, 108, 54)
    light = (92, 148, 80)
    for y in range(N):
        for x in range(N):
            m = (x * 3 + y * 7) % 13
            col = dark if m < 3 else (light if m > 10 else base)
            img.putpixel((x, y), col)
    return img


def gen_leaves():
    img = _img()
    base = (52, 104, 56)
    dark = (40, 84, 46)
    light = (70, 130, 68)
    for y in range(N):
        for x in range(N):
            m = (x * 5 + y * 5) % 7
            col = dark if m == 0 else (light if m == 3 else base)
            img.putpixel((x, y), col)
    return img


def gen_metal():
    img = _img()
    base = (150, 154, 160)
    for y in range(N):
        for x in range(N):
            shade = 10 if y % 8 == 0 else (-10 if y % 8 == 4 else 0)
            img.putpixel((x, y), tuple(max(0, min(255, c + shade)) for c in base))
    return img


def gen_office_surface():
    img = _img()
    base = (222, 220, 212)
    for y in range(N):
        for x in range(N):
            shade = -6 if (x + y) % 8 == 0 else 0
            img.putpixel((x, y), tuple(max(0, c + shade) for c in base))
    return img


SIGN_DIR = OUT_DIR / "signs"


def gen_sign_texture(text: str, bg=(200, 40, 40), fg=(250, 250, 245), w=128, h=48) -> Image.Image:
    """Original fictional K70 signage (K70 BANK / CAFE / OFFICE / MARKET
    etc.) -- plain bold bitmap text on a flat color panel, deliberately
    small/blocky so it reads as pixel-art signage, not a crisp real-world
    sign. No third-party logos or branding of any kind."""
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w - tw) / 2 - bbox[0], (h - th) / 2 - bbox[1]), text, fill=fg, font=font)
    # border frame
    for i in range(2):
        draw.rectangle([i, i, w - 1 - i, h - 1 - i], outline=tuple(max(0, c - 40) for c in bg))
    return img


SIGN_TEXTS = {
    "sign_k70bank": ("K70 BANK", (40, 60, 110), (240, 240, 245)),
    "sign_cafe": ("CAFE", (110, 60, 30), (245, 235, 210)),
    "sign_office": ("OFFICE", (60, 60, 65), (230, 230, 232)),
    "sign_market": ("MARKET", (30, 100, 50), (240, 240, 220)),
    "sign_busstop": ("BUS STOP", (200, 170, 20), (30, 30, 30)),
    "sign_street12": ("K70 ST. 12", (235, 235, 230), (30, 30, 30)),
}


def generate_signs() -> Path:
    SIGN_DIR.mkdir(parents=True, exist_ok=True)
    for name, (text, bg, fg) in SIGN_TEXTS.items():
        gen_sign_texture(text, bg=bg, fg=fg).save(SIGN_DIR / f"{name}.png")
    print(f"K70 signage generated -> {SIGN_DIR} ({len(SIGN_TEXTS)} signs)")
    return SIGN_DIR


def gen_brick_dark():
    img = _img()
    mortar = (140, 138, 132)
    brick = (96, 96, 100)
    brick_alt = (108, 78, 60)
    img.paste(mortar, (0, 0, N, N))
    row_h = 6
    for by, y0 in enumerate(range(0, N, row_h)):
        offset = 0 if by % 2 == 0 else 4
        for bx in range(-4, N, 8):
            x0 = bx + offset
            col = brick if (bx // 8) % 2 == 0 else brick_alt
            for y in range(y0, min(y0 + row_h - 1, N)):
                for x in range(max(0, x0), min(x0 + 7, N)):
                    img.putpixel((x, y), col)
    return img


def gen_wood_dark():
    img = _img()
    plank = [(72, 50, 30), (64, 44, 26), (80, 56, 34)]
    for y in range(N):
        band = (y // 5) % len(plank)
        for x in range(N):
            grain = -8 if (x * 3 + y) % 17 < 2 else 0
            base = plank[band]
            img.putpixel((x, y), tuple(max(0, c + grain) for c in base))
        if y % 5 == 0:
            for x in range(N):
                img.putpixel((x, y), tuple(max(0, c - 22) for c in plank[band]))
    return img


def gen_road_worn():
    img = gen_road()
    for y in range(0, N, 9):
        for x in range(N):
            if (x + y) % 5 == 0:
                r, g, b = img.getpixel((x, y))
                img.putpixel((x, y), (max(0, r - 14), max(0, g - 14), max(0, b - 14)))
    return img


def gen_glass_tint():
    img = gen_glass()
    for y in range(N):
        for x in range(N):
            r, g, b = img.getpixel((x, y))
            img.putpixel((x, y), (max(0, r - 30), g, min(255, b + 10)))
    return img


GENERATORS = {
    "concrete": gen_concrete, "road": gen_road, "wood": gen_wood, "glass": gen_glass,
    "brick": gen_brick, "grass": gen_grass, "leaves": gen_leaves, "metal": gen_metal,
    "office_surface": gen_office_surface,
    "brick_dark": gen_brick_dark, "wood_dark": gen_wood_dark,
    "road_worn": gen_road_worn, "glass_tint": gen_glass_tint,
}


def generate_all() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in GENERATORS.items():
        fn().save(OUT_DIR / f"{name}.png")
    print(f"K70 environment textures generated -> {OUT_DIR} ({len(GENERATORS)} materials)")
    return OUT_DIR


if __name__ == "__main__":
    generate_all()
    generate_signs()
