"""
Transparent PNG plates for the countdown, drawn with Pillow from the brand
fonts already bundled in config/brand/fonts (Anton / Archivo Black).

Everything is laid out inside the YouTube Shorts safe area for a 1080x1920
frame: top 160 px (search/camera icons), bottom 420 px (title, channel, audio
row) and the right 140 px from mid-frame down (like/comment/share rail) stay
clear of text.
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config import CONFIG_DIR

W, H = 1080, 1920
SAFE = {"top": 160, "bottom": 1500, "left": 60, "right": 940}
# above y=900 there is no action rail on the right, so the header may use a
# symmetric band around the centre line
SAFE_TOP = {"top": 160, "bottom": 900, "left": 60, "right": 1020}
FONT_DIR = CONFIG_DIR / "brand" / "fonts"
CAPTION_POS = (330, 1255)       # right of the rank badge
CAPTION_PAD = 30                # pill padding (24) + outline/shadow margin


def font(size: int, face: str = "Anton-Regular.ttf") -> ImageFont.FreeTypeFont:
    path = FONT_DIR / face
    if not path.exists():
        path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    return ImageFont.truetype(str(path), size)


def _rgb(hex_color: str, a: int = 255) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


def _wrap(draw, text: str, fnt, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def _fit(draw, text: str, max_w: int, max_lines: int, size: int, min_size: int = 40):
    """Largest size (stepping down) at which `text` wraps into `max_lines`."""
    while size > min_size:
        f = font(size)
        lines = _wrap(draw, text, f, max_w)
        if len(lines) <= max_lines and all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, lines
        size -= 4
    f = font(min_size)
    return f, _wrap(draw, text, f, max_w)[:max_lines]


def title_plate(title: str, handle: str, brand: dict, out: Path) -> Path:
    """Persistent header: accent 'TOP 5' tag + headline, with a channel handle."""
    img = Image.new("RGBA", (W, 380), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    accent, ink = brand["accent"], brand["ink"]
    body = re.sub(r"^(TOP\s*)?5\s+", "", title.upper())
    tag_f = font(64)
    tw = d.textlength("TOP 5", font=tag_f)
    x0 = (W - tw - 60) / 2
    d.rounded_rectangle([x0, 10, x0 + tw + 60, 100], radius=18, fill=_rgb(accent))
    d.text((W / 2, 55), "TOP 5", font=tag_f, fill=_rgb(brand["accent_ink"]), anchor="mm")
    f, lines = _fit(d, body, SAFE_TOP["right"] - SAFE_TOP["left"] - 20, 2, 84)
    y, bottom = 120, 120
    for line in lines:
        d.text((W / 2, y), line, font=f, fill=_rgb(ink), anchor="ma",
               stroke_width=7, stroke_fill=(0, 0, 0, 255))
        bottom = d.textbbox((W / 2, y), line, font=f, anchor="ma", stroke_width=7)[3]
        y += int(f.size * 1.08)
    if handle:
        # measured glyph bottom, not the line advance: Anton's ascent is tall
        # enough that an advance-based offset collided with the headline
        d.text((W / 2, min(bottom + 10, 336)), handle, font=font(30, "BarlowCondensed-Bold.ttf"),
               fill=_rgb(ink, 200), anchor="ma", stroke_width=3, stroke_fill=(0, 0, 0, 200))
    img.save(out)
    return out


def rank_badge(rank: int, brand: dict, out: Path) -> Path:
    img = Image.new("RGBA", (260, 210), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill = brand["accent"] if rank == 1 else brand["primary"]
    d.rounded_rectangle([8, 8, 252, 202], radius=34, fill=_rgb(fill),
                        outline=(0, 0, 0, 255), width=6)
    d.text((130, 108), f"#{rank}", font=font(150),
           fill=_rgb(brand["accent_ink"] if rank == 1 else brand["ink"]), anchor="mm",
           stroke_width=5 if rank != 1 else 0, stroke_fill=(0, 0, 0, 255))
    img.save(out)
    return out


def caption_plate(text: str, brand: dict, out: Path) -> Path:
    """White pill with dark type — readable over any footage."""
    max_w = SAFE["right"] - CAPTION_POS[0] - 2 * CAPTION_PAD
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    f, lines = _fit(probe, text.upper(), max_w, 2, 64, 36)
    lh = int(f.size * 1.12)
    w = int(max(probe.textlength(l, font=f) for l in lines)) + 48
    h = lh * len(lines) + 36
    img = Image.new("RGBA", (w + 12, h + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, w + 6, h + 6], radius=24, fill=(255, 255, 255, 245),
                        outline=(0, 0, 0, 255), width=5)
    y = 6 + 18
    for line in lines:
        d.text((6 + w / 2, y), line, font=f, fill=_rgb(brand["bg"]), anchor="ma")
        y += lh
    img.save(out)
    return out


HOOK_H = 250                    # HOOK_Y (1240) + 250 stays inside SAFE bottom (1500)


def hook_plate(text: str, brand: dict, out: Path) -> Path:
    img = Image.new("RGBA", (W, HOOK_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # centred on W/2 but clear of the right rail: half-width <= 940 - 540
    max_w = 2 * (SAFE["right"] - W // 2) - 24
    size = 150
    while True:                 # fit width AND height: two lines must fit the plate
        f, lines = _fit(d, text.upper(), max_w, 2, size, 56)
        # measured: Anton's glyph box reaches ~1.25x the size below the anchor
        last = d.textbbox((0, 0), lines[-1], font=f, anchor="ma", stroke_width=10)[3]
        if 10 + (len(lines) - 1) * int(f.size * 1.05) + last <= HOOK_H or f.size <= 56:
            break
        size = f.size - 6
    y = 10
    for line in lines:
        d.text((W / 2, y), line, font=f, fill=_rgb(brand["accent"]), anchor="ma",
               stroke_width=10, stroke_fill=(0, 0, 0, 255))
        y += int(f.size * 1.05)
    img.save(out)
    return out


def endcard_plate(outro: str, cta: str, brand: dict, out: Path) -> Path:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, 110))
    f, lines = _fit(d, outro.upper(), SAFE["right"] - SAFE["left"], 3, 120, 70)
    y = 640
    for line in lines:
        d.text((W / 2, y), line, font=f, fill=_rgb(brand["ink"]), anchor="ma",
               stroke_width=8, stroke_fill=(0, 0, 0, 255))
        y += int(f.size * 1.1)
    cf = font(58)
    cw = d.textlength(cta.upper(), font=cf)
    y += 50
    d.rounded_rectangle([(W - cw) / 2 - 36, y, (W + cw) / 2 + 36, y + 100], radius=50,
                        fill=_rgb(brand["accent"]))
    d.text((W / 2, y + 50), cta.upper(), font=cf, fill=_rgb(brand["accent_ink"]), anchor="mm")
    img.save(out)
    return out
