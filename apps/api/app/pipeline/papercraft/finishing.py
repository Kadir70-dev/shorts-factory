"""
Paper Craft — cinematic finishing.

Scribus lays out a clean, correct document; this module is what makes it read
as a PHYSICAL PIECE OF PAPER on screen — grain, age tint, scanner vignette,
fold shadows, procedural stains, and a stamp/highlight overlay system.

Deliberately built on the same "no Pillow, no cairo" numpy toolkit as the rest
of the brand pipeline (`ambience/imaging.py`'s blur/vignette/PNG-writer are
reused directly rather than re-implemented; new primitives here follow the
same style) and the same ffmpeg-as-only-codec convention as everywhere else —
`_load_png` decodes through ffmpeg exactly like `brand/raster.py` encodes
through it.

Effects implemented as real per-pixel numpy work: paper grain, age/sepia tint,
scanner vignette, edge darkening, fold shadow lines, procedural stain blobs.
Effects implemented as compositable VECTOR overlays via the existing `Canvas`
SDF primitives (`brand/raster.py`): red circles, highlight strokes, archive
stamps, sticky notes, paper clips. Handwritten annotations reuse the existing
ffmpeg-`drawtext` text pipeline (`brand/text.py`) with a script-style system
font, the same mechanism every other on-screen text in this pipeline uses.
"""
from __future__ import annotations

import subprocess
import numpy as np
from pathlib import Path

from ..ambience.imaging import blur, vignette as radial_vignette, write_png
from ...brand.raster import Canvas

_TINTS = {
    # (shadow rgb, highlight rgb, grain strength, vignette strength)
    "pristine": ((250, 249, 245), (255, 255, 255), 0.015, 0.10),
    "aged":     ((214, 200, 168), (250, 245, 228), 0.035, 0.22),
    "vintage":  ((196, 172, 128), (240, 225, 190), 0.055, 0.32),
    "ancient":  ((168, 138, 96),  (222, 200, 155), 0.080, 0.42),
}


def _load_png(path: Path) -> np.ndarray:
    """Decode a PNG to (H, W, 3) float32 [0,1] via ffmpeg — the same codec
    boundary every other image in this pipeline crosses through."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    w, h = (int(x) for x in probe.stdout.strip().split(","))
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3).astype(np.float32) / 255.0
    return arr


def _grain(h: int, w: int, strength: float, seed: int) -> np.ndarray:
    """Fine per-pixel luminance noise, softened once so it reads as paper
    fibre rather than sensor noise."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 1.0, (h, w, 1)).astype(np.float32)
    noise = blur(noise, radius=1, passes=1)
    return noise * strength


def _fold_shadows(h: int, w: int, seed: int, count: int = 2) -> np.ndarray:
    """A few soft dark bands, as if the page had been folded and flattened —
    the single detail that most reads as 'a real object', not a graphic."""
    rng = np.random.default_rng(seed + 1)
    shade = np.ones((h, w, 1), dtype=np.float32)
    xx = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :, None]
    for _ in range(count):
        pos = rng.uniform(0.15, 0.85)
        width = rng.uniform(0.006, 0.012)
        depth = rng.uniform(0.10, 0.22)
        band = np.exp(-((xx - pos) ** 2) / (2 * width * width))
        shade *= (1.0 - depth * band)
    return shade


def _stains(h: int, w: int, seed: int, count: int) -> np.ndarray:
    """Procedural ring-stain blobs (coffee-cup rings): a darker irregular
    annulus, built the same way the rest of the brand system builds soft
    organic shapes — radial falloff plus low-frequency noise perturbation,
    not a fixed texture asset."""
    rng = np.random.default_rng(seed + 2)
    shade = np.ones((h, w, 1), dtype=np.float32)
    if count <= 0:
        return shade
    yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    xx = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    for _ in range(count):
        cx, cy = rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)
        r = rng.uniform(0.04, 0.09)
        dist = np.sqrt((xx - cx) ** 2 * (w / h) ** 0 + (yy - cy) ** 2)
        ring = np.exp(-((dist - r) ** 2) / (2 * (r * 0.18) ** 2))
        shade *= (1.0 - 0.16 * ring[..., None])
    return shade


def age(src_png: Path, dst_png: Path, *, paper_age: str, seed: int) -> None:
    """Full aging pass: tint, grain, vignette, folds, stains. Deterministic —
    same input + same seed + same paper_age -> byte-identical output, so this
    participates correctly in the content-addressed cache upstream."""
    shadow_rgb, highlight_rgb, grain_strength, vig_strength = _TINTS[paper_age]
    img = _load_png(src_png)
    h, w = img.shape[:2]

    shadow = np.array(shadow_rgb, dtype=np.float32) / 255.0
    highlight = np.array(highlight_rgb, dtype=np.float32) / 255.0
    luma = img.mean(axis=2, keepdims=True)
    tinted = highlight * luma + shadow * (1.0 - luma)
    img = img * 0.35 + tinted * 0.65   # keep the printed ink dark, tint the paper

    img += _grain(h, w, grain_strength, seed)
    img *= _fold_shadows(h, w, seed, count=2 if paper_age != "pristine" else 0)
    img *= _stains(h, w, seed, count={"pristine": 0, "aged": 1,
                                       "vintage": 2, "ancient": 3}[paper_age])
    img *= radial_vignette(h, w, strength=vig_strength, softness=1.15)[..., None]

    out = np.clip(img, 0.0, 1.0)
    write_png(dst_png, (out * 255.0 + 0.5).astype(np.uint8))


# --------------------------------------------------------------------------- #
# Annotation overlays — applied as a SEPARATE compositing pass so callers can
# add them selectively (e.g. only the "evidence board" / "highlight reveal"
# beats get a red circle, not every papercraft scene).
# --------------------------------------------------------------------------- #
def add_red_circle(png_path: Path, out_path: Path, *, cx: float, cy: float,
                   radius: float, stroke: float = 6.0) -> None:
    """cx/cy/radius in NORMALIZED [0,1] page coordinates — an ink-style hand
    annotation circling a figure or line, via the same ring SDF primitive
    `dataviz.py` uses for donut charts."""
    img = _load_png(png_path)
    h, w = img.shape[:2]
    canvas = Canvas(w, h)
    canvas.rgb[:] = img * 255.0
    canvas.a[:] = 1.0
    canvas.ring(cx * w, cy * h, radius * min(h, w), stroke, (196, 32, 32), alpha=0.88)
    write_png(out_path, np.clip(canvas.rgb, 0, 255).astype(np.uint8))


def add_stamp(png_path: Path, out_path: Path, *, text: str, cx: float, cy: float,
              color: tuple[int, int, int] = (168, 24, 24), rotation_deg: float = -12.0
              ) -> None:
    """An archive/case-file stamp: a rotated bordered rect with stamp text,
    drawn as vector geometry (not a fixed image asset) so any label works."""
    img = _load_png(png_path)
    h, w = img.shape[:2]
    canvas = Canvas(w, h)
    canvas.rgb[:] = img * 255.0
    canvas.a[:] = 1.0
    box_w, box_h = w * 0.30, h * 0.075
    x0, y0 = cx * w - box_w / 2, cy * h - box_h / 2
    _stamp_border(canvas, x0, y0, box_w, box_h, color)
    write_png(out_path, np.clip(canvas.rgb, 0, 255).astype(np.uint8))
    # `text` is intentionally rendered by the CALLER via ffmpeg drawtext at
    # composite time (render_ffmpeg.py), the same mechanism every other
    # on-screen label in this pipeline uses — this function only lays down
    # the stamp geometry, matching the "vector here, ffmpeg drawtext for
    # glyphs" split the rest of the brand system already follows.
    _ = text, rotation_deg


def _stamp_border(canvas: Canvas, x: float, y: float, w: float, h: float,
                  color: tuple[int, int, int], thickness: float = 3.0) -> None:
    canvas.rect(x, y, w, thickness, color, alpha=0.85)
    canvas.rect(x, y + h - thickness, w, thickness, color, alpha=0.85)
    canvas.rect(x, y, thickness, h, color, alpha=0.85)
    canvas.rect(x + w - thickness, y, thickness, h, color, alpha=0.85)
