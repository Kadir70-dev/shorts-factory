"""Bridge to _animated_character_script.py -- renders a real N-frame
animation sequence from a character's own glTF action and encodes it to
an mp4 via ffmpeg. This is the genuine fix for the audit finding that
Gobkit characters are "rigged, animation data exists, but never played":
this module actually samples and renders the action's real frame range.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .bpy_bridge import find_blender
from .hardware import detect as detect_hardware

SCRIPT = Path(__file__).resolve().parent / "_animated_character_script.py"


def render_animation(*, source_path: str, tint: tuple[float, float, float] | None,
                     n_frames: int, width: int, height: int, out_dir: Path,
                     fps: int = 6, samples_override: int | None = None) -> Path:
    """Renders n_frames sampled across the asset's real animation action
    and encodes them into an mp4. Returns the mp4 path. Raises
    RuntimeError (does not silently fall back to a static image) if the
    asset has no armature+action -- see script docstring."""
    hw = detect_hardware()
    render_settings = {"engine": hw.recommended_engine,
                       "samples": samples_override or max(16, hw.max_samples // 2)}

    blender_exe = find_blender()
    out_dir = out_dir.resolve()
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    spec = {
        "source_path": source_path, "tint": list(tint) if tint else None,
        "n_frames": n_frames,
        "render": {"engine": render_settings["engine"], "samples": render_settings["samples"],
                   "width": width, "height": height, "output_dir": str(frames_dir)},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name

    proc = subprocess.run(
        [str(blender_exe), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=900,
    )
    Path(args_path).unlink(missing_ok=True)

    if "K70_ANIM_SEQUENCE_OK" not in proc.stdout:
        raise RuntimeError(
            f"animation render did not complete.\nSTDOUT:\n{proc.stdout[-3000:]}\n"
            f"STDERR:\n{proc.stderr[-1500:]}")

    frame_files = sorted(frames_dir.glob("frame_*.png"))
    if not frame_files:
        raise RuntimeError(f"no frames written to {frames_dir}")

    out_mp4 = out_dir / "animation.mp4"
    ff = subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%03d.png"),
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         str(out_mp4)],
        capture_output=True, text=True,
    )
    if ff.returncode != 0 or not out_mp4.exists():
        raise RuntimeError(f"ffmpeg encode failed: {ff.stderr[-1500:]}")
    return out_mp4
