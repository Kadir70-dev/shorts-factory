#!/usr/bin/env python3
"""K70 VOXEL V3 -- premium block-world benchmark. ONE cinematic short
proving the new texture/geometry/lighting/environment system before it
touches any production video. Does NOT rerender Day 06, does NOT touch
the 9-mode master, does NOT start Day 07.

4 shots, single character (John, K70 V3):
  1. Exit block-style apartment/house
  2. Walk through a K70 block-city street
  3. Enter a block-style bank/office, interact
  4. Cinematic house/street ending, wide composition

All rendering goes through _voxel_human_v3_script.py (V3 character +
_k70_block_kit.py environment pieces + the new block_world_v3 lighting
preset). Checkpoint/resume-safe (each beat/frame skipped if already
rendered), same discipline as the Day 06 scripts.

    .venv-win/Scripts/python.exe scripts/build_voxel_v3_benchmark.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
BDIR = ROOT / "tools/k70_scene_engine/blender"
MUSIC_BED = ROOT / "data/assets/music/beds/premium_a.wav"

JOB_DIR = ROOT / "data" / "jobs" / "k70_voxel_v3_benchmark"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1080, 1920, 24
XFADE_DUR = 0.4


def winpath(p: Path) -> str:
    return str(p).replace("\\", "/")


def eng(samples=24):
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": W, "height": H}


def _done(p: Path, min_size: int = 1024) -> bool:
    return p.exists() and p.stat().st_size > min_size


def render_v3(spec: dict, tag: str, timeout: int = 900) -> Path:
    out_dir = SHOTS_DIR / tag
    spec["render"]["output_dir"] = winpath(out_dir)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(BDIR / "_voxel_human_v3_script.py"), "--", args_path],
        capture_output=True, text=True, timeout=timeout,
    )
    Path(args_path).unlink(missing_ok=True)
    if "K70_VOXEL_V3_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"shot {tag} failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print(f"  [{tag}] rendered -> {out_dir}")
    return out_dir


def frames_to_clip(frames_dir: Path, out_mp4: Path, n_frames: int, duration_sec: float) -> Path:
    fps = n_frames / duration_sec
    tmp = out_mp4.with_suffix(".raw.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(tmp)],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(tmp), "-t", str(duration_sec), "-r", str(FPS),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", "-an", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    tmp.unlink(missing_ok=True)
    return out_mp4


LIGHT = {"mode": "block_world_v3", "sun_energy": 4.2, "sun_rotation": [0.95, 0, 0.75],
         "ambient_strength": 0.16, "ambient_preset": "exterior_day"}

SHOTS = [
    dict(id="exit_house", duration=4.0, n_frames=10, frame_range=[0, 45]),
    dict(id="street_walk", duration=4.5, n_frames=12, frame_range=[0, 72]),
    dict(id="bank_interior", duration=4.0, n_frames=10, frame_range=[0, 50]),
    dict(id="cinematic_close", duration=3.5, n_frames=10, frame_range=[0, 40]),
]


def build_specs():
    specs = {}

    # ---- Shot 1: exit house ---- #
    specs["exit_house"] = {
        "characters": [{"role": "john", "location": [0.0, 0.55, 0], "rotation_z_deg": 5,
                        "animation": {"type": "idle", "params": {"length": 40}}}],
        "env_pieces": [
            {"fn": "build_house", "kwargs": {"name": "house1", "location": [0.0, 2.3, 0], "w": 2.6, "d": 2.2, "h": 1.7}},
            {"fn": "build_sidewalk_segment", "kwargs": {"name": "walk1", "location": [0.0, 0.4, 0], "length": 4.0, "width": 2.4}},
            {"fn": "build_tree", "kwargs": {"name": "tree1", "location": [-1.6, 1.4, 0]}},
            {"fn": "build_streetlamp", "kwargs": {"name": "lamp1", "location": [1.5, 0.6, 0]}},
        ],
        "lighting": LIGHT,
        "camera_keyframes": [
            {"frame": 0, "location": [1.6, -5.4, 1.35], "look_at": [0.0, 0.9, 0.85]},
            {"frame": 45, "location": [1.3, -4.6, 1.3], "look_at": [0.0, 0.9, 0.85]},
        ],
        "lens": 82, "dof": True, "fstop": 2.6,
    }

    # ---- Shot 2: street walk ---- #
    specs["street_walk"] = {
        "characters": [{"role": "john", "location": [-0.3, -1.4, 0], "rotation_z_deg": 0,
                        "animation": {"type": "walk", "params": {"length": 22, "n_cycles": 3, "stride_deg": 28, "forward_dist": 3.2}}}],
        "env_pieces": [
            {"fn": "build_road_segment", "kwargs": {"name": "road1", "location": [0.0, 0.0, 0], "length": 10.0, "width": 1.8}},
            {"fn": "build_sidewalk_segment", "kwargs": {"name": "sw_l", "location": [-1.5, 0.0, 0], "length": 10.0, "width": 1.0}},
            {"fn": "build_sidewalk_segment", "kwargs": {"name": "sw_r", "location": [1.5, 0.0, 0], "length": 10.0, "width": 1.0}},
            {"fn": "build_wall_panel", "kwargs": {"name": "bldg_l1", "location": [-2.4, -1.5, 0], "w": 1.8, "h": 2.6, "material": "brick"}},
            {"fn": "build_wall_panel", "kwargs": {"name": "bldg_l2", "location": [-2.4, 1.5, 0], "w": 1.8, "h": 2.2, "material": "concrete"}},
            {"fn": "build_wall_panel", "kwargs": {"name": "bldg_r1", "location": [2.4, -0.5, 0], "w": 1.8, "h": 3.0, "material": "brick"}},
            {"fn": "build_wall_panel", "kwargs": {"name": "bldg_r2", "location": [2.4, 2.5, 0], "w": 1.8, "h": 2.4, "material": "concrete"}},
            {"fn": "build_window", "kwargs": {"name": "win_l1", "location": [-2.4, -1.5, 1.5]}},
            {"fn": "build_window", "kwargs": {"name": "win_r1", "location": [2.4, -0.5, 1.7]}},
            {"fn": "build_streetlamp", "kwargs": {"name": "lamp2", "location": [-1.5, 0.5, 0]}},
            {"fn": "build_streetlamp", "kwargs": {"name": "lamp3", "location": [1.5, 2.5, 0]}},
            {"fn": "build_tree", "kwargs": {"name": "tree2", "location": [4.8, -1.0, 0]}},
        ],
        "lighting": LIGHT,
        "camera_keyframes": [
            {"frame": 0, "location": [3.1, -5.6, 1.35], "look_at": [-0.3, -1.4, 0.8]},
            {"frame": 72, "location": [3.1, -2.4, 1.35], "look_at": [-0.3, 1.8, 0.8]},
        ],
        "lens": 68, "dof": True, "fstop": 2.8,
    }

    # ---- Shot 3: bank interior ---- #
    specs["bank_interior"] = {
        "characters": [{"role": "john", "location": [0.0, -0.3, 0], "rotation_z_deg": 180,
                        "animation": {"type": "point", "params": {"start": 0, "length": 45}}}],
        "env_pieces": [
            {"fn": "build_wall_panel", "kwargs": {"name": "back_wall", "location": [0.0, 1.1, 0], "w": 3.4, "h": 2.4, "material": "office_surface"}},
            {"fn": "build_counter", "kwargs": {"name": "counter1", "location": [0.0, 0.55, 0], "w": 1.7, "d": 0.6, "h": 0.95}},
            {"fn": "build_sign", "kwargs": {"name": "banksign", "location": [0.0, 1.02, 1.7], "w": 1.0, "h": 0.35, "color_tex": "metal"}},
            {"fn": "build_desk", "kwargs": {"name": "sidedesk", "location": [1.4, 0.3, 0]}},
            {"fn": "build_chair", "kwargs": {"name": "sidechair", "location": [1.4, 0.75, 0]}},
            {"fn": "build_laptop", "kwargs": {"name": "laptop1", "location": [1.4, 0.15, 0.79]}},
            {"fn": "build_money_prop", "kwargs": {"name": "cash1", "location": [-0.3, 0.45, 0.99], "n": 3}},
        ],
        "lighting": {**LIGHT, "ambient_preset": "office_interior", "sun_energy": 2.6},
        "camera_keyframes": [
            {"frame": 0, "location": [1.9, -3.6, 1.35], "look_at": [0.1, 0.5, 0.85]},
            {"frame": 50, "location": [1.6, -3.2, 1.3], "look_at": [0.1, 0.5, 0.85]},
        ],
        "lens": 70, "dof": True, "fstop": 2.4,
    }

    # ---- Shot 4: cinematic close ---- #
    specs["cinematic_close"] = {
        "characters": [{"role": "john", "location": [0.2, 0.3, 0], "rotation_z_deg": -15,
                        "animation": {"type": "idle", "params": {"length": 40}}}],
        "env_pieces": [
            {"fn": "build_house", "kwargs": {"name": "house2", "location": [0.6, 2.6, 0], "w": 2.6, "d": 2.2, "h": 1.7}},
            {"fn": "build_road_segment", "kwargs": {"name": "road2", "location": [-1.6, 0.5, 0], "length": 6.0, "width": 1.6}},
            {"fn": "build_sidewalk_segment", "kwargs": {"name": "sw3", "location": [0.4, 0.2, 0], "length": 5.0, "width": 1.4}},
            {"fn": "build_streetlamp", "kwargs": {"name": "lamp4", "location": [-0.9, -0.6, 0]}},
            {"fn": "build_tree", "kwargs": {"name": "tree3", "location": [1.9, -0.6, 0]}},
            {"fn": "build_tree", "kwargs": {"name": "tree4", "location": [-2.3, 1.6, 0]}},
        ],
        "lighting": {**LIGHT, "sun_energy": 4.6},
        "camera_keyframes": [
            {"frame": 0, "location": [-2.4, -6.2, 1.4], "look_at": [0.2, 0.9, 0.9]},
            {"frame": 40, "location": [-2.0, -5.4, 1.35], "look_at": [0.2, 0.9, 0.9]},
        ],
        "lens": 68, "dof": True, "fstop": 2.2,
    }

    return specs


def main():
    t0 = time.time()
    print("K70 VOXEL V3 -- premium block-world benchmark")
    specs = build_specs()
    clips: dict[str, Path] = {}

    for shot in SHOTS:
        sid = shot["id"]
        out_mp4 = SHOTS_DIR / f"{sid}.mp4"
        if _done(out_mp4):
            print(f"  [resume] {sid}.mp4 already present, skipping")
            clips[sid] = out_mp4
            continue
        spec = specs[sid]
        spec["n_frames"] = shot["n_frames"]
        spec["frame_range"] = shot["frame_range"]
        spec["render"] = eng()
        d = render_v3(spec, sid)
        clips[sid] = frames_to_clip(d, out_mp4, shot["n_frames"], shot["duration"])

    order = [s["id"] for s in SHOTS]
    durations = [s["duration"] for s in SHOTS]

    inputs = []
    for sid in order:
        inputs += ["-i", str(clips[sid])]
    filter_parts = []
    prev_label = "0:v"
    running_total = durations[0]
    for i in range(1, len(order)):
        out_label = f"v{i}" if i < len(order) - 1 else "vout"
        offset = running_total - XFADE_DUR
        filter_parts.append(
            f"[{prev_label}][{i}:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offset:.3f}[{out_label}]")
        running_total = running_total + durations[i] - XFADE_DUR
        prev_label = out_label
    filter_complex = ";".join(filter_parts)
    video_only = JOB_DIR / "video_only.mp4"
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex, "-map", "[vout]",
         "-pix_fmt", "yuv420p", "-r", str(FPS), str(video_only)],
        capture_output=True, text=True, check=True,
    )
    final_video_duration = running_total
    print(f"  [assemble] video_only duration ~{final_video_duration:.2f}s")

    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_only), "-stream_loop", "-1", "-i", str(MUSIC_BED),
         "-filter_complex", f"[1:a]volume=0.18,atrim=0:{final_video_duration:.3f}[aout]",
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-shortest", str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    n_thumbs = 9
    thumbs = []
    from PIL import Image
    for i in range(n_thumbs):
        t = final_video_duration * (i + 0.5) / n_thumbs
        tp = JOB_DIR / f"thumb_{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(final_mp4), "-vframes", "1", str(tp)],
                      capture_output=True, text=True)
        thumbs.append(Image.open(tp))
    cols, rows = 3, 3
    tw, th = 270, 480
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im.resize((tw, th)), ((i % cols) * tw, (i // cols) * th))
    sheet.save(JOB_DIR / "contact_sheet.jpg", quality=92)

    # comparison sheet: one frame per shot, labeled by extraction order
    comp_thumbs = []
    for sid in order:
        tp = JOB_DIR / f"comp_{sid}.jpg"
        subprocess.run(["ffmpeg", "-y", "-i", str(clips[sid]), "-vf", "select=eq(n\\,3)", "-vframes", "1", str(tp)],
                      capture_output=True, text=True)
        comp_thumbs.append(Image.open(tp))
    comp_sheet = Image.new("RGB", (tw * 4, th), (15, 15, 18))
    for i, im in enumerate(comp_thumbs):
        comp_sheet.paste(im.resize((tw, th)), (i * tw, 0))
    comp_sheet.save(JOB_DIR / "comparison_sheet.jpg", quality=92)

    total_build_time = round(time.time() - t0, 1)
    dur_actual = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)],
                                capture_output=True, text=True).stdout.strip()
    metadata = {
        "title": "K70 Voxel V3 -- Premium Block-World Benchmark",
        "resolution": f"{W}x{H}", "fps": FPS,
        "duration_sec": float(dur_actual) if dur_actual else None,
        "shots": [{"id": s["id"], "duration_sec": s["duration"]} for s in SHOTS],
        "character_system": "_voxel_human_v3_script.py (new) -- same Empty-driven rig/animation "
                            "as _voxel_human_script.py, zero-bevel flat-shaded textured boxes instead "
                            "of flat-color beveled boxes",
        "texture_atlas": "tools/k70_scene_engine/vendor/k70_textures/characters/john/ "
                         "(original K70 pixel art, generated by tools/k70_scene_engine/textures/gen_k70_skin.py)",
        "environment_kit": "tools/k70_scene_engine/blender/_k70_block_kit.py + "
                           "tools/k70_scene_engine/vendor/k70_textures/environment/ "
                           "(original K70 pixel materials, no Poly Haven/photoreal assets used)",
        "lighting": "lighting_presets.setup_block_world_v3() -- directional Sun key light + low-strength "
                    "ambient fill, new preset, additive (does not modify prior HDRI-only presets)",
        "old_voxel_pipeline_untouched": "_voxel_human_script.py, Day 06, and the 9-mode master are "
                                        "unmodified by this benchmark",
        "total_build_time_sec": total_build_time,
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur_actual}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"COMPARISON SHEET: {JOB_DIR / 'comparison_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Total build time: {total_build_time}s")


if __name__ == "__main__":
    main()
