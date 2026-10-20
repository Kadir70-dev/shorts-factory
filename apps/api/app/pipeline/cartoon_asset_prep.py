"""P1: CPU-only cutout-sheet / individual-sprite PNG preparation and rig draft.

IMPORTANT: Does not hallucinate invisible body geometry. Input MUST contain
separate body parts with visible gaps (a named sheet or a part-file directory).
Plain-background removal is a deterministic edge-connected color-key operation,
not learned instance/pose segmentation. All pivots are editable draft estimates.
"""
from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

REQUIRED = ("body", "head", "arm_left", "arm_right", "leg_left", "leg_right")
OPTIONAL = ("eyes_open", "eyes_closed", "mouth_open", "mouth_closed")
PARTS = REQUIRED + OPTIONAL
DEFAULT_CELLS = {
    "head": (0, 0), "body": (0, 1), "arm_left": (0, 2), "arm_right": (0, 3),
    "leg_left": (1, 0), "leg_right": (1, 1), "eyes_open": (1, 2),
    "eyes_closed": (1, 3), "mouth_open": (2, 0), "mouth_closed": (2, 1),
}
TARGET_WIDTH = {"body": 110, "head": 120, "arm_left": 38, "arm_right": 38,
                "leg_left": 39, "leg_right": 39, "eyes_open": 59,
                "eyes_closed": 59, "mouth_open": 27, "mouth_closed": 27}
BODY_ANCHORS = {"body": (0, -256), "head": (0, -294),
                "arm_left": (-48, -248), "arm_right": (46, -248),
                "leg_left": (-23, -125), "leg_right": (23, -125)}
JOINTS = {"body": (0.5, .11), "head": (0.5, .89),
          "arm_left": (.50, .08), "arm_right": (.50, .08),
          "leg_left": (.50, .07), "leg_right": (.50, .07)}
FACE_TOP_LEFT = {"eyes_open": (.275, .453), "eyes_closed": (.275, .453),
                 "mouth_open": (.392, .703), "mouth_closed": (.392, .703)}
MAX_PIXELS = 9_000_000


class AssetPrepError(ValueError):
    """Actionable failure for sheets that cannot be cut out safely."""


@dataclass(frozen=True)
class Cutout:
    image: Image.Image
    method: str
    foreground_fraction: float
    source_bbox: tuple[int, int, int, int]


def _load_image(path: Path) -> Image.Image:
    if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
        raise AssetPrepError(f'Unsupported image type: {path}')
    if not path.is_file():
        raise AssetPrepError(f'Image does not exist: {path}')
    with Image.open(path) as im:
        if im.width * im.height > MAX_PIXELS:
            raise AssetPrepError(f'Image too large for CPU mode: {im.width}x{im.height}')
        return im.convert('RGBA')


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise AssetPrepError('Input path escapes the assets directory')
    return candidate


def _drop_background(im: Image.Image, tolerance: int) -> tuple[Image.Image, str]:
    """Preserve native alpha, else flood only border-connected solid backdrop.

    This retains white eyes enclosed in dark eyelids and interior white areas:
    only near-background colors connected to the cell's outer edge are erased.
    """
    rgba = np.asarray(im, dtype=np.uint8).copy()
    a = rgba[:, :, 3]
    if (a < 250).any():
        return im, 'source_alpha'
    h, w = a.shape
    if w < 4 or h < 4:
        raise AssetPrepError('Sprite cell is too small')
    corners = np.stack((rgba[0, 0, :3], rgba[0, -1, :3],
                        rgba[-1, 0, :3], rgba[-1, -1, :3])).astype(np.int16)
    bg = np.median(corners, axis=0)
    if np.max(np.abs(corners - bg)) > 28:
        raise AssetPrepError('Corners differ: provide a clean solid background or transparent PNG')
    rgb = rgba[:, :, :3].astype(np.int16)
    d = np.max(np.abs(rgb - bg[None, None, :]), axis=2)
    candidates = Image.fromarray(np.where(d <= tolerance, 255, 0).astype('uint8'), 'L').copy()
    # Region marker = 128. Restrict erasure to border-connected candidate pixels.
    pix = candidates.load()
    starts = ([(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] +
              [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)])
    for point in starts:
        if pix[point] == 255:
            ImageDraw.floodfill(candidates, point, 128, thresh=0)
    erasure = np.asarray(candidates) == 128
    rgba[:, :, 3] = np.where(erasure, 0, 255).astype('uint8')
    rgba[erasure, :3] = 0
    return Image.fromarray(rgba, 'RGBA'), 'border_color_key'


def cutout_image(im: Image.Image, *, tolerance: int = 26,
                 padding: int = 3) -> Cutout:
    if not 0 <= tolerance <= 90:
        raise AssetPrepError('background_tolerance must be 0..90')
    if not 0 <= padding <= 40:
        raise AssetPrepError('padding must be 0..40')
    image, method = _drop_background(im.convert('RGBA'), tolerance)
    alpha = np.asarray(image.getchannel('A'))
    ys, xs = np.nonzero(alpha >= 16)
    if len(xs) < 16:
        raise AssetPrepError('Empty or near-empty cell: check sheet mapping and background')
    occupied = len(xs) / float(image.width * image.height)
    if occupied > 0.93:
        raise AssetPrepError('Cell still almost opaque; transparent parts / solid background required')
    x0, y0, x1, y1 = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    bbox = (max(0, x0 - padding), max(0, y0 - padding),
            min(image.width, x1 + padding), min(image.height, y1 + padding))
    return Cutout(image.crop(bbox), method, round(occupied, 5), bbox)


def _grid_crop(sheet: Image.Image, r: int, c: int, rows: int, cols: int,
               inset: int) -> Image.Image:
    if not (0 <= r < rows and 0 <= c < cols):
        raise AssetPrepError(f'Grid cell outside sheet: {(r, c)}')
    l = math.floor(c * sheet.width / cols) + inset
    t = math.floor(r * sheet.height / rows) + inset
    rr = math.floor((c + 1) * sheet.width / cols) - inset
    bb = math.floor((r + 1) * sheet.height / rows) - inset
    if rr - l < 10 or bb - t < 10:
        raise AssetPrepError('Grid cell too small; decrease inset')
    return sheet.crop((l, t, rr, bb))


def _sized(cut: Image.Image, name: str, factor: float) -> Image.Image:
    width = max(8, round(TARGET_WIDTH[name] * factor))
    height = max(4, round(cut.height * (width / cut.width)))
    if height > 900:
        raise AssetPrepError(f'Unexpected aspect ratio for {name}; revise sprite')
    return cut.resize((width, height), Image.Resampling.LANCZOS)


def prepare_assets(spec_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Create ready-to-render PNG assets, draft rig JSON, visual QA preview.

    Spec supports {"source":"sheet","sheet":"...","grid":[3,4],
    "cells":{"head":[0,0],...}} or {"source":"parts","input_dir":"..."}.
    Paths are relative to the spec file and constrained to that directory.
    """
    spec_path = Path(spec_path).resolve()
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    base = spec_path.parent
    source = spec.get('source')
    if source not in ('sheet', 'parts'):
        raise AssetPrepError('source must be "sheet" or "parts"; a flattened full character is unsupported')
    width, height = int(spec.get('width', 360)), int(spec.get('height', 640))
    if not (120 <= width <= 1920 and 120 <= height <= 1920 and width * height <= 2_100_000):
        raise AssetPrepError('Invalid CPU-safe output canvas')
    fps, dur = int(spec.get('fps', 12)), float(spec.get('duration_sec', 5))
    if not (6 <= fps <= 30 and 0.1 < dur <= 600):
        raise AssetPrepError('Invalid FPS/duration')
    factor = min(width / 360.0, height / 640.0)
    tolerance = int(spec.get('background_tolerance', 26))
    inset = int(spec.get('cell_inset_px', 5))
    cells = spec.get('cells', DEFAULT_CELLS)
    if not isinstance(cells, dict):
        raise AssetPrepError('cells must map part names to [row,col]')
    if source == 'sheet':
        raw_sheet = _load_image(_safe_child(base, str(spec['sheet'])))
        rows, cols = spec.get('grid', [3, 4])
        rows, cols = int(rows), int(cols)
        if not (1 <= rows <= 12 and 1 <= cols <= 12):
            raise AssetPrepError('Unsupported sheet grid')
        if len({tuple(cell) for cell in cells.values()}) != len(cells):
            raise AssetPrepError('Duplicate sheet grid cell; each part needs its own cell')
        requested = {name: _grid_crop(raw_sheet, *map(int, cells[name]), rows, cols, inset)
                     for name in PARTS if name in cells}
    else:
        folder = _safe_child(base, str(spec.get('input_dir', '.')))
        parts = spec.get('parts', {})
        if not isinstance(parts, dict):
            raise AssetPrepError('parts must map body part names to file paths')
        requested = {}
        for name in PARTS:
            filename = parts.get(name, f'{name}.png')
            path = _safe_child(folder, str(filename))
            if path.is_file():
                requested[name] = _load_image(path)
    missing = sorted(set(REQUIRED) - set(requested))
    if missing:
        raise AssetPrepError(f'Missing essential body-part assets: {", ".join(missing)}')
    # Collect in memory BEFORE producing files to avoid partial success on bad inputs.
    extracted = {name: cutout_image(im, tolerance=tolerance)
                 for name, im in requested.items()}
    if {'eyes_open', 'eyes_closed'} & extracted.keys() and not {'eyes_open', 'eyes_closed'} <= extracted.keys():
        raise AssetPrepError('Provide both eyes_open and eyes_closed for stable blinking')
    if {'mouth_open', 'mouth_closed'} & extracted.keys() and not {'mouth_open', 'mouth_closed'} <= extracted.keys():
        raise AssetPrepError('Provide both mouth_open and mouth_closed for stable talking')
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    assets = out / 'assets'
    assets.mkdir(exist_ok=True)
    sizes: dict[str, tuple[int, int]] = {}
    report = {}
    for name, cut in extracted.items():
        sized = _sized(cut.image, name, factor)
        sized.save(assets / f'{name}.png')
        sizes[name] = sized.size
        report[name] = {'source_bbox': list(cut.source_bbox), 'size': list(sized.size),
                        'method': cut.method, 'foreground_fraction': cut.foreground_fraction}
    scene_origin = (width / 2, height * .86)
    rig = {}
    for name in REQUIRED:
        xoff, yoff = BODY_ANCHORS[name]
        joint = JOINTS[name]
        size = sizes[name]
        rig[name] = {'file': f'assets/{name}.png',
                     'anchor': [round(scene_origin[0] + xoff * factor, 2),
                                round(scene_origin[1] + yoff * factor, 2)],
                     'pivot': [round(size[0] * joint[0], 2), round(size[1] * joint[1], 2)]}
    for name in OPTIONAL:
        if name in sizes:
            head_size = sizes['head']
            coords = FACE_TOP_LEFT[name]
            rig[name] = {'file': f'assets/{name}.png',
                         'anchor': [round(head_size[0] * coords[0], 2),
                                    round(head_size[1] * coords[1], 2)],
                         'pivot': [0, 0]}
    manifest = {'width': width, 'height': height, 'fps': fps,
                'duration_sec': dur, 'background_color': spec.get('background_color', '#b8e6fd'),
                'motions': spec.get('motions', ['idle', 'wave', 'blink', 'talk', 'nod']),
                'rig': rig}
    manifest_path = out / 'cartoon.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (out / 'asset_qa.json').write_text(json.dumps({
        'status': 'draft_requires_visual_approval', 'source': source,
        'parts': report, 'note': 'Pivots and facial placement are heuristic; inspect preview.png and adjust cartoon.json'
    }, indent=2), encoding='utf-8')
    from .cartoon_motion_cpu import CartoonMotion
    CartoonMotion(manifest, out).frame(0).save(out / 'preview.png')
    return manifest_path, out / 'preview.png'
