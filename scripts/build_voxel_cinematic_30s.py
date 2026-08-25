#!/usr/bin/env python3
"""K70 PREMIUM CINEMATIC VOXEL -- 30-second story sequence, no
narration. Uses the enhanced _voxel_human_script.py (real HDRI
lighting, animated dolly/tracking camera, DOF, foreground/midground/
background depth) on the proven K70 custom voxel_human character
system (Thomas Rig evaluated and reverted this session -- see
tools/k70_voxel_v2/notes/thomas_rig_final_status.md).

    .venv-win/Scripts/python.exe scripts/build_voxel_cinematic_30s.py
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
SCRIPT = ROOT / "tools/k70_scene_engine/blender/_voxel_human_script.py"

JOB_DIR = ROOT / "data" / "jobs" / "k70_voxel_cinematic_30s"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24


def render_blender(spec: dict, tag: str) -> Path:
    out_dir = SHOTS_DIR / tag
    spec["render"]["output_dir"] = str(out_dir)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=600,
    )
    Path(args_path).unlink(missing_ok=True)
    if "K70_VOXEL_HUMAN_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"shot {tag} failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print(f"  [{tag}] rendered -> {out_dir}")
    return out_dir


def frames_to_mp4(frames_dir: Path, out_mp4: Path, n_frames: int, duration_sec: float) -> Path:
    """Permanent fix (was: hardcoded fps=10 regardless of n_frames/target
    duration, e.g. 20 frames / 10fps = 2.0s instead of the intended ~7-8s).
    fps is now DERIVED from n_frames and the shot's actual target duration
    so output length is correct by construction, not patched after the
    fact via manual ffmpeg re-encodes."""
    fps = n_frames / duration_sec
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    return out_mp4


def eng():
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": 40, "width": W, "height": H}


def main() -> None:
    print("K70 PREMIUM CINEMATIC VOXEL -- 30s sequence")
    clips = []

    # ---------------------------------------------------------- #
    # Shot 1 (~7s): John in his apartment, cinematic dolly-in,
    # warm interior light, DOF with foreground wall/window depth.
    # ---------------------------------------------------------- #
    spec1 = {
        "scene_type": "apartment",
        "lighting_preset": "golden_hour", "hdri_strength": 0.55,
        "characters": [{
            "role": "john", "location": [0, -0.3, 0], "rotation_z_deg": -30,
            "animation": {"type": "idle", "params": {"length": 60}},
        }],
        "camera_keyframes": [
            {"frame": 0, "location": [2.6, -3.0, 1.7], "look_at": [0.2, -0.3, 1.1]},
            {"frame": 60, "location": [1.4, -1.8, 1.3], "look_at": [0.1, -0.2, 0.95]},
        ],
        "dof": True, "fstop": 1.8, "lens": 40,
        "n_frames": 20, "frame_range": [0, 60],
        "render": eng(),
    }
    d1 = render_blender(spec1, "shot1_apartment")
    clips.append(frames_to_mp4(d1, SHOTS_DIR / "shot1_apartment.mp4", spec1["n_frames"], 7.27))

    # ---------------------------------------------------------- #
    # Shot 2 (~8s): John walks through a living city street --
    # tracking dolly alongside him, golden hour, real depth.
    # ---------------------------------------------------------- #
    spec2 = {
        "scene_type": "street",
        "lighting_preset": "golden_hour", "hdri_strength": 0.9,
        "characters": [{
            "role": "john", "location": [0, -2.2, 0], "rotation_z_deg": 0,
            "animation": {"type": "walk", "params": {"length": 24, "n_cycles": 3, "stride_deg": 27, "forward_dist": 4.0}},
        }],
        "camera_keyframes": [
            {"frame": 0, "location": [-5.5, -4.5, 1.5], "look_at": [0, -1.8, 0.9]},
            {"frame": 36, "location": [-4.8, -1.0, 1.6], "look_at": [0, 0.2, 0.9]},
            {"frame": 72, "location": [-4.2, 2.0, 1.7], "look_at": [0, 2.2, 0.9]},
        ],
        "dof": True, "fstop": 2.5, "lens": 35,
        "n_frames": 22, "frame_range": [0, 72],
        "render": eng(),
    }
    d2 = render_blender(spec2, "shot2_street")
    clips.append(frames_to_mp4(d2, SHOTS_DIR / "shot2_street.mp4", spec2["n_frames"], 8.0))

    # ---------------------------------------------------------- #
    # Shot 3 (~8s): office, John + Banker, slow orbit camera,
    # Banker gestures explaining something.
    # ---------------------------------------------------------- #
    spec3 = {
        "scene_type": "office",
        "lighting_preset": "office_interior", "hdri_strength": 0.7,
        "characters": [
            {"role": "john", "location": [-0.55, -0.6, 0], "rotation_z_deg": 15,
             "animation": {"type": "idle", "params": {"length": 60}}},
            {"role": "banker", "location": [0.5, 1.5, 0], "rotation_z_deg": 195,
             "animation": {"type": "point", "params": {"start": 8, "length": 55}}},
        ],
        "camera_keyframes": [
            {"frame": 0, "location": [3.2, -3.6, 1.6], "look_at": [0.0, 0.6, 0.95]},
            {"frame": 60, "location": [-2.6, -3.4, 1.7], "look_at": [-0.1, 0.6, 0.95]},
        ],
        "dof": True, "fstop": 2.8, "lens": 32,
        "n_frames": 20, "frame_range": [0, 60],
        "render": eng(),
    }
    d3 = render_blender(spec3, "shot3_office")
    clips.append(frames_to_mp4(d3, SHOTS_DIR / "shot3_office.mp4", spec3["n_frames"], 7.27))

    # ---------------------------------------------------------- #
    # Shot 4 (~7s): cinematic ending -- John near the house at
    # golden hour, slow pull-back reveal.
    # ---------------------------------------------------------- #
    spec4 = {
        "scene_type": "house", "house_location": [0, 2.3, 0], "house_scale": 1.0,
        "lighting_preset": "golden_hour", "hdri_strength": 1.0,
        "characters": [{
            "role": "john", "location": [0, -1.0, 0], "rotation_z_deg": -25,
            "animation": {"type": "idle", "params": {"length": 55}},
        }],
        "camera_keyframes": [
            {"frame": 0, "location": [-2.6, -3.2, 1.4], "look_at": [0, 0.3, 0.9]},
            {"frame": 55, "location": [-5.2, -6.5, 2.0], "look_at": [0, 0.7, 1.0]},
        ],
        "dof": True, "fstop": 2.5, "lens": 35,
        "n_frames": 18, "frame_range": [0, 55],
        "render": eng(),
    }
    d4 = render_blender(spec4, "shot4_ending")
    clips.append(frames_to_mp4(d4, SHOTS_DIR / "shot4_ending.mp4", spec4["n_frames"], 6.55))

    # ---------------------------------------------------------- #
    # Assemble
    # ---------------------------------------------------------- #
    concat_list = JOB_DIR / "concat.txt"
    concat_list.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips), encoding="utf-8")
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(final_mp4)],
        capture_output=True, text=True, check=True,
    )
    print(f"\nFINAL VIDEO: {final_mp4}")

    build_contact_sheet(clips, JOB_DIR / "contact_sheet.jpg")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")


def build_contact_sheet(clips: list[Path], out_path: Path) -> None:
    from PIL import Image
    import subprocess as sp

    thumbs = []
    for i, clip in enumerate(clips):
        thumb_path = SHOTS_DIR / f"thumb_{i}.jpg"
        sp.run(["ffmpeg", "-y", "-i", str(clip), "-vf", "select=eq(n\\,5)", "-vframes", "1", str(thumb_path)],
              capture_output=True, text=True)
        if not thumb_path.exists():
            sp.run(["ffmpeg", "-y", "-i", str(clip), "-vframes", "1", str(thumb_path)],
                  capture_output=True, text=True)
        thumbs.append(Image.open(thumb_path))

    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    tw, th = 640, 360
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        im = im.resize((tw, th))
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
    sheet.save(out_path, quality=92)


if __name__ == "__main__":
    main()
