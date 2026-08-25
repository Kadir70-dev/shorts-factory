#!/usr/bin/env python3
"""Finishes the voxel benchmark using already-rendered shot1/2/3, since
the office shot (shot456) timed out on the first full run. Renders
shot456 (lighter settings: no DOF, 12 frames), shot7 (chart), shot8
(ending), then assembles final.mp4 + contact sheet.
"""
from __future__ import annotations
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from build_voxel_benchmark_ep01 import (
    JOB_DIR, SHOTS_DIR, render_engine, render_blender, frames_to_mp4,
    build_chart_cards, build_contact_sheet, FPS,
)

clips = [SHOTS_DIR / "shot1_house_stock.mp4"]

spec2 = {
    "scene_type": "house", "house_location": [0, 2.6, 0], "house_scale": 1.0,
    "characters": [{
        "role": "john", "location": [0, -2.6, 0], "rotation_z_deg": 0,
        "animation": {"type": "walk", "params": {"length": 22, "n_cycles": 3, "stride_deg": 28, "forward_dist": 2.2}},
    }],
    "camera": {"location": [-5.5, -3.2, 1.6], "look_at": [0, -0.5, 0.85]},
    "lens": 32, "n_frames": 14,
    "frame_range": [0, 66],
    "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 24, "width": 1920, "height": 1080},
}
d2 = render_blender(spec2, "shot2_john_walk_v2")
clips.append(frames_to_mp4(d2, SHOTS_DIR / "shot2_john_walk.mp4", 8))

spec3 = {
    "scene_type": "plain",
    "characters": [{
        "role": "john", "location": [0, 0, 0], "rotation_z_deg": -18,
        "animation": {"type": "idle", "params": {"length": 48}},
    }],
    "camera": {"location": [1.6, -3.3, 1.15], "look_at": [0, 0, 0.95]},
    "lens": 50, "dof": False, "n_frames": 12,
    "frame_range": [0, 48],
    "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 24, "width": 1920, "height": 1080},
}
d3 = render_blender(spec3, "shot3_john_closeup_v2")
clips.append(frames_to_mp4(d3, SHOTS_DIR / "shot3_john_closeup.mp4", 8))

spec456 = {
    "scene_type": "office",
    "characters": [
        {"role": "john", "location": [-0.55, -0.6, 0], "rotation_z_deg": 10,
         "animation": {"type": "idle", "params": {"length": 60}}},
        {"role": "banker", "location": [0.5, 1.5, 0], "rotation_z_deg": 200,
         "animation": {"type": "point", "params": {"start": 5, "length": 55}}},
    ],
    "camera": {"location": [2.6, -4.2, 1.5], "look_at": [0.0, 0.6, 0.9]},
    "lens": 32, "dof": False, "n_frames": 12,
    "frame_range": [0, 60],
    "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 24, "width": 1920, "height": 1080},
}
d456 = render_blender(spec456, "shot456_office_v2")
shot456 = frames_to_mp4(d456, SHOTS_DIR / "shot456_office.mp4", 8)
clips.append(shot456)

clips.append(build_chart_cards())

spec8 = {
    "scene_type": "house", "house_location": [0, 2.3, 0], "house_scale": 1.0,
    "characters": [{
        "role": "john", "location": [0, -1.0, 0], "rotation_z_deg": -25,
        "animation": {"type": "idle", "params": {"length": 50}},
    }],
    "camera": {"location": [-3.8, -4.5, 1.6], "look_at": [0, 0.6, 0.85]},
    "lens": 32, "dof": False, "n_frames": 12,
    "frame_range": [0, 50],
    "sun_rotation": [1.0, 0, 1.0], "sky_color": [0.75, 0.68, 0.55], "sky_strength": 1.1,
    "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 24, "width": 1920, "height": 1080},
}
d8 = render_blender(spec8, "shot8_ending")
shot8 = frames_to_mp4(d8, SHOTS_DIR / "shot8_ending.mp4", 8)
clips.append(shot8)

import subprocess
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
