"""VOXEL_STORY mode (brief section 8): voxelizes an eligible CC0 mesh and
renders the resulting block geometry with Blender's own renderer.

Adapts the logic of the vendored
`vendor/minecraft-voxel-loader-scripts/Scripts/blender_voxelizer.py` (MIT,
see license/sources.py:source:minecraft-voxel-loader) into a
`scene_builder_script.py`-style headless call. Deliberately does NOT reuse
that script byte-for-byte: the original is written as an interactive
Blender-UI panel operator (`bl_info`/`bpy.types.Panel`) meant to be pasted
into Blender's Scripting tab by a human and clicked, not invoked headless
from a command line. `_voxelize_script.py` below extracts its core
algorithm (iterate a mesh's vertices, bucket them into a 3D grid of unit
cubes) into a plain function callable from `--background --python`, with
zero Minecraft/Fabric/Mojang code path anywhere in the chain -- the output
is rendered by Blender itself (Cycles/EEVEE), never played back in an
actual Minecraft client.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .bpy_bridge import find_blender
from ..cache import render_cache

VOXELIZE_SCRIPT = Path(__file__).resolve().parent / "_voxelize_script.py"


def voxelize_and_render(*, source_asset_path: str, source_format: str,
                        block_size: float, width: int, height: int,
                        out_dir: Path, use_cache: bool = True) -> Path:
    from .hardware import detect as detect_hardware
    hw = detect_hardware()
    render_settings = {"engine": hw.recommended_engine, "samples": hw.max_samples}

    h = render_cache.scene_hash(
        assets=[source_asset_path], camera={"mode": "voxel_default"}, lighting={},
        animation="voxelize_static", text=f"block_size={block_size}",
        resolution=(width, height), render_settings=render_settings,
    )
    if use_cache:
        hit = render_cache.lookup(h, ext="png")
        if hit:
            return hit

    blender_exe = find_blender()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"k70_voxel_{h[:12]}.png"

    spec = {
        "source_path": source_asset_path, "source_format": source_format,
        "block_size": block_size,
        "render": {"engine": render_settings["engine"], "samples": render_settings["samples"],
                   "width": width, "height": height, "output": str(output_path)},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name

    proc = subprocess.run(
        [str(blender_exe), "--background", "--python", str(VOXELIZE_SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=600,
    )
    Path(args_path).unlink(missing_ok=True)

    candidates = list(out_dir.glob(f"k70_voxel_{h[:12]}*"))
    if not candidates:
        raise RuntimeError(
            f"voxel render produced no output.\nSTDOUT:\n{proc.stdout[-2000:]}\n"
            f"STDERR:\n{proc.stderr[-2000:]}")
    result = candidates[0]
    if use_cache:
        render_cache.store(h, result, ext="png")
    return result
