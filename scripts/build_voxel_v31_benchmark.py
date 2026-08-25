#!/usr/bin/env python3
"""K70 VOXEL V3.1 -- premium polish pass. Builds on the APPROVED V3
foundation (same rig, same textured_box/UV technique, same lighting
architecture) -- this is density/polish, not a rebuild:
  - lighting_presets.setup_block_world_v31(): flat stylized sky (no HDRI
    photo visible anywhere) + warm sun / cool fill / rim
  - _k70_block_kit.py: multistory buildings w/ shopfronts+signage, traffic
    lights, benches, bins, fences, planters, crosswalks, vehicles, a
    distant block skyline + extended ground (background is ALSO block-
    world now, never a photo horizon)
  - gen_k70_skin.py: richer John detail (eye highlight, cheek shading,
    fabric bands, shoe tread) + 4 new NPC roles (sarah/banker/investor/
    worker) via the SAME character rig script, zero code changes needed
    there since it already takes `role` generically.

Does NOT touch Day 06, the 9-mode master, Synfig/Natron/Krita/Pencil2D,
Clay, Isometric, or Thomas Rig. Does NOT overwrite k70_voxel_v3_benchmark/.

Checkpoint/resume per shot -- same discipline as every prior K70 script.

    .venv-win/Scripts/python.exe scripts/build_voxel_v31_benchmark.py
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

JOB_DIR = ROOT / "data" / "jobs" / "k70_voxel_v31_benchmark"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1080, 1920, 24
XFADE_DUR = 0.4


def winpath(p: Path) -> str:
    return str(p).replace("\\", "/")


def eng(samples=22):
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": W, "height": H}


def _done(p: Path, min_size: int = 1024) -> bool:
    return p.exists() and p.stat().st_size > min_size


def render_v3(spec: dict, tag: str, timeout: int = 1100) -> Path:
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


LIGHT = {"mode": "block_world_v31", "sun_energy": 4.4, "sun_rotation": [0.95, 0, 0.75]}
LIGHT_GOLDEN = {"mode": "block_world_v31", "sun_energy": 4.0, "sun_rotation": [1.25, 0, 0.9],
               "sky_color": [0.72, 0.55, 0.42], "sun_color": [1.0, 0.82, 0.55], "fill_color": [0.5, 0.55, 0.75]}

SHOTS = [
    dict(id="city_establishing", duration=5.0, n_frames=14, frame_range=[0, 60]),
    dict(id="street_tracking", duration=5.0, n_frames=14, frame_range=[0, 80]),
    dict(id="bank_interior", duration=5.0, n_frames=14, frame_range=[0, 55]),
    dict(id="hero_ending", duration=5.0, n_frames=14, frame_range=[0, 55]),
]


def build_specs():
    specs = {}

    # ---- Shot 1: city establishing ---- #
    specs["city_establishing"] = {
        "characters": [{"role": "john", "location": [-0.4, 0.2, 0], "rotation_z_deg": 10,
                        "animation": {"type": "walk", "params": {"length": 26, "n_cycles": 1, "stride_deg": 20, "forward_dist": 0.8}}},
                       {"role": "worker", "location": [-2.3, 1.6, 0], "rotation_z_deg": -60,
                        "animation": {"type": "idle", "params": {"length": 40}}}],
        "env_pieces": [
            {"fn": "build_distant_ground", "kwargs": {"name": "ground1", "location": [0, 0, 0], "material": "concrete"}},
            {"fn": "build_distant_skyline", "kwargs": {"name": "sky1", "location": [0, 9, 0], "n_buildings": 7, "spread": 10, "seed": 3}},
            {"fn": "build_building_multistory", "kwargs": {"name": "bA", "location": [-2.6, 2.6, 0], "floors": 4, "w": 2.0, "d": 1.8,
                                                            "wall_material": "brick", "ground_shop": True, "shop_sign_key": "sign_cafe"}},
            {"fn": "build_building_multistory", "kwargs": {"name": "bB", "location": [2.4, 2.8, 0], "floors": 5, "w": 2.2, "d": 1.8,
                                                            "wall_material": "concrete", "ground_shop": True, "shop_sign_key": "sign_k70bank"}},
            {"fn": "build_sidewalk_segment", "kwargs": {"name": "sw1", "location": [0, 1.2, 0], "length": 5.0, "width": 3.0}},
            {"fn": "build_crosswalk", "kwargs": {"name": "cw1", "location": [0.0, -0.3, 0], "width": 2.6}},
            {"fn": "build_traffic_light", "kwargs": {"name": "tl1", "location": [-1.4, -0.2, 0]}},
            {"fn": "build_streetlamp", "kwargs": {"name": "lamp1", "location": [1.5, 0.4, 0]}},
            {"fn": "build_bench", "kwargs": {"name": "bn1", "location": [1.0, 1.6, 0]}},
            {"fn": "build_planter", "kwargs": {"name": "pl1", "location": [-1.1, 1.5, 0]}},
            {"fn": "build_vehicle", "kwargs": {"name": "car1", "location": [1.9, -1.4, 0], "rotation_z_deg": 0, "kind": "car", "color": [0.55, 0.12, 0.12]}},
        ],
        "lighting": LIGHT,
        "camera_keyframes": [
            {"frame": 0, "location": [1.6, -7.5, 1.7], "look_at": [-0.1, 1.2, 1.0]},
            {"frame": 60, "location": [1.2, -5.0, 1.4], "look_at": [-0.2, 0.8, 0.95]},
        ],
        "lens": 62, "dof": True, "fstop": 3.2,
    }

    # ---- Shot 2: street tracking ---- #
    specs["street_tracking"] = {
        "characters": [{"role": "john", "location": [-0.3, -1.6, 0], "rotation_z_deg": 0,
                        "animation": {"type": "walk", "params": {"length": 22, "n_cycles": 3, "stride_deg": 28, "forward_dist": 3.4}}},
                       {"role": "sarah", "location": [-1.4, 2.6, 0], "rotation_z_deg": 165,
                        "animation": {"type": "walk", "params": {"length": 24, "n_cycles": 2, "stride_deg": 24, "forward_dist": -1.6}}}],
        "env_pieces": [
            {"fn": "build_distant_ground", "kwargs": {"name": "ground2", "location": [0, 0, 0], "material": "concrete"}},
            {"fn": "build_distant_skyline", "kwargs": {"name": "sky2", "location": [0, 10, 0], "n_buildings": 6, "spread": 9, "seed": 11}},
            {"fn": "build_road_segment", "kwargs": {"name": "road1", "location": [0.0, 0.5, 0], "length": 11.0, "width": 1.8}},
            {"fn": "build_sidewalk_segment", "kwargs": {"name": "sw_l", "location": [-1.5, 0.5, 0], "length": 11.0, "width": 1.0}},
            {"fn": "build_sidewalk_segment", "kwargs": {"name": "sw_r", "location": [1.5, 0.5, 0], "length": 11.0, "width": 1.0}},
            {"fn": "build_building_multistory", "kwargs": {"name": "bldg_l1", "location": [-2.6, -1.2, 0], "floors": 3, "wall_material": "brick"}},
            {"fn": "build_building_multistory", "kwargs": {"name": "bldg_l2", "location": [-2.6, 2.0, 0], "floors": 4, "wall_material": "concrete",
                                                            "ground_shop": True, "shop_sign_key": "sign_market"}},
            {"fn": "build_building_multistory", "kwargs": {"name": "bldg_r1", "location": [2.7, -0.2, 0], "floors": 4, "wall_material": "brick_dark"}},
            {"fn": "build_building_multistory", "kwargs": {"name": "bldg_r2", "location": [2.7, 2.8, 0], "floors": 3, "wall_material": "concrete",
                                                            "ground_shop": True, "shop_sign_key": "sign_office"}},
            {"fn": "build_streetlamp", "kwargs": {"name": "lamp2", "location": [-1.5, 0.9, 0]}},
            {"fn": "build_streetlamp", "kwargs": {"name": "lamp3", "location": [1.5, 3.2, 0]}},
            {"fn": "build_bench", "kwargs": {"name": "bn2", "location": [1.85, -1.6, 0]}},
            {"fn": "build_planter", "kwargs": {"name": "pl2", "location": [1.85, -0.6, 0]}},
            {"fn": "build_vehicle", "kwargs": {"name": "taxi1", "location": [2.0, 1.2, 0], "rotation_z_deg": 0, "kind": "taxi", "color": [0.85, 0.72, 0.1]}},
        ],
        "lighting": LIGHT,
        "camera_keyframes": [
            {"frame": 0, "location": [3.0, -5.6, 1.4], "look_at": [-0.3, -1.6, 0.85]},
            {"frame": 80, "location": [3.0, -1.6, 1.4], "look_at": [-0.3, 2.6, 0.85]},
        ],
        "lens": 68, "dof": True, "fstop": 2.8,
    }

    # ---- Shot 3: bank interior (recomposed) ---- #
    specs["bank_interior"] = {
        "characters": [{"role": "john", "location": [-0.55, -0.55, 0], "rotation_z_deg": 55,
                        "animation": {"type": "point", "params": {"start": 0, "length": 45}}},
                       {"role": "banker", "location": [0.15, 0.95, 0], "rotation_z_deg": -130,
                        "animation": {"type": "idle", "params": {"length": 45}}},
                       {"role": "worker", "location": [1.7, 1.3, 0], "rotation_z_deg": 180,
                        "animation": {"type": "sit", "params": {"start": 0, "length": 30}}}],
        "env_pieces": [
            {"fn": "build_wall_panel", "kwargs": {"name": "back_wall", "location": [0.0, 1.5, 0], "w": 3.6, "h": 2.4, "material": "office_surface"}},
            {"fn": "build_counter", "kwargs": {"name": "counter1", "location": [-0.2, 0.35, 0], "w": 1.7, "d": 0.6, "h": 0.95}},
            {"fn": "build_signboard", "kwargs": {"name": "banksign", "location": [-0.2, 1.36, 1.75], "sign_key": "sign_k70bank", "w": 1.1, "h": 0.4}},
            {"fn": "build_desk", "kwargs": {"name": "sidedesk", "location": [1.7, 0.75, 0]}},
            {"fn": "build_chair", "kwargs": {"name": "sidechair", "location": [1.7, 1.15, 0]}},
            {"fn": "build_laptop", "kwargs": {"name": "laptop1", "location": [1.7, 0.6, 0.79]}},
            {"fn": "build_laptop", "kwargs": {"name": "laptop2", "location": [-0.2, 0.15, 0.99]}},
            {"fn": "build_money_prop", "kwargs": {"name": "cash1", "location": [-0.55, 0.2, 0.99], "n": 3}},
            {"fn": "build_planter", "kwargs": {"name": "plint", "location": [-1.7, -0.6, 0]}},
        ],
        "lighting": {**LIGHT, "sun_energy": 3.0, "fill_color": [0.75, 0.78, 0.9]},
        "camera_keyframes": [
            {"frame": 0, "location": [3.0, -3.8, 1.5], "look_at": [-0.15, 0.4, 0.95]},
            {"frame": 55, "location": [2.6, -3.3, 1.45], "look_at": [-0.15, 0.5, 0.95]},
        ],
        "lens": 48, "dof": True, "fstop": 4.5,
    }

    # ---- Shot 4: hero ending ---- #
    specs["hero_ending"] = {
        "characters": [{"role": "john", "location": [0.2, 0.4, 0], "rotation_z_deg": -20,
                        "animation": {"type": "idle", "params": {"length": 40}}}],
        "env_pieces": [
            {"fn": "build_distant_ground", "kwargs": {"name": "ground4", "location": [0, 0, 0], "material": "grass"}},
            {"fn": "build_distant_skyline", "kwargs": {"name": "sky4", "location": [-1, 10, 0], "n_buildings": 6, "spread": 10, "seed": 21}},
            {"fn": "build_house", "kwargs": {"name": "house2", "location": [0.7, 2.8, 0], "w": 2.6, "d": 2.2, "h": 1.7}},
            {"fn": "build_road_segment", "kwargs": {"name": "road2", "location": [-1.7, 0.6, 0], "length": 6.5, "width": 1.6}},
            {"fn": "build_sidewalk_segment", "kwargs": {"name": "sw4", "location": [0.4, 0.3, 0], "length": 5.5, "width": 1.4}},
            {"fn": "build_streetlamp", "kwargs": {"name": "lamp4", "location": [-1.0, -0.8, 0]}},
            {"fn": "build_tree", "kwargs": {"name": "tree3", "location": [2.6, -1.0, 0]}},
            {"fn": "build_tree", "kwargs": {"name": "tree4", "location": [-3.0, 1.8, 0]}},
            {"fn": "build_fence_segment", "kwargs": {"name": "fence1", "location": [0.7, 1.6, 0], "length": 2.0}},
            {"fn": "build_bench", "kwargs": {"name": "bn4", "location": [-1.4, 0.2, 0]}},
        ],
        "lighting": LIGHT_GOLDEN,
        "camera_keyframes": [
            {"frame": 0, "location": [-1.1, -3.0, 1.3], "look_at": [0.2, 1.0, 0.9]},
            {"frame": 55, "location": [-2.6, -6.6, 1.6], "look_at": [0.3, 1.3, 0.95]},
        ],
        "lens": 62, "dof": True, "fstop": 2.4,
    }

    return specs


def main():
    t0 = time.time()
    print("K70 VOXEL V3.1 -- premium polish benchmark")
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

    # comparison_sheet: OLD V3 vs NEW V3.1, one representative frame each
    v3_dir = ROOT / "data" / "jobs" / "k70_voxel_v3_benchmark" / "shots"
    v3_frames = {
        "city/exit": v3_dir / "exit_house" / "frame_005.png",
        "street": v3_dir / "street_walk" / "frame_006.png",
        "bank": v3_dir / "bank_interior" / "frame_005.png",
        "hero": v3_dir / "cinematic_close" / "frame_005.png",
    }
    v31_mid_frames = {}
    for sid in order:
        frame_dir = SHOTS_DIR / sid
        frames = sorted(frame_dir.glob("frame_*.png"))
        if frames:
            v31_mid_frames[sid] = frames[len(frames) // 2]

    comp_w, comp_h = 260, 462
    comp_sheet = Image.new("RGB", (comp_w * 4, comp_h * 2 + 40), (12, 12, 15))
    v3_order = ["city/exit", "street", "bank", "hero"]
    for i, key in enumerate(v3_order):
        p = v3_frames[key]
        if p.exists():
            comp_sheet.paste(Image.open(p).resize((comp_w, comp_h)), (i * comp_w, 20))
    for i, sid in enumerate(order):
        p = v31_mid_frames.get(sid)
        if p and p.exists():
            comp_sheet.paste(Image.open(p).resize((comp_w, comp_h)), (i * comp_w, comp_h + 20))
    comp_sheet.save(JOB_DIR / "comparison_sheet.jpg", quality=92)
    print("  [comparison] row 1 = OLD V3, row 2 = NEW V3.1 (same shot order)")

    total_build_time = round(time.time() - t0, 1)
    dur_actual = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)],
                                capture_output=True, text=True).stdout.strip()
    metadata = {
        "title": "K70 Voxel V3.1 -- Premium Polish Benchmark",
        "resolution": f"{W}x{H}", "fps": FPS,
        "duration_sec": float(dur_actual) if dur_actual else None,
        "shots": [{"id": s["id"], "duration_sec": s["duration"]} for s in SHOTS],
        "v3_to_v31_changes": {
            "lighting": "setup_block_world_v31() -- flat procedural sky (NO HDRI photo as world "
                        "background anymore), warm sun + cool fill + rim light",
            "environment": "_k70_block_kit.py +11 new builders: multistory buildings w/ shopfronts+"
                          "signage, traffic lights, benches, bins, fences, planters, crosswalks, "
                          "vehicles, distant block skyline, extended block-textured ground",
            "materials": "+4 variant textures (brick_dark, wood_dark, road_worn, glass_tint) + 6 "
                        "original K70 signage textures (K70 BANK, CAFE, OFFICE, MARKET, BUS STOP, "
                        "street sign)",
            "character": "John's texture atlas enhanced: eye highlight pixel, 2-stage cheek/jaw "
                        "shading, arched eyebrows, alternating shirt highlight/shadow fabric bands, "
                        "pants weave variation, shoe tread + toe highlight",
            "npcs": "4 new roles (sarah, banker, investor, worker) via the SAME V3 character rig "
                   "script -- zero code changes needed there since it already takes role generically",
            "bank_shot": "recomposed: 3/4 camera angle showing John AND the Banker NPC, both faces "
                        "readable, background Worker NPC seated at a side desk for depth",
        },
        "untouched": "_voxel_human_script.py (Day 06's character system), Day 06 videos, the 9-mode "
                    "specialized master, Synfig/Natron/Krita/Pencil2D pipelines, Clay, Isometric, "
                    "Thomas Rig -- none of these were modified",
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
