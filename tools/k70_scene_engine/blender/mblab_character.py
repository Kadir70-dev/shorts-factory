"""Bridge to _mblab_render_script.py -- renders an MB-Lab premium
character (dressed, lit, framed) from an already-finalized checkpoint
.blend. See _mblab_character.py's module docstring for the license
basis (MB-Lab's own license.txt: rendered 2D output is NOT a derivative
of the AGPL'd 3D database, commercial use of the render is explicitly
permitted) and why checkpoints exist (finalize_character's bake takes
several minutes; this bridge assumes that already happened once).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .bpy_bridge import find_blender
from .hardware import detect as detect_hardware
from ..cache import render_cache

SCRIPT = Path(__file__).resolve().parent / "_mblab_render_script.py"


def render_mblab_character(*, role: str, checkpoint: Path, lighting: str = "portrait_studio",
                           shot: str = "medium", angle: str = "three_quarter",
                           office_environment: bool = False, width: int = 1280, height: int = 720,
                           out_dir: Path, use_cache: bool = True, samples_override: int | None = None) -> Path:
    hw = detect_hardware()
    render_settings = {"engine": "BLENDER_EEVEE_NEXT", "samples": samples_override or hw.max_samples}

    h = render_cache.scene_hash(
        assets=[f"mblab:{role}:{checkpoint}"], camera={"shot": shot, "angle": angle},
        lighting={"preset": lighting}, animation="static",
        text=f"office={office_environment}",
        resolution=(width, height), render_settings=render_settings,
    )
    if use_cache:
        hit = render_cache.lookup(h, ext="png")
        if hit:
            return hit

    blender_exe = find_blender()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"k70_mblab_{h[:12]}.png"

    spec = {
        "role": role, "checkpoint": str(Path(checkpoint).resolve()), "lighting": lighting,
        "shot": shot, "angle": angle, "office_environment": office_environment,
        "width": width, "height": height, "samples": render_settings["samples"],
        "output": str(output_path),
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name

    proc = subprocess.run(
        [str(blender_exe), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=900,
    )
    Path(args_path).unlink(missing_ok=True)

    if "K70_MBLAB_SCENE_RENDER_OK" not in proc.stdout or not output_path.exists():
        raise RuntimeError(
            f"MB-Lab character render failed for role={role}.\nSTDOUT:\n{proc.stdout[-3000:]}\n"
            f"STDERR:\n{proc.stderr[-3000:]}")
    if use_cache:
        render_cache.store(h, output_path, ext="png")
    return output_path
