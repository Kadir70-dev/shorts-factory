"""Bridge to _voxel_human_script.py -- premium stylized voxel human
characters (the K70 approved visual direction; MB-Lab organic humans
are frozen/archived, not used in production). Handles both a single
still frame (for ken-burns beats) and a short animated clip (idle/
walk/point loop) from one shared scene-spec builder, reusing the
camera framing validated in the k70_voxel_character_benchmark_ep01
manual review.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .bpy_bridge import find_blender

SCRIPT = Path(__file__).resolve().parent / "_voxel_human_script.py"

# Per-scene camera presets, validated visually in the EP01 benchmark
# (wide enough to show full character +/- environment, no head crop).
_SCENE_CAMERA = {
    "apartment": {"camera": {"location": [1.6, -3.4, 1.2], "look_at": [0, 0.3, 0.95]}, "lens": 38},
    "office": {"camera": {"location": [2.6, -4.2, 1.5], "look_at": [0.0, 0.6, 0.9]}, "lens": 32},
    "house": {"camera": {"location": [-3.8, -4.5, 1.6], "look_at": [0, 0.6, 0.85]}, "lens": 32},
    "plain": {"camera": {"location": [1.6, -3.3, 1.15], "look_at": [0, 0, 0.95]}, "lens": 50},
}

_ANIM_PARAMS = {
    "idle": {"type": "idle", "params": {"length": 50}},
    "point": {"type": "point", "params": {"start": 5, "length": 55}},
    "walk": {"type": "walk", "params": {"length": 22, "n_cycles": 3, "stride_deg": 28, "forward_dist": 2.2}},
}
_ANIM_FRAME_RANGE = {"idle": [0, 50], "point": [0, 60], "walk": [0, 66]}


def _build_spec(scene: str, characters: list[dict], width: int, height: int, samples: int) -> dict:
    preset = _SCENE_CAMERA.get(scene, _SCENE_CAMERA["plain"])
    chars_spec = []
    default_locs = [[0, 0, 0]] if len(characters) == 1 else [[-0.55, -0.6, 0], [0.5, 1.5, 0]]
    for i, ch in enumerate(characters):
        anim_name = ch.get("anim", "idle")
        chars_spec.append({
            "role": ch["role"],
            "location": ch.get("location", default_locs[i] if i < len(default_locs) else [0, 0, 0]),
            "rotation_z_deg": ch.get("rotation_z_deg", 0),
            "animation": _ANIM_PARAMS[anim_name],
        })
    frame_range = _ANIM_FRAME_RANGE[characters[0].get("anim", "idle")]
    return {
        "scene_type": scene,
        "characters": chars_spec,
        "camera": preset["camera"], "lens": preset["lens"], "dof": False,
        "frame_range": frame_range,
        "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": width, "height": height},
    }


def render_voxel_human_still(*, scene: str, characters: list[dict], width: int, height: int,
                             out_dir: Path, samples: int = 32) -> Path:
    spec = _build_spec(scene, characters, width, height, samples)
    spec["n_frames"] = 1
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"voxel_still_{_tag(spec)}.png"
    if final.exists():
        # Real regression avoided: an earlier production run got killed
        # mid-pipeline (environmental, machine RAM pressure) with most
        # scenes already rendered. Without this check, re-running the
        # producer script re-renders every scene from scratch -- this
        # skip makes the whole pipeline resumable for free, matching
        # how the "chart" vis type already behaved.
        return final
    frames_dir = out_dir / f"voxel_still_{_tag(spec)}"
    spec["render"]["output_dir"] = str(frames_dir)
    _run(spec)
    result = frames_dir / "frame_000.png"
    final.write_bytes(result.read_bytes())
    return final


def render_voxel_human_clip(*, scene: str, characters: list[dict], width: int, height: int,
                            out_dir: Path, n_frames: int = 14, fps: int = 8, samples: int = 24) -> Path:
    spec = _build_spec(scene, characters, width, height, samples)
    spec["n_frames"] = n_frames
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = _tag(spec)
    out_mp4 = out_dir / f"voxel_clip_{tag}.mp4"
    if out_mp4.exists():
        return out_mp4
    frames_dir = out_dir / f"voxel_clip_{tag}"
    spec["render"]["output_dir"] = str(frames_dir)
    _run(spec)

    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%03d.png"),
         "-vf", f"scale={width}:{height}", "-pix_fmt", "yuv420p", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    if not out_mp4.exists():
        raise RuntimeError(f"ffmpeg failed to produce {out_mp4}")
    return out_mp4


def _tag(spec: dict) -> str:
    roles = "_".join(c["role"] for c in spec["characters"])
    anim = spec["characters"][0]["animation"]["type"]
    return f"{spec['scene_type']}_{roles}_{anim}"


def _run(spec: dict) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    blender_exe = find_blender()
    proc = subprocess.run(
        [str(blender_exe), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=420,
    )
    Path(args_path).unlink(missing_ok=True)
    if "K70_VOXEL_HUMAN_RENDER_OK" not in proc.stdout:
        raise RuntimeError(
            f"voxel human render failed.\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
