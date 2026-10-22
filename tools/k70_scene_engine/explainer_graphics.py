"""K70 P3.2: original explanatory graphics (1080x1920 stills, Pillow only).

These are K70-designed illustrations, never archival evidence: each one
carries only facts stated in the narration/source overlays or computed live
(the proof-of-work demo really hashes). The map outline comes from Natural
Earth (public domain). No network, no third-party photography.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .editorial_plates import H, SAFE_W, W, _font

_INK = (245, 240, 228)
_GOLD = (201, 162, 39)
_DIM = (150, 160, 178)


def _base(top=(12, 18, 30), bottom=(24, 36, 58)) -> Image.Image:
    grad = Image.linear_gradient("L").resize((W, H))
    canvas = Image.composite(Image.new("RGB", (W, H), bottom),
                             Image.new("RGB", (W, H), top), grad)
    grain = Image.effect_noise((W, H), 18).convert("RGB")
    return Image.blend(canvas, grain, 0.05)


def _center(draw, text, y, font, fill=_INK) -> int:
    draw.text(((W - draw.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)
    return y + round(font.size * 1.3)


def _caption(draw, kicker: str, title: str, sub: str, y: int) -> None:
    if kicker:
        y = _center(draw, kicker, y, _font(30, bold=True), _GOLD)
        draw.line(((W - 120) / 2, y + 4, (W + 120) / 2, y + 4), fill=_GOLD, width=3)
        y += 30
    if title:
        y = _center(draw, title, y, _font(64, bold=True, serif=True))
    if sub:
        _center(draw, sub, y + 6, _font(34), _DIM)


def _tag(draw, text: str) -> None:
    """Honest provenance line at the bottom of the safe area."""
    f = _font(22)
    draw.text(((W - draw.textlength(text, font=f)) / 2, H - 330), text, font=f, fill=_DIM)


def map_plate(geojson: Path, country: str, out: Path, *, marker: tuple[float, float],
              marker_label: str, kicker: str = "", title: str = "", sub: str = "",
              tag: str = "Graphic: K70 · outline: Natural Earth (public domain)") -> Path:
    data = json.loads(Path(geojson).read_text(encoding="utf-8"))
    feat = next(f for f in data["features"] if f["properties"].get("ADMIN") == country)
    geom = feat["geometry"]
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    pts = [p for poly in polys for p in poly[0]]
    lo0, lo1 = min(p[0] for p in pts), max(p[0] for p in pts)
    la0, la1 = min(p[1] for p in pts), max(p[1] for p in pts)
    box_h, box_w = 900, SAFE_W - 200
    k = min(box_w / (lo1 - lo0), box_h / (la1 - la0))
    ox = (W - (lo1 - lo0) * k) / 2
    oy = 330

    def xy(lon, lat):
        return ox + (lon - lo0) * k, oy + (la1 - lat) * k
    canvas = _base()
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for poly in polys:
        gd.line([xy(*p) for p in poly[0]], fill=_GOLD, width=10)
    canvas = ImageChops.screen(canvas, glow.filter(ImageFilter.GaussianBlur(16)))
    draw = ImageDraw.Draw(canvas)
    for poly in polys:
        draw.polygon([xy(*p) for p in poly[0]], fill=(30, 44, 70), outline=_GOLD)
        draw.line([xy(*p) for p in poly[0]] + [xy(*poly[0][0])], fill=_GOLD, width=3)
    mx, my = xy(*marker)
    for r, a in ((34, 60), (20, 140), (9, 255)):
        draw.ellipse((mx - r, my - r, mx + r, my + r), outline=(255, 214, 120), width=3 if a < 255 else 0,
                     fill=(255, 214, 120) if a == 255 else None)
    draw.text((mx + 44, my - 18), marker_label, font=_font(32, bold=True), fill=_INK)
    _caption(draw, kicker, title, sub, oy + box_h + 70)
    _tag(draw, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out


def proof_of_work(prefix: str, zero_hex: int = 4, limit: int = 2_000_000) -> tuple[int, str]:
    """Smallest counter whose SHA-1(prefix+counter) starts with zero_hex '0's."""
    for n in range(limit):
        h = hashlib.sha1(f"{prefix}{n}".encode()).hexdigest()
        if h.startswith("0" * zero_hex):
            return n, h
    raise ValueError("no proof of work found within limit")


def terminal_plate(prefix: str, out: Path, *, kicker: str = "", title: str = "",
                   sub: str = "", zero_hex: int = 4,
                   tag: str = "Illustration computed live by K70 · SHA-1, the hash Hashcash uses") -> Path:
    n, winner = proof_of_work(prefix, zero_hex)
    canvas = _base((6, 8, 10), (14, 18, 22))
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = 90, 720, W - 90, 1400     # below the scene's y=0.3 headline
    draw.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=(10, 12, 14), outline=(60, 66, 72), width=2)
    for i, c in enumerate(((237, 106, 94), (245, 191, 79), (98, 197, 84))):
        draw.ellipse((x0 + 26 + i * 34, y0 + 22, x0 + 44 + i * 34, y0 + 40), fill=c)
    mono = _mono(30)
    amber, green = (255, 196, 92), (120, 230, 140)
    rows = [f"{prefix}{i}" for i in range(4)] + ["…"] + [f"{prefix}{n}"]
    y = y0 + 80
    for row in rows:
        if row == "…":
            draw.text((x0 + 40, y), f"… {n - 4:,} more tries …", font=mono, fill=_DIM)
            y += 64
            continue
        h = hashlib.sha1(row.encode()).hexdigest()
        ok = h.startswith("0" * zero_hex)
        draw.text((x0 + 40, y), row, font=mono, fill=amber)
        draw.text((x0 + 40, y + 34), f"→ {h[:24]}…" + ("  ✓" if ok else ""),
                  font=mono, fill=green if ok else _DIM)
        y += 96
    _caption(draw, kicker, title, sub, y1 + 40)
    _tag(draw, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out


def _mono(size: int):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def shutter_plate(out: Path, *, kicker: str = "", title: str = "", sub: str = "",
                  notice: Sequence[str] = (), tag: str = "Illustration: K70 (not archival)") -> Path:
    """A closed corrugated bank shutter under a single light, with a posted notice."""
    canvas = _base((8, 10, 14), (18, 22, 30))
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = 120, 330, W - 120, 1180
    for i, y in enumerate(range(y0, y1, 26)):
        shade = 92 + (18 if i % 2 else 0)
        draw.rectangle((x0, y, x1, y + 24), fill=(shade, shade + 4, shade + 10))
        draw.line((x0, y + 24, x1, y + 24), fill=(40, 44, 50), width=2)
    draw.rectangle((x0 - 18, y0 - 30, x1 + 18, y0), fill=(52, 56, 64))
    light = Image.new("L", (W, H), 0)
    ImageDraw.Draw(light).ellipse((W / 2 - 520, 120, W / 2 + 520, 1100), fill=255)
    canvas = Image.composite(canvas, Image.blend(canvas, Image.new("RGB", (W, H), 0), 0.6),
                             light.filter(ImageFilter.GaussianBlur(160)))
    draw = ImageDraw.Draw(canvas)
    if notice:
        nx0, ny0, nx1 = W / 2 - 230, 600, W / 2 + 230
        ny1 = ny0 + 70 + 56 * len(notice)
        draw.rectangle((nx0, ny0, nx1, ny1), fill=(236, 230, 214))
        y = ny0 + 36
        for i, line in enumerate(notice):
            f = _font(40 if i == 0 else 30, bold=(i == 0))
            draw.text(((W - draw.textlength(line, font=f)) / 2, y), line, font=f, fill=(30, 30, 30))
            y += 56
    _caption(draw, kicker, title, sub, y1 + 70)
    _tag(draw, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out


def ledger_plate(out: Path, *, kicker: str = "", title: str = "", sub: str = "",
                 rows: Sequence[tuple[str, str]] = (), stamp: str = "", top: int = 380,
                 tag: str = "Illustration: K70 (not archival)") -> Path:
    """An account ledger card with a diagonal stamp; rows are label/value text.

    `top` moves the card below a scene's own headline overlay (y≈0.3)."""
    canvas = _base()
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1 = 150, top, W - 150
    y1 = y0 + 120 + 96 * len(rows) + (260 if stamp else 0)
    draw.rounded_rectangle((x0 + 12, y0 + 16, x1 + 12, y1 + 16), radius=18, fill=(6, 8, 12))
    draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=(236, 230, 214))
    y = y0 + 60
    for label, value in rows:
        lf = _font(30)
        draw.text((x0 + 50, y), label, font=lf, fill=(90, 84, 74))
        room = (x1 - x0 - 100) - draw.textlength(label, font=lf) - 30
        size = 34
        while size > 18 and draw.textlength(value, font=_font(size, bold=True)) > room:
            size -= 2                                  # fit long values beside the label
        f = _font(size, bold=True)
        draw.text((x1 - 50 - draw.textlength(value, font=f), y), value, font=f, fill=(30, 30, 30))
        draw.line((x0 + 50, y + 58, x1 - 50, y + 58), fill=(196, 188, 170), width=2)
        y += 96
    if stamp:
        f = _font(96, bold=True)
        tw = int(draw.textlength(stamp, font=f)) + 60
        st = Image.new("RGBA", (tw, 150), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        sd.rectangle((4, 4, tw - 4, 146), outline=(190, 40, 40, 230), width=8)
        sd.text((30, 14), stamp, font=f, fill=(190, 40, 40, 230))
        st = st.rotate(14, expand=True, resample=Image.BICUBIC)
        canvas.paste(st, ((W - st.width) // 2, y1 - st.height - 60), st)
    draw = ImageDraw.Draw(canvas)
    _caption(draw, kicker, title, sub, y1 + 80)
    _tag(draw, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out


def _save(canvas: Image.Image, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return out


def _spot(canvas: Image.Image, cx: float, cy: float, r: float, dim: float = 0.6) -> Image.Image:
    light = Image.new("L", (W, H), 0)
    ImageDraw.Draw(light).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return Image.composite(canvas, Image.blend(canvas, Image.new("RGB", (W, H), 0), dim),
                           light.filter(ImageFilter.GaussianBlur(r / 3)))


def broken_link_plate(out: Path, *, left: str, right: str, kicker: str = "", title: str = "",
                      sub: str = "", tag: str = "Illustration: K70 (not archival)") -> Path:
    """Two chain links pulled apart; each half carries a factual label."""
    canvas = _base()
    draw = ImageDraw.Draw(canvas)
    cy = 820
    for cx, label, tilt in ((W / 2 - 215, left, -12), (W / 2 + 215, right, 12)):
        link = Image.new("RGBA", (330, 210), (0, 0, 0, 0))
        ld = ImageDraw.Draw(link)
        ld.rounded_rectangle((16, 16, 314, 194), radius=88, outline=(200, 170, 90, 255), width=28)
        ld.rounded_rectangle((16, 16, 314, 194), radius=88, outline=(250, 220, 140, 255), width=7)
        link = link.rotate(tilt, expand=True, resample=Image.BICUBIC)
        canvas.paste(link, (int(cx - link.width / 2), int(cy - link.height / 2)), link)
        f = _font(40, bold=True)
        draw = ImageDraw.Draw(canvas)
        draw.text((cx - draw.textlength(label, font=f) / 2, cy + 140), label, font=f, fill=_INK)
    for i in range(14):                                   # sparks at the break
        a = i * 0.45
        draw.line((W / 2, cy, W / 2 + 70 * math.cos(a), cy + 70 * math.sin(a)),
                  fill=(255, 214, 120), width=3)
    canvas = _spot(canvas, W / 2, cy, 520)
    draw = ImageDraw.Draw(canvas)
    _caption(draw, kicker, title, sub, 1150)
    _tag(draw, tag)
    return _save(canvas, out)


def wall_plate(out: Path, *, kicker: str = "", title: str = "", sub: str = "",
               tag: str = "Illustration: K70 (not archival)") -> Path:
    """A tall brick wall under a spotlight, one small figure at its base."""
    canvas = _base((10, 12, 16), (26, 22, 22))
    draw = ImageDraw.Draw(canvas)
    top, bottom = 260, 1240
    for row, y in enumerate(range(top, bottom, 46)):
        off = 0 if row % 2 else 60
        for x in range(-120 + off, W, 120):
            shade = 70 + ((x * 7 + y * 3) % 23)
            draw.rectangle((x + 3, y + 3, x + 117, y + 43), fill=(shade + 20, shade - 6, shade - 14))
    draw.rectangle((0, bottom, W, H), fill=(14, 14, 18))
    fx = W / 2                                            # small human silhouette
    draw.ellipse((fx - 14, bottom - 128, fx + 14, bottom - 100), fill=(8, 8, 10))
    draw.rounded_rectangle((fx - 22, bottom - 98, fx + 22, bottom - 30), radius=10, fill=(8, 8, 10))
    draw.rectangle((fx - 18, bottom - 34, fx - 4, bottom), fill=(8, 8, 10))
    draw.rectangle((fx + 4, bottom - 34, fx + 18, bottom), fill=(8, 8, 10))
    canvas = _spot(canvas, W / 2, bottom - 200, 560, 0.7)
    draw = ImageDraw.Draw(canvas)
    _caption(draw, kicker, title, sub, bottom + 70)
    _tag(draw, tag)
    return _save(canvas, out)


def empty_room_plate(out: Path, *, kicker: str = "", title: str = "", sub: str = "",
                     tag: str = "Illustration: K70 (not archival)") -> Path:
    """One-point-perspective empty room: bare walls, a window of light, two boxes."""
    canvas = _base((16, 16, 20), (30, 28, 30))
    draw = ImageDraw.Draw(canvas)
    bx0, by0, bx1, by1 = 300, 480, 780, 1000            # back wall
    draw.polygon([(0, 200), (bx0, by0), (bx0, by1), (0, 1320)], fill=(58, 54, 52))
    draw.polygon([(W, 200), (bx1, by0), (bx1, by1), (W, 1320)], fill=(50, 47, 46))
    draw.rectangle((bx0, by0, bx1, by1), fill=(70, 66, 62))
    draw.polygon([(0, 1320), (bx0, by1), (bx1, by1), (W, 1320)], fill=(40, 34, 30))
    draw.rectangle((470, 580, 610, 800), fill=(236, 226, 196))  # window
    draw.line((540, 580, 540, 800), fill=(70, 66, 62), width=6)
    draw.polygon([(470, 800), (610, 800), (760, 1260), (330, 1260)], fill=(96, 84, 66))
    for x0, y0, s in ((620, 1060, 150), (760, 1110, 120)):   # moving boxes
        draw.rectangle((x0, y0, x0 + s, y0 + s * 0.8), fill=(150, 116, 74))
        draw.line((x0, y0 + 12, x0 + s, y0 + 12), fill=(120, 92, 58), width=4)
    canvas = _spot(canvas, 540, 760, 620, 0.55)
    draw = ImageDraw.Draw(canvas)
    _caption(draw, kicker, title, sub, 1350)
    _tag(draw, tag)
    return _save(canvas, out)


def house_sign_plate(out: Path, *, sign: Sequence[str], kicker: str = "", title: str = "",
                     sub: str = "", tag: str = "Illustration: K70 (not archival)") -> Path:
    """Dusk silhouette of a suburban house with a yard sign."""
    canvas = _base((20, 26, 44), (60, 44, 52))
    draw = ImageDraw.Draw(canvas)
    gy = 1120
    draw.rectangle((0, gy, W, H), fill=(14, 16, 18))
    draw.polygon([(240, 760), (540, 520), (840, 760)], fill=(10, 12, 16))
    draw.rectangle((280, 760, 800, gy), fill=(10, 12, 16))
    for x in (340, 640):
        draw.rectangle((x, 840, x + 100, 960), fill=(30, 34, 40))  # dark windows
    draw.rectangle((500, 900, 580, gy), fill=(24, 26, 30))
    px = 830
    draw.rectangle((px - 6, 900, px + 6, gy + 30), fill=(40, 34, 28))
    sx0, sy0 = px - 150, 880
    sy1 = sy0 + 56 * len(sign) + 30
    draw.rectangle((sx0, sy0, px + 150, sy1), fill=(236, 230, 214))
    y = sy0 + 18
    for i, line in enumerate(sign):
        f = _font(40 if i == 0 else 28, bold=(i == 0))
        draw.text((px - draw.textlength(line, font=f) / 2, y), line, font=f,
                  fill=(170, 30, 30) if i == 0 else (30, 30, 30))
        y += 56
    _caption(draw, kicker, title, sub, gy + 90)
    _tag(draw, tag)
    return _save(canvas, out)


def mail_plate(out: Path, *, header: Sequence[tuple[str, str]], body: Sequence[str],
               kicker: str = "", title: str = "", sub: str = "",
               tag: str = "Illustration: K70 (not archival)") -> Path:
    """A plain-text e-mail on a dark terminal, e.g. a mailing-list subscribe."""
    canvas = _base((6, 8, 10), (14, 18, 22))
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = 90, 560, W - 90, 1160
    draw.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=(10, 12, 14), outline=(60, 66, 72), width=2)
    mono = _mono(34)
    y = y0 + 50
    for k, v in header:
        draw.text((x0 + 40, y), f"{k}:", font=mono, fill=_DIM)
        draw.text((x0 + 40 + draw.textlength(f"{k}: ", font=mono), y), v, font=mono, fill=(255, 196, 92))
        y += 56
    draw.line((x0 + 40, y + 10, x1 - 40, y + 10), fill=(60, 66, 72), width=2)
    y += 50
    for line in body:
        draw.text((x0 + 40, y), line, font=mono, fill=(120, 230, 140))
        y += 56
    _caption(draw, kicker, title, sub, y1 + 60)
    _tag(draw, tag)
    return _save(canvas, out)
