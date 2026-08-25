#!/usr/bin/env python3
"""K70 VOXEL V5.2 -- ONE 5-second 1080x1920 animation test of the winning
still-image scene (seed from data/jobs/k70_voxel_v52_visual_director/
director_decisions.json).

Subtle cinematic camera dolly + natural John walk + subtle NPC
idle/walk, reusing the exact same scene layout/lighting the still-image
director already selected and approved. This does NOT build a full
Short -- one clip only.

    .venv-win/Scripts/python.exe scripts/build_voxel_v52_animation_test.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/k70_scene_engine/director"))
from shot_templates import resolve_shot_spec
from composition import plan_scene

BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
BDIR = ROOT / "tools/k70_scene_engine/blender"
JOB_DIR = ROOT / "data/jobs/k70_voxel_v52_visual_director"
FRAMES_DIR = JOB_DIR / "animation_test_frames"
OUT_MP4 = JOB_DIR / "animation_test_5s.mp4"

SHOT_SPEC = {
    "shot_type": "city_walk", "hero": "john", "location": "financial_district",
    "time_of_day": "golden_hour", "mood": "optimistic", "density": "high",
    "camera": "medium_tracking", "story_focus": "john",
    "required_visible": ["john", "3_npcs", "2_vehicles", "storefront", "street_sign", "skyline"],
}

FPS = 24
DURATION_SEC = 5


def main():
    t0 = time.time()
    decisions = json.loads((JOB_DIR / "director_decisions.json").read_text(encoding="utf-8"))
    winner_seed = decisions["winner_seed"]
    print(f"K70 V5.2 animation test -- rebuilding winning plan for seed={winner_seed}")

    spec = resolve_shot_spec(SHOT_SPEC)
    plan = plan_scene(spec, winner_seed)

    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    args_spec = {
        "plan": plan, "fps": FPS, "duration_sec": DURATION_SEC,
        "width": 1080, "height": 1920, "samples": 24,
        "output_dir": str(FRAMES_DIR), "practical_emission": 2.3,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(args_spec, f)
        args_path = f.name

    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(BDIR / "_director_animate_test.py"), "--", args_path],
        capture_output=True, text=True, timeout=3600,
    )
    Path(args_path).unlink(missing_ok=True)
    n_frame_ok = proc.stdout.count("K70_ANIM_FRAME_OK")
    print(f"Rendered {n_frame_ok} new frames this run "
         f"({len(list(FRAMES_DIR.glob('frame_*.png')))} total frames on disk)")
    if "K70_ANIM_RENDER_DONE" not in proc.stdout:
        print("BLENDER RENDER DID NOT COMPLETE")
        print(proc.stdout[-3000:])
        print(proc.stderr[-2000:])
        sys.exit(1)

    total_frames = FPS * DURATION_SEC
    n_frames_on_disk = len(list(FRAMES_DIR.glob("frame_*.png")))
    if n_frames_on_disk < total_frames:
        print(f"INCOMPLETE: expected {total_frames} frames, found {n_frames_on_disk}")
        sys.exit(1)

    ffmpeg_proc = subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        str(OUT_MP4),
    ], capture_output=True, text=True)
    if ffmpeg_proc.returncode != 0:
        print("FFMPEG FAILED:", ffmpeg_proc.stderr[-2000:])
        sys.exit(1)

    total_time = round(time.time() - t0, 1)
    print(f"\nANIMATION TEST COMPLETE: {OUT_MP4}")
    print(f"Frames: {total_frames} @ {FPS}fps ({DURATION_SEC}s)")
    print(f"Total time: {total_time}s")


if __name__ == "__main__":
    main()
