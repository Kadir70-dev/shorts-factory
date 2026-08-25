"""
Brand package — the permanent visual identity of the channel.

Four modules, deliberately separated so the identity is data, not code:

  theme.py    — loads config/brand/<id>.yaml into a typed BrandTheme: palette,
                font system (with real on-disk font resolution), sizes, safe
                areas, grade variants, chart styling.
  raster.py   — dependency-free image generation (numpy → ffmpeg). Lets us build
                brand PNGs and chart frames without Pillow/cairo/manim.
  assets.py   — generates + caches the brand asset set (watermark, lower third
                plate, end card, disclaimer strip) keyed by a theme hash.
  overlays.py — turns the theme into ffmpeg filter fragments and ASS caption
                styles the renderer splices into its filtergraph.

Nothing here talks to the network and nothing here raises on a missing font or
asset: a degraded brand is always better than a failed render.
"""
from .theme import BrandTheme, load_theme
from .manager import BrandManager, brand_manager, theme_for

__all__ = ["BrandTheme", "load_theme", "BrandManager", "brand_manager", "theme_for"]
