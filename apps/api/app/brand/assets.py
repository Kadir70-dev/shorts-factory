"""
Brand asset generation + cache.

Everything the channel stamps onto a frame — the watermark bug, the lower-third
plate, the end card, the disclaimer strip, the intro rule — is GENERATED from the
theme rather than checked in as binary. Two reasons:

  1. Editing config/brand/k70.yaml re-skins every future upload with no asset
     wrangling. The cache key is the theme fingerprint, so a changed palette
     rebuilds automatically and a stale asset can't survive a rebrand.
  2. A fresh clone has a complete brand with zero setup. There is no "download the
     logo pack" step that a batch run can trip over at 3am.

Users who have a real designed logo drop it at `watermark.custom_path` and it
wins — the generator is the floor, not a ceiling.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from ..config import ROOT, settings
from . import text as tx
from .raster import Canvas, write_png
from .theme import BrandTheme

_LOCK = asyncio.Lock()


def asset_dir(theme: BrandTheme) -> Path:
    """Per-fingerprint directory — a theme edit lands in a fresh folder."""
    return settings().data_dir / "assets" / "brand" / theme.id / theme.fingerprint


# --------------------------------------------------------------------------- #
# Generators — each returns the path it wrote
# --------------------------------------------------------------------------- #
def _watermark(theme: BrandTheme, out: Path) -> Path:
    """The channel bug: a wordmark under a signature accent rule.

    Drawn as a plate + rule here; the LETTERING is burned by ffmpeg drawtext in
    `overlays.py` (we have no glyph rasteriser), which also lets the text stay
    crisp at whatever scale the frame needs.
    """
    w = int(theme.watermark.get("width_px", 190))
    h = round(w * 0.42)
    c = Canvas(w, h)
    accent = theme.rgb("primary")
    # a short accent rule above the wordmark — the recognisable mark
    c.rect(0, 0, w * 0.34, max(3, h * 0.055), accent, alpha=1.0, radius=2)
    # a soft dark plate so the bug reads over bright footage
    c.rect(0, h * 0.13, w, h * 0.87, theme.rgb("bg"), alpha=0.34, radius=6)
    return write_png(c, out)


def _lower_third(theme: BrandTheme, out: Path, width: int = 1080) -> Path:
    """Lower-third plate: a full-bleed soft bar with a solid accent edge."""
    lt = theme.lower_third
    h = int(lt.get("height_px", 150))
    bar = int(lt.get("accent_bar_px", 10))
    side = int(theme.safe.get("side", 0.055) * width)
    c = Canvas(width, h)
    c.rect(side, 0, width - 2 * side, h, theme.rgb("bg_soft"),
           alpha=float(lt.get("bg_opacity", 0.86)), radius=6)
    c.rect(side, 0, bar, h, theme.rgb("primary"), alpha=1.0, radius=3)
    # a hairline under the plate ties it to the chart/grid language
    c.rect(side, h - 2, width - 2 * side, 2, theme.rgb("grid"), alpha=0.8)
    return write_png(c, out)


def _endcard(theme: BrandTheme, out: Path, width: int = 1080,
             height: int = 1920) -> Path:
    """Outro plate — a graded scrim the CTA, wordmark and disclaimer sit on."""
    c = Canvas(width, height)
    bg = theme.rgb("bg")
    c.rect(0, 0, width, height, bg, alpha=0.90)
    # signature rule across the upper third
    side = int(theme.safe.get("side", 0.055) * width)
    y = int(height * 0.34)
    c.rect(side, y, width - 2 * side, 5, theme.rgb("primary"), alpha=1.0, radius=2)
    # a subtle gradient floor so the disclaimer band has weight
    c.vgradient(0, int(height * 0.72), width, int(height * 0.28),
                bg, (0, 0, 0), 0.0, 0.55)
    return write_png(c, out)


def _disclaimer_strip(theme: BrandTheme, out: Path, width: int = 1080) -> Path:
    """The persistent finance-safety band. Deliberately quiet: legible, never
    competing with the caption line."""
    h = 74
    c = Canvas(width, h)
    c.rect(0, 0, width, h, theme.rgb("bg"), alpha=0.72)
    c.rect(0, 0, width, 2, theme.rgb("primary"), alpha=0.55)
    return write_png(c, out)


def _intro_rule(theme: BrandTheme, out: Path, width: int = 1080) -> Path:
    """The intro wipe element — one accent rule, wiped across by the renderer."""
    c = Canvas(width, 8)
    c.rect(0, 0, width, 8, theme.rgb("primary"), alpha=1.0, radius=4)
    return write_png(c, out)


def _caption_plate(theme: BrandTheme, out: Path, width: int = 1080) -> Path:
    """Optional soft scrim behind captions for bright/busy footage."""
    h = 260
    c = Canvas(width, h)
    c.vgradient(0, 0, width, h, (0, 0, 0), (0, 0, 0), 0.0, 0.55)
    return write_png(c, out)


_GENERATORS = {
    "watermark.png": _watermark,
    "lower_third.png": _lower_third,
    "endcard.png": _endcard,
    "disclaimer_strip.png": _disclaimer_strip,
    "intro_rule.png": _intro_rule,
    "caption_plate.png": _caption_plate,
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
async def ensure_assets(theme: BrandTheme) -> dict[str, Path]:
    """Build any missing brand assets for this theme fingerprint (idempotent).

    Serialised behind a lock so two concurrent renders don't race on the first
    build. Individual failures are swallowed — a missing plate degrades one
    overlay, and `overlays.py` checks existence before referencing anything.
    """
    d = asset_dir(theme)
    async with _LOCK:
        d.mkdir(parents=True, exist_ok=True)
        for name, gen in _GENERATORS.items():
            p = d / name
            if p.exists():
                continue
            try:
                await asyncio.to_thread(gen, theme, p)
            except Exception as e:              # noqa: BLE001 — never block a render
                print(f"[brand] could not generate {name}: "
                      f"{type(e).__name__}: {str(e)[:100]}", flush=True)

    paths = {name: d / name for name in _GENERATORS}

    # A real designed logo always beats the generated bug.
    custom = (theme.watermark.get("custom_path") or "").strip()
    if custom:
        cp = Path(custom)
        if not cp.is_absolute():
            cp = ROOT / cp
        if cp.exists():
            paths["watermark.png"] = cp

    return {k: v for k, v in paths.items() if v.exists()}


def clear_cache(theme: BrandTheme) -> None:
    """Drop this fingerprint's assets so the next render regenerates them."""
    shutil.rmtree(asset_dir(theme), ignore_errors=True)


def wordmark_filters(theme: BrandTheme, width: int, height: int,
                     hide_after: float | None = None) -> list[str]:
    """drawtext filters that letter the watermark bug over its plate.

    Separated from the plate raster so the type stays vector-crisp and so the bug
    can fade out for the end card without regenerating anything.
    """
    wm = theme.watermark
    if not wm.get("text"):
        return []
    margin = round(int(wm.get("margin_px", 46)) * width / 1080)
    plate_w = round(int(wm.get("width_px", 190)) * width / 1080)
    plate_h = round(plate_w * 0.42)
    pos = str(wm.get("position", "top_right"))
    opacity = float(wm.get("opacity", 0.62))

    x_expr = f"w-{margin + plate_w}" if pos.endswith("right") else f"{margin}"
    y_base = (margin if pos.startswith("top")
              else height - margin - plate_h)

    alpha: float | str = opacity
    if hide_after is not None and wm.get("hide_on_outro", True):
        alpha = (f"if(lt(t,{hide_after:.3f}),{opacity:.3f},"
                 f"max(0,{opacity:.3f}*(1-(t-{hide_after:.3f})/0.4)))")

    main = round(plate_h * 0.46)
    sub = round(plate_h * 0.20)
    out = [tx.drawtext(
        wm["text"], font=theme.display.path, size=main,
        color=theme.ff("ink"), x=f"{x_expr}+{round(plate_w*0.06)}",
        y=f"{y_base + round(plate_h * 0.22)}", alpha=alpha, border=0,
        shadow=2,
    )]
    if wm.get("sub"):
        out.append(tx.drawtext(
            wm["sub"], font=theme.body.path, size=sub,
            color=theme.ff("primary"), x=f"{x_expr}+{round(plate_w*0.07)}",
            y=f"{y_base + round(plate_h * 0.74)}", alpha=alpha, shadow=1,
        ))
    return out
