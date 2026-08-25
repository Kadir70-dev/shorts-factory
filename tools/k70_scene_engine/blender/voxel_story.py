"""Bridge to _voxel_story_script.py -- VOXEL_STORY mode that produces
recognizable objects (house/bank/dollar/car), not an abstract cube blob.
Fixes the audit finding that the mortgage video's one voxel scene
"communicated nothing" without narration.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .bpy_bridge import find_blender
from .hardware import detect as detect_hardware
from ..cache import render_cache

SCRIPT = Path(__file__).resolve().parent / "_voxel_story_script.py"


def render_voxel_object(*, object_type: str, params: dict | None = None,
                        block_size: float = 0.35, width: int = 1920, height: int = 1080,
                        out_dir: Path, use_cache: bool = True,
                        samples_override: int | None = None) -> Path:
    hw = detect_hardware()
    render_settings = {"engine": hw.recommended_engine,
                       "samples": samples_override or hw.max_samples}

    h = render_cache.scene_hash(
        assets=[f"voxel_story:{object_type}"], camera={"mode": "voxel_story_auto"},
        lighting={}, animation="static",
        text=json.dumps(params or {}, sort_keys=True) + f"|block={block_size}",
        resolution=(width, height), render_settings=render_settings,
    )
    if use_cache:
        hit = render_cache.lookup(h, ext="png")
        if hit:
            return hit

    blender_exe = find_blender()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"k70_voxelstory_{h[:12]}.png"

    spec = {
        "object_type": object_type, "params": params or {}, "block_size": block_size,
        "render": {"engine": render_settings["engine"], "samples": render_settings["samples"],
                   "width": width, "height": height, "output": str(output_path)},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name

    proc = subprocess.run(
        [str(blender_exe), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=600,
    )
    Path(args_path).unlink(missing_ok=True)

    candidates = list(out_dir.glob(f"k70_voxelstory_{h[:12]}*"))
    if not candidates:
        raise RuntimeError(
            f"voxel story render produced no output.\nSTDOUT:\n{proc.stdout[-2000:]}\n"
            f"STDERR:\n{proc.stderr[-2000:]}")
    result = candidates[0]
    if use_cache:
        render_cache.store(h, result, ext="png")
    return result
