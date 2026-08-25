"""Bridge to _mblab_walk_script.py -- renders a real walk-cycle sequence
(MB-Lab's own bundled walking.bvh, retargeted onto the character rig)
and ffmpeg-encodes it to mp4. Same real-frames-only contract as
animated_character.py's Gobkit walk render from the earlier session --
raises if retargeting produced no action rather than faking a static
loop.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .bpy_bridge import find_blender
from .hardware import detect as detect_hardware

SCRIPT = Path(__file__).resolve().parent / "_mblab_walk_script.py"


def render_walk_animation(*, role: str, checkpoint: Path, house: bool = True,
                          lighting: str = "exterior_day", n_frames: int = 12,
                          width: int = 1920, height: int = 1080, fps: int = 8,
                          out_dir: Path, samples_override: int | None = None) -> Path:
    hw = detect_hardware()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / f"{role}_walk_frames"

    spec = {
        "role": role, "checkpoint": str(Path(checkpoint).resolve()), "house": house,
        "lighting": lighting, "n_frames": n_frames,
        "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": samples_override or hw.max_samples,
                   "width": width, "height": height, "output_dir": str(frames_dir)},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name

    blender_exe = find_blender()
    proc = subprocess.run(
        [str(blender_exe), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=900,
    )
    Path(args_path).unlink(missing_ok=True)

    if "K70_WALK_SEQUENCE_OK" not in proc.stdout:
        raise RuntimeError(
            f"walk animation render failed for role={role}.\nSTDOUT:\n{proc.stdout[-3000:]}\n"
            f"STDERR:\n{proc.stderr[-3000:]}")

    out_mp4 = out_dir / f"{role}_walk.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%03d.png"),
         "-vf", f"scale={width}:{height}", "-pix_fmt", "yuv420p", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    if not out_mp4.exists():
        raise RuntimeError(f"ffmpeg failed to produce {out_mp4}")
    return out_mp4
