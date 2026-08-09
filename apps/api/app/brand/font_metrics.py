"""
Real per-glyph advance widths, via fontTools — for deciding whether a string
actually fits a pixel width, instead of guessing from a character count.

`brand/text.py`'s `_CHAR_BUDGET` table exists because "measuring real glyph
advances would need a font library we deliberately don't depend on" (its own
docstring). That was an acceptable approximation for drawtext overlays sized
well inside their frame — but ASS captions render with `WrapStyle: 2` (no
auto-wrap: see `overlays.py`), so a caption group that's actually too wide
doesn't wrap or clip, it just overflows the frame on both sides. That failure
mode needs the real answer, not a calibrated guess, so this module reads the
font file's own `hmtx` table directly.

No kerning/shaping (that would need HarfBuzz): advance widths are summed per
character. A small conservative multiplier covers that gap, same spirit as
`_CHAR_BUDGET`'s "better a slightly early wrap than an overflowing line".
"""
from __future__ import annotations

import functools

# fontTools is optional at import time so a font-metrics failure degrades to
# the character-budget heuristic rather than breaking caption generation.
try:
    from fontTools.ttLib import TTFont
    _HAVE_FONTTOOLS = True
except ImportError:                                    # pragma: no cover
    _HAVE_FONTTOOLS = False

# Real advance widths don't include hinting/anti-aliasing/subpixel rounding
# libass applies at render time — a small headroom keeps the safety check
# conservative rather than exact-to-the-pixel.
_SAFETY_MARGIN = 1.05


@functools.lru_cache(maxsize=16)
def _load_font(path: str) -> "TTFont | None":
    if not path or not _HAVE_FONTTOOLS:
        return None
    try:
        return TTFont(path, lazy=True, fontNumber=0)
    except Exception:                                   # noqa: BLE001
        return None


@functools.lru_cache(maxsize=16)
def _metrics(path: str) -> tuple[dict, dict, int] | None:
    """(cmap, glyph-name -> advance-width, unitsPerEm), or None if unreadable."""
    font = _load_font(path)
    if font is None:
        return None
    try:
        units_per_em = font["head"].unitsPerEm
        cmap = font.getBestCmap() or {}
        hmtx = font["hmtx"]
        widths = {name: hmtx[name][0] for name in cmap.values()}
        return cmap, widths, units_per_em
    except Exception:                                   # noqa: BLE001
        return None


def text_width_px(text: str, font_path: str, size_px: float) -> float | None:
    """Real rendered advance width of `text` at `size_px`, or None when the
    font can't be read (caller should fall back to the character budget)."""
    m = _metrics(font_path)
    if m is None:
        return None
    cmap, widths, units_per_em = m
    if not units_per_em:
        return None
    total_units = 0
    fallback = next(iter(widths.values()), units_per_em * 0.6)
    for ch in text:
        glyph = cmap.get(ord(ch))
        total_units += widths.get(glyph, fallback) if glyph else fallback
    return total_units * (size_px / units_per_em) * _SAFETY_MARGIN


@functools.lru_cache(maxsize=16)
def real_family_name(path: str) -> str | None:
    """The font file's OWN family name (`name` table ID 16, else ID 1) —
    NOT whatever search string happened to match it to a file.

    This matters beyond width math: libass (the ASS caption renderer)
    matches `Fontname:` in the style line against installed font family
    names. `theme.resolve_font()` was returning the PREFERENCE-LIST string
    that matched a file (e.g. "Barlow"), not the file's real family (e.g.
    "Barlow Condensed") — a real font shipped under a condensed-only
    filename has no family literally called "Barlow", so libass silently
    substituted a fallback font instead of raising an error. Reading the
    name table directly is what fixes the mismatch, not a width heuristic.
    """
    font = _load_font(path)
    if font is None:
        return None
    try:
        name_table = font["name"]
        for name_id in (16, 1):                    # 16 = preferred family
            rec = name_table.getDebugName(name_id)
            if rec:
                return rec
    except Exception:                               # noqa: BLE001
        pass
    return None

