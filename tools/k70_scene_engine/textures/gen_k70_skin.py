#!/usr/bin/env python3
"""K70 VOXEL V3 -- original pixel-art character skin generator.

Generates a small set of PNG texture atlases per character role (head,
torso, arm, leg), each laid out as a 3x2 grid of faces:
    row0 (v: 0.5-1.0): FRONT | BACK | LEFT
    row1 (v: 0.0-0.5): RIGHT | TOP  | BOTTOM
matched 1:1 with the UV layout _k70_block_kit.textured_box() assigns.

This is a 100% original K70 art system -- no Minecraft skin files, no
official textures, no copied assets. Palettes/features are authored here
in code (per-role color config), not extracted from any third-party game.
Everything is generated at a small native pixel resolution and must be
sampled with nearest-neighbor filtering at render time (see
_k70_block_kit.py) to keep pixels crisp -- do not upscale/blur these.

    .venv-win/Scripts/python.exe tools/k70_scene_engine/textures/gen_k70_skin.py [role]
"""
from __future__ import annotations

import colorsys
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "tools" / "k70_scene_engine" / "vendor" / "k70_textures" / "characters"

# Cell pixel sizes per body-part atlas (width, height) -- head gets the
# highest resolution since facial readability matters most in close/medium
# shots; limbs get less since they read fine at a lower texel density.
CELL_SIZES = {
    "head": (32, 32),
    "torso": (28, 32),
    "arm": (16, 32),
    "leg": (16, 32),
    "hand": (12, 12),
    "foot": (16, 10),
}

# ROLE configs: fully original K70 palettes. Each new character (Sarah,
# Banker, Investor, Worker, Business Owner) is just a new entry here --
# the drawing functions below are role-agnostic.
ROLES = {
    "john": {
        "skin": (196, 148, 116), "skin_shadow": (168, 122, 94),
        "hair": (74, 48, 32), "hair_shadow": (54, 34, 22), "hair_light": (96, 66, 46),
        "eye": (46, 40, 90), "eye_white": (238, 238, 240),
        "brow": (54, 34, 22), "mouth": (140, 70, 62),
        "shirt": (46, 92, 150), "shirt_shadow": (34, 70, 118), "shirt_light": (66, 112, 168),
        "cuff": (226, 220, 206),
        "pants": (52, 52, 60), "pants_shadow": (36, 36, 42), "pants_seam": (26, 26, 30),
        "shoe": (28, 24, 22),
        "hair_style": "short_side_part",
    },
}


def _shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def _derive_role(skin, hair, shirt, pants, cuff, eye=(46, 40, 90), mouth=(150, 74, 66),
                 hair_style="short_side_part", shoe=(30, 26, 24), tie=None) -> dict:
    """Fills in the full per-role palette (shadow/light variants) from a
    compact set of base colors -- lets new NPC roles be added as a single
    short call instead of a fully-spelled-out dict like John's."""
    role = {
        "skin": skin, "skin_shadow": _shade(skin, 0.84),
        "hair": hair, "hair_shadow": _shade(hair, 0.72), "hair_light": _shade(hair, 1.28),
        "eye": eye, "eye_white": (238, 238, 240),
        "brow": _shade(hair, 0.72), "mouth": mouth,
        "shirt": shirt, "shirt_shadow": _shade(shirt, 0.76), "shirt_light": _shade(shirt, 1.22),
        "cuff": cuff,
        "pants": pants, "pants_shadow": _shade(pants, 0.76), "pants_seam": _shade(pants, 0.55),
        "shoe": shoe, "hair_style": hair_style,
    }
    if tie is not None:
        role["tie"] = tie
    return role


ROLES["sarah"] = _derive_role(skin=(214, 174, 143), hair=(92, 54, 28), shirt=(158, 51, 89),
                              pants=(40, 38, 44), cuff=(232, 226, 214), hair_style="long")
ROLES["banker"] = _derive_role(skin=(120, 86, 64), hair=(24, 22, 22), shirt=(28, 30, 46),
                               pants=(20, 20, 26), cuff=(235, 232, 226), shoe=(15, 14, 14),
                               tie=(150, 32, 32))
ROLES["investor"] = _derive_role(skin=(112, 80, 58), hair=(28, 24, 22), shirt=(140, 107, 40),
                                 pants=(48, 42, 28), cuff=(222, 210, 180), hair_style="bun")
ROLES["worker"] = _derive_role(skin=(201, 150, 114), hair=(80, 54, 32), shirt=(206, 112, 24),
                               pants=(58, 56, 50), cuff=(230, 224, 210), hair_style="cap")


def _colors_collide(c1, c2, hue_thresh: float = 0.10, val_thresh: float = 0.28) -> bool:
    """Two colors read as 'the same' in a shot only if they're close in
    BOTH hue AND brightness -- hue alone is too crude (John's medium-blue
    shirt and a dark-navy banker suit share a hue neighborhood but are
    obviously distinguishable; the real V5.1 collision was 'worker'
    orange vs 'investor' mustard, which are close in BOTH hue and
    brightness)."""
    h1, _, v1 = colorsys.rgb_to_hsv(*(x / 255.0 for x in c1))
    h2, _, v2 = colorsys.rgb_to_hsv(*(x / 255.0 for x in c2))
    hd = abs(h1 - h2)
    hd = min(hd, 1.0 - hd)
    return hd < hue_thresh and abs(v1 - v2) < val_thresh


def _shift_hue(color, delta):
    h, s, v = colorsys.rgb_to_hsv(*(x / 255.0 for x in color))
    r, g, b = colorsys.hsv_to_rgb((h + delta) % 1.0, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _ensure_palette_separation(roles: dict, anchor_role: str = "john", shift_step: float = 0.14):
    """Automatically separates every NPC's SHIRT color from John's AND
    from every other NPC's shirt color whenever they'd read as the same
    color in a shot (see _colors_collide) -- run once here at module
    load (a general, one-time asset fix), not per-candidate.

    Found necessary during K70 V5.2: 'worker' (orange) and 'investor'
    (mustard) were close enough in BOTH hue and brightness that under
    strong warm golden-hour grading they read as the same color,
    causing the exact character-identity confusion ('is that John or an
    NPC?') this is meant to prevent -- even though neither NPC's color
    actually collided with John's blue by this same test."""
    fixed = [roles[anchor_role]["shirt"]]
    for name, role in roles.items():
        if name == anchor_role:
            continue
        color = role["shirt"]
        attempts = 0
        while any(_colors_collide(color, f) for f in fixed) and attempts < 6:
            color = _shift_hue(color, shift_step)
            attempts += 1
        if color != role["shirt"]:
            role["shirt"] = color
            role["shirt_shadow"] = _shade(color, 0.76)
            role["shirt_light"] = _shade(color, 1.22)
        fixed.append(color)


_ensure_palette_separation(ROLES)


def _cell_box(col: int, row: int, cw: int, ch: int) -> tuple[int, int, int, int]:
    """PIL pixel-space box for a (col,row) cell in a 3-col x 2-row atlas,
    row 0 = TOP of the image (PIL y grows downward) -- matches the UV
    layout in _k70_block_kit.py where UV row1 (v 0.5-1.0) = image row0."""
    x0, y0 = col * cw, row * ch
    return x0, y0, x0 + cw, y0 + ch


def _fill(img: Image.Image, box, color):
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        for x in range(x0, x1):
            img.putpixel((x, y), color)


def _row_band(img: Image.Image, box, color, frac0: float, frac1: float):
    """Fill a horizontal sub-band of a cell (frac measured from the TOP of
    the cell, 0=top/1=bottom) -- used for cuffs, seams, shading bands,
    hairlines, shoe soles etc."""
    x0, y0, x1, y1 = box
    h = y1 - y0
    yb0, yb1 = y0 + int(h * frac0), y0 + int(h * frac1)
    _fill(img, (x0, yb0, x1, max(yb1, yb0 + 1)), color)


def build_head_atlas(role: dict) -> Image.Image:
    cw, ch = CELL_SIZES["head"]
    img = Image.new("RGB", (cw * 3, ch * 2))
    skin, skin_sh = role["skin"], role["skin_shadow"]
    hair, hair_sh, hair_lt = role["hair"], role["hair_shadow"], role["hair_light"]

    front = _cell_box(0, 0, cw, ch)
    back = _cell_box(1, 0, cw, ch)
    left = _cell_box(2, 0, cw, ch)
    right = _cell_box(0, 1, cw, ch)
    top = _cell_box(1, 1, cw, ch)
    bottom = _cell_box(2, 1, cw, ch)

    # ---- FRONT: face ---- #
    _fill(img, front, skin)
    fx0, fy0, fx1, fy1 = front
    fw, fh = fx1 - fx0, fy1 - fy0
    # hairline fringe (jagged: deeper in the middle-third)
    _row_band(img, front, hair, 0.0, 0.22)
    for x in range(fx0 + int(fw * 0.30), fx0 + int(fw * 0.70)):
        for y in range(fy0 + int(fh * 0.22), fy0 + int(fh * 0.30)):
            img.putpixel((x, y), hair)
    # eyebrows -- thicker inner brow tapering to a thinner outer tip (arch)
    for (bx0f, bx1f) in ((0.18, 0.38), (0.62, 0.82)):
        bx0, bx1 = fx0 + int(fw * bx0f), fx0 + int(fw * bx1f)
        _fill(img, (bx0, fy0 + int(fh * 0.355), bx1, fy0 + int(fh * 0.395)), role["brow"])
        _fill(img, (bx0, fy0 + int(fh * 0.34), bx0 + max(1, (bx1 - bx0) // 3), fy0 + int(fh * 0.395)), role["brow"])
    # eyes (white + iris + a small highlight pixel for life)
    for (ex0f, ex1f) in ((0.20, 0.40), (0.60, 0.80)):
        ex0, ex1 = fx0 + int(fw * ex0f), fx0 + int(fw * ex1f)
        ey0, ey1 = fy0 + int(fh * 0.42), fy0 + int(fh * 0.54)
        _fill(img, (ex0, ey0, ex1, ey1), role["eye_white"])
        iris_w = max(2, (ex1 - ex0) // 2)
        ix0 = ex0 + (ex1 - ex0 - iris_w) // 2
        _fill(img, (ix0, ey0 + 1, ix0 + iris_w, ey1 - 1), role["eye"])
        img.putpixel((ix0, ey0 + 1), (255, 255, 255))
    # cheek/jaw shading -- two-tone gradient (subtler mid-tone before the
    # darker jawline band) instead of one flat shadow strip
    _row_band(img, front, _shade(skin, 0.94), 0.80, 0.90)
    # nose hint (very subtle shadow sliver)
    nx = fx0 + fw // 2
    _fill(img, (nx - 1, fy0 + int(fh * 0.55), nx + 1, fy0 + int(fh * 0.66)), skin_sh)
    # mouth
    _fill(img, (fx0 + int(fw * 0.35), fy0 + int(fh * 0.72), fx0 + int(fw * 0.65), fy0 + int(fh * 0.76)), role["mouth"])
    # jaw shading
    _row_band(img, front, skin_sh, 0.90, 1.0)

    hair_style = role.get("hair_style", "short_side_part")

    # ---- BACK: full hair, richer strand variation (denser clusters for "long") ---- #
    _fill(img, back, hair)
    bx0, by0, bx1, by1 = back
    stride = 3 if hair_style == "long" else 5
    for i, x in enumerate(range(bx0, bx1)):
        col = hair_lt if i % stride == 0 else (hair_sh if i % (stride + 2) == 0 else hair)
        _fill(img, (x, by0, x + 1, by1), col)
    if hair_style == "long":
        _row_band(img, back, hair_sh, 0.55, 1.0)  # hair falls past the shoulders, reads darker/longer

    # ---- LEFT / RIGHT: sideburn hair over skin, simple ear ---- #
    for side_box in (left, right):
        sx0, sy0, sx1, sy1 = side_box
        _fill(img, side_box, skin)
        cover = 0.55 if hair_style == "long" else (0.42 if hair_style == "cap" else 0.30)
        _row_band(img, side_box, hair, 0.0, cover)
        sw, sh = sx1 - sx0, sy1 - sy0
        _fill(img, (sx0 + int(sw * 0.05), sy0 + int(sh * 0.45), sx0 + int(sw * 0.22), sy0 + int(sh * 0.62)), skin_sh)

    # ---- TOP: hair with light/shadow patches (+ a bun bump, or a cap brim) ---- #
    _fill(img, top, hair)
    tx0, ty0, tx1, ty1 = top
    for i, y in enumerate(range(ty0, ty1)):
        col = hair_lt if i % 6 == 0 else hair
        _fill(img, (tx0, y, tx1, y + 1), col)
    if hair_style == "bun":
        tw, th_ = tx1 - tx0, ty1 - ty0
        _fill(img, (tx0 + int(tw * 0.35), ty0 + int(th_ * 0.30), tx0 + int(tw * 0.65), ty0 + int(th_ * 0.70)), hair_sh)
    elif hair_style == "cap":
        _fill(img, top, _shade(hair, 1.15))  # cap fabric reads a touch lighter/flatter than loose hair

    # ---- BOTTOM: chin/neck underside ---- #
    _fill(img, bottom, skin_sh)

    return img


def build_torso_atlas(role: dict) -> Image.Image:
    cw, ch = CELL_SIZES["torso"]
    img = Image.new("RGB", (cw * 3, ch * 2))
    shirt, sh_sh, sh_lt = role["shirt"], role["shirt_shadow"], role["shirt_light"]

    cells = {
        "front": _cell_box(0, 0, cw, ch), "back": _cell_box(1, 0, cw, ch), "left": _cell_box(2, 0, cw, ch),
        "right": _cell_box(0, 1, cw, ch), "top": _cell_box(1, 1, cw, ch), "bottom": _cell_box(2, 1, cw, ch),
    }
    for name, box in cells.items():
        _fill(img, box, shirt)
        x0, y0, x1, y1 = box
        w = x1 - x0
        if name in ("front", "back"):
            # collar
            _row_band(img, box, sh_sh, 0.0, 0.10)
            # center seam/button line
            cx = x0 + w // 2
            _fill(img, (cx - 1, y0 + int((y1 - y0) * 0.12), cx + 1, y1), sh_sh)
            # fold shading bands -- alternating shadow/highlight for a
            # woven-fabric read instead of one flat shade repeated
            for i, frac in enumerate((0.32, 0.48, 0.64, 0.80)):
                _row_band(img, box, sh_lt if i % 2 == 0 else sh_sh, frac, frac + 0.035)
            # subtle highlight patch (shoulder-facing light catch)
            _fill(img, (x0 + int(w * 0.10), y0 + int((y1 - y0) * 0.14), x0 + int(w * 0.30), y0 + int((y1 - y0) * 0.30)), sh_lt)
        elif name in ("left", "right"):
            _fill(img, (x1 - 2, y0, x1, y1), sh_sh)  # side seam
            _row_band(img, box, sh_sh, 0.0, 0.10)
        elif name == "top":
            _row_band(img, box, sh_sh, 0.0, 1.0)
    return img


def build_arm_atlas(role: dict) -> Image.Image:
    cw, ch = CELL_SIZES["arm"]
    img = Image.new("RGB", (cw * 3, ch * 2))
    shirt, sh_sh = role["shirt"], role["shirt_shadow"]
    cuff = role["cuff"]
    skin, skin_sh = role["skin"], role["skin_shadow"]

    cells = ["front", "back", "left", "right", "top", "bottom"]
    boxes = {"front": _cell_box(0, 0, cw, ch), "back": _cell_box(1, 0, cw, ch), "left": _cell_box(2, 0, cw, ch),
            "right": _cell_box(0, 1, cw, ch), "top": _cell_box(1, 1, cw, ch), "bottom": _cell_box(2, 1, cw, ch)}
    for name in cells:
        box = boxes[name]
        if name == "top":
            _fill(img, box, sh_sh)
            continue
        if name == "bottom":
            _fill(img, box, skin_sh)
            continue
        _fill(img, box, shirt)
        _row_band(img, box, cuff, 0.62, 0.72)
        _row_band(img, box, skin, 0.72, 1.0)
        _row_band(img, box, skin_sh, 0.95, 1.0)
    return img


def build_leg_atlas(role: dict) -> Image.Image:
    cw, ch = CELL_SIZES["leg"]
    img = Image.new("RGB", (cw * 3, ch * 2))
    pants, pants_sh, seam = role["pants"], role["pants_shadow"], role["pants_seam"]
    shoe = role["shoe"]

    boxes = {"front": _cell_box(0, 0, cw, ch), "back": _cell_box(1, 0, cw, ch), "left": _cell_box(2, 0, cw, ch),
            "right": _cell_box(0, 1, cw, ch), "top": _cell_box(1, 1, cw, ch), "bottom": _cell_box(2, 1, cw, ch)}
    for name, box in boxes.items():
        if name == "top":
            _fill(img, box, pants_sh)
            continue
        if name == "bottom":
            _fill(img, box, (18, 16, 15))
            continue
        _fill(img, box, pants)
        x0, y0, x1, y1 = box
        w = x1 - x0
        if name in ("front", "back"):
            cx = x0 + w // 2
            _fill(img, (cx - 1, y0, cx + 1, y1), seam)
            # subtle woven variation -- two faint vertical pixel columns
            for fx in (0.18, 0.82):
                _fill(img, (x0 + int(w * fx), y0, x0 + int(w * fx) + 1, y0 + int((y1 - y0) * 0.55)), pants_sh)
        _row_band(img, box, pants_sh, 0.55, 0.80)
        _row_band(img, box, shoe, 0.80, 1.0)
        # shoe sole tread line + toe highlight
        _row_band(img, box, _shade(shoe, 0.6), 0.94, 1.0)
        _fill(img, (x0 + int(w * 0.3), y0 + int((y1 - y0) * 0.82), x0 + int(w * 0.7), y0 + int((y1 - y0) * 0.86)), _shade(shoe, 1.4))
    return img


def build_flat_atlas(role: dict, part: str, color) -> Image.Image:
    """Simple flat-but-shaded atlas for small extremity pieces (hands/feet)
    -- a single base color plus a darker underside band, avoiding the
    repeating-gradient artifact a full sleeve/pants atlas would show if
    reused at this tiny scale."""
    cw, ch = CELL_SIZES[part]
    img = Image.new("RGB", (cw * 3, ch * 2))
    shadow = tuple(max(0, c - 28) for c in color)
    for col in range(3):
        for row in range(2):
            box = _cell_box(col, row, cw, ch)
            _fill(img, box, color)
            _row_band(img, box, shadow, 0.82, 1.0)
    return img


def generate(role_name: str) -> Path:
    role = ROLES[role_name]
    out_dir = OUT_DIR / role_name
    out_dir.mkdir(parents=True, exist_ok=True)
    build_head_atlas(role).save(out_dir / "head.png")
    build_torso_atlas(role).save(out_dir / "torso.png")
    build_arm_atlas(role).save(out_dir / "arm.png")
    build_leg_atlas(role).save(out_dir / "leg.png")
    build_flat_atlas(role, "hand", role["skin"]).save(out_dir / "hand.png")
    build_flat_atlas(role, "foot", role["shoe"]).save(out_dir / "foot.png")
    print(f"K70 skin generated for '{role_name}' -> {out_dir}")
    return out_dir


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "john"
    if arg == "all":
        for r in ROLES:
            generate(r)
    else:
        generate(arg)
