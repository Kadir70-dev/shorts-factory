"""Render cache for expensive 3D output (brief section 15).

Mirrors the existing pipeline's own cache pattern
(`apps/api/app/pipeline/util.py`'s `visual_cache_path`/`visual_cache_store`)
deliberately, rather than inventing a new convention: content-addressed by
a hash of everything that actually affects pixels, stored under
`data/cache/k70_scene_engine/`. A cache hit means "do not re-render",
matching section 15's own wording exactly.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path("data/cache/k70_scene_engine")


def scene_hash(*, assets: list[str], camera: dict, lighting: dict,
               animation: str, text: str, resolution: tuple[int, int],
               render_settings: dict, extra: dict | None = None) -> str:
    """Hash every input named in section 15: assets, scene configuration,
    camera, lighting, animation, text, resolution, render settings."""
    payload = {
        "assets": sorted(assets),
        "camera": camera,
        "lighting": lighting,
        "animation": animation,
        "text": text,
        "resolution": list(resolution),
        "render_settings": render_settings,
        "extra": extra or {},
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def cache_path(h: str, ext: str = "mp4", root: Path = CACHE_DIR) -> Path:
    return root / f"{h}.{ext}"


def lookup(h: str, ext: str = "mp4", root: Path = CACHE_DIR) -> Path | None:
    p = cache_path(h, ext, root)
    return p if p.exists() and p.stat().st_size > 0 else None


def store(h: str, rendered_file: Path, ext: str = "mp4", root: Path = CACHE_DIR) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    dest = cache_path(h, ext, root)
    if rendered_file.resolve() != dest.resolve():
        dest.write_bytes(rendered_file.read_bytes())
    return dest
