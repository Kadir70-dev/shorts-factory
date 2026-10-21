"""K70 P3.2: portrait (1080x1920) still plates for reviewed archival evidence.

A landscape archival still cover-cropped to 9:16 loses most of its subject (a
banknote becomes its middle third). These plates keep the WHOLE source image
on a blurred copy of itself, with an honest date/identity label baked inside the
ken-burns safe area. Typography plates carry only factual text already present
in the narration or source overlay. Pure Pillow, no network, no rendering.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
SAFE_W = 860            # ken-burns travel (~15%) crops ~70px per side
_FONTS = Path("/usr/share/fonts/truetype/noto")
_NAVY = (21, 35, 58)


def _font(size: int, bold: bool = False, serif: bool = False):
    name = ("NotoSerif" if serif else "NotoSans") + ("-Bold" if bold else "-Regular")
    try:
        return ImageFont.truetype(str(_FONTS / f"{name}.ttf"), size)
    except OSError:
        return ImageFont.load_default()


def _open(path: Path, crop: Sequence[float] | None = None) -> Image.Image:
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if crop:
        l, t, r, b = crop
        if not (0 <= l < r <= 1 and 0 <= t < b <= 1):
            raise ValueError("crop must be fractional l<r, t<b within 0..1")
        im = im.crop((round(l * im.width), round(t * im.height),
                      round(r * im.width), round(b * im.height)))
    return im


def _backdrop(im: Image.Image) -> Image.Image:
    bg = ImageOps.fit(im, (W, H), method=Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(42))
    return Image.blend(bg, Image.new("RGB", (W, H), (8, 10, 16)), 0.55)


def _tag(canvas: Image.Image, text: str, x: int, y: int) -> None:
    """Small dark label, top-left anchored at (x, y)."""
    if not text:
        return
    draw = ImageDraw.Draw(canvas)
    f = _font(26, bold=True)
    box = draw.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.rectangle((x, y, x + w + 24, y + h + 18), fill=(0, 0, 0))
    draw.text((x + 12, y + 7 - box[1]), text, font=f, fill=(240, 236, 226))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def archival_plate(src: Path, out: Path, *, label: str = "",
                   crop: Sequence[float] | None = None,
                   max_h: int = 1060, text: Sequence[str] = ()) -> Path:
    im = _open(src, crop)
    canvas = _backdrop(im)
    k = min(SAFE_W / im.width, max_h / im.height)   # fit; small sources upscale
    fg = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    text_h = 70 * len(text)
    x = (W - fg.width) // 2
    y = max(300, (H - fg.height - text_h) // 2 - 40)
    canvas.paste(fg, (x, y))
    _tag(canvas, label, x + 16, y + fg.height - 62)
    draw = ImageDraw.Draw(canvas)
    ty = y + fg.height + 34
    for i, line in enumerate(text):
        f = _font(48 if i == 0 else 34, bold=(i == 0), serif=(i == 0))
        tw = draw.textlength(line, font=f)
        draw.text(((W - tw) / 2, ty), line, font=f, fill=(245, 240, 228))
        ty += 70
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out


def triptych_plate(panels: Sequence[tuple[Path, str]], out: Path) -> Path:
    if len(panels) != 3:
        raise ValueError("triptych needs exactly three panels")
    first = _open(panels[0][0])
    canvas = _backdrop(first)
    ph, gap = 470, 26
    y = (H - (3 * ph + 2 * gap)) // 2 - 30
    x = (W - SAFE_W) // 2
    for path, label in panels:
        tile = ImageOps.fit(_open(path), (SAFE_W, ph), method=Image.LANCZOS)
        canvas.paste(tile, (x, y))
        _tag(canvas, label, x + 16, y + ph - 60)
        y += ph + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out


def typography_plate(lines: Sequence[tuple[str, int, bool]], out: Path,
                     *, kicker: str = "") -> Path:
    """Navy paper plate with factual text: (text, size, bold) per line."""
    canvas = Image.new("RGB", (W, H), _NAVY)
    grain = Image.effect_noise((W, H), 18).convert("RGB")
    canvas = Image.blend(canvas, grain, 0.06)
    draw = ImageDraw.Draw(canvas)
    blocks = []
    for text, size, bold in lines:
        f = _font(size, bold=bold, serif=bold)
        blocks.append((f, _wrap(draw, text, f, SAFE_W - 40), round(size * 1.25)))
    total = sum(len(ls) * lh for _, ls, lh in blocks) + 40 * (len(blocks) - 1)
    y = (H - total) // 2 + 120   # below headline overlays near the top
    if kicker:
        f = _font(30, bold=True)
        tw = draw.textlength(kicker, font=f)
        draw.text(((W - tw) / 2, y - 90), kicker, font=f, fill=(201, 162, 39))
        draw.line(((W - 120) / 2, y - 40, (W + 120) / 2, y - 40), fill=(201, 162, 39), width=3)
    for f, ls, lh in blocks:
        for line in ls:
            tw = draw.textlength(line, font=f)
            draw.text(((W - tw) / 2, y), line, font=f, fill=(245, 240, 228))
            y += lh
        y += 40
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out
