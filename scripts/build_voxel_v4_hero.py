#!/usr/bin/env python3
"""K70 VOXEL V4 -- hero frame driver. Cheap preview by default; pass
--final for the full 1080x1920 high-sample render.

    .venv-win/Scripts/python.exe scripts/build_voxel_v4_hero.py [--final]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
BDIR = ROOT / "tools/k70_scene_engine/blender"
JOB_DIR = ROOT / "data" / "jobs" / "k70_voxel_v4_hero"
JOB_DIR.mkdir(parents=True, exist_ok=True)

CAMERA = {
    "camera_location": [2.4, -4.3, 1.3],
    "camera_look_at": [0.05, 3.2, 1.3],
    "focus_at": [0.35, 0.9, 1.0],
    "lens": 24, "fstop": 3.6,
}


def run(final: bool):
    if final:
        spec = {**CAMERA, "width": 1080, "height": 1920, "samples": 96,
                "output_path": str(JOB_DIR / "hero_1080x1920.png"),
                "provenance_path": str(JOB_DIR / "_provenance.json")}
    else:
        spec = {**CAMERA, "width": 540, "height": 960, "samples": 24,
                "output_path": str(JOB_DIR / "preview.png"),
                "provenance_path": str(JOB_DIR / "_provenance_preview.json")}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(BDIR / "_voxel_v4_hero_scene.py"), "--", args_path],
        capture_output=True, text=True, timeout=900,
    )
    Path(args_path).unlink(missing_ok=True)
    print(proc.stdout[-4000:])
    if proc.returncode != 0 or "K70_V4_HERO_RENDER_OK" not in proc.stdout:
        print("STDERR:", proc.stderr[-3000:])
        raise RuntimeError("hero scene render failed")
    print(f"Rendered: {spec['output_path']}")


if __name__ == "__main__":
    run(final="--final" in sys.argv)
