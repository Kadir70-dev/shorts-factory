"""Subprocess bridge from K70's own venv into Blender's bundled Python.

Blender ships its own Python interpreter with its own `bpy` module; there
is no way to `import bpy` from this project's `.venv-win`. Every
Blender-dependent operation in this engine therefore goes through
`render_still()`, which shells out to `blender --background --python
scene_builder_script.py -- args.json` and reads back a PNG (or, for
animated scenes, a short image sequence -- not implemented yet, see
FINAL_REPORT.md open items).

Caching (section 15) happens HERE, one layer above the actual Blender
call, so a cache hit means Blender never even launches.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .hardware import detect as detect_hardware
from ..cache import render_cache

SCRIPT = Path(__file__).resolve().parent / "scene_builder_script.py"

_PORTABLE_DIR = Path(__file__).resolve().parents[1] / ".blender_portable"

_BLENDER_SEARCH = [
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
]


class BlenderNotFound(RuntimeError):
    pass


def find_blender() -> Path:
    exe = shutil.which("blender")
    if exe:
        return Path(exe)
    if _PORTABLE_DIR.exists():
        for sub in sorted(_PORTABLE_DIR.glob("blender-*"), reverse=True):
            candidate = sub / "blender.exe"
            if candidate.exists():
                return candidate
    for candidate in _BLENDER_SEARCH:
        p = Path(candidate)
        if p.exists():
            return p
    program_files = Path(r"C:\Program Files\Blender Foundation")
    if program_files.exists():
        for sub in sorted(program_files.glob("Blender*"), reverse=True):
            exe = sub / "blender.exe"
            if exe.exists():
                return exe
    raise BlenderNotFound(
        "blender.exe not found on PATH or under 'C:\\Program Files\\Blender Foundation'. "
        "3D_CHARACTER / 3D_ENVIRONMENT / PROCEDURAL_CITY / VOXEL_STORY modes are "
        "unavailable until Blender is installed.")


def render_still(*, assets: list[dict], camera: dict, lighting: dict | None,
                 width: int, height: int, out_dir: Path, cache_key_extra: str = "",
                 use_cache: bool = True, studio: bool = True,
                 world_color: tuple[float, float, float] = (0.035, 0.045, 0.07),
                 samples_override: int | None = None) -> Path:
    """Render one static frame from imported asset(s). Returns the PNG path
    (from cache if a matching scene has already been rendered).

    `studio=True` (default) builds a ground plane + gradient world +
    three-point lighting around the subject (scene_builder_script.py's
    `_build_studio()`) instead of a bare sun light against pure black --
    see FINAL_REPORT.md item 30 for why the first test render needed this.
    """
    hw = detect_hardware()
    render_settings = {"engine": hw.recommended_engine, "device": hw.recommended_device,
                       "samples": samples_override or hw.max_samples}

    h = render_cache.scene_hash(
        assets=[json.dumps(a, sort_keys=True) for a in assets], camera=camera,
        lighting=lighting or {}, animation="static",
        text=f"{cache_key_extra}|studio={studio}|world={world_color}",
        resolution=(width, height), render_settings=render_settings,
    )
    if use_cache:
        hit = render_cache.lookup(h, ext="png")
        if hit:
            return hit

    blender_exe = find_blender()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"k70_scene_{h[:12]}.png"

    spec = {
        "assets": assets, "camera": camera, "lighting": lighting or {},
        "studio": studio, "world_color": list(world_color),
        "render": {"engine": render_settings["engine"], "device": render_settings["device"],
                   "samples": render_settings["samples"], "width": width, "height": height,
                   "output": str(output_path)},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name

    proc = subprocess.run(
        [str(blender_exe), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=600,
    )
    Path(args_path).unlink(missing_ok=True)

    rendered = output_path.with_suffix(".png") if output_path.suffix != ".png" else output_path
    # Blender appends its own extension logic; the exact on-disk name can
    # differ by one char (e.g. trailing frame number) -- glob for it.
    candidates = list(out_dir.glob(f"k70_scene_{h[:12]}*"))
    if not candidates:
        raise RuntimeError(
            f"Blender render produced no output file.\nSTDOUT:\n{proc.stdout[-2000:]}\n"
            f"STDERR:\n{proc.stderr[-2000:]}")
    result = candidates[0]

    if use_cache:
        render_cache.store(h, result, ext="png")
    return result
