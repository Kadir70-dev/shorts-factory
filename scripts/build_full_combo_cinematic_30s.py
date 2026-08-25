#!/usr/bin/env python3
"""K70 FULL COMBO PREMIUM CINEMATIC VOXEL -- 30-second story proof.

Combines, inside the SAME shots (not isolated demos):
  - K70 custom voxel characters (idle/walk/sit/point/sit_point actions)
  - Real Poly Haven CC0 furniture (gltf, physically placed: desk, chair,
    laptop, lamp, clock, cash register, shelf, sofa, cabinet)
  - Real CC0Tree CC0 vegetation (fbx trees, street + house exterior)
  - Real bene-proggen-maps Procgen Maps city (verified headless this
    session: 226 buildings/2858 props/309 signs) as a distant skyline
    layer behind the hand-authored midground street buildings
  - K70 Voxelizer-style finance objects (beveled-box bills/coins/savings
    pillar) physically choreographed in-scene (shot 4)
  - Real stock footage (via app.pipeline.broll) as a brief reality cutaway
  - Real HDRI lighting (Poly Haven, via lighting_presets.py)

fps is DERIVED from n_frames/duration per shot (no hardcoded fps bug --
see the permanent fix applied to build_voxel_cinematic_30s.py too).

    .venv-win/Scripts/python.exe scripts/build_full_combo_cinematic_30s.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
SCRIPT = ROOT / "tools/k70_scene_engine/blender/_voxel_human_script.py"
PROCGEN_CITY_BLEND = ROOT / "tools/k70_voxel_v2/renders/procgen_test_city.blend"

JOB_DIR = ROOT / "data" / "jobs" / "k70_full_combo_cinematic_30s"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24


def render_blender(spec: dict, tag: str, timeout: int = 900) -> Path:
    out_dir = SHOTS_DIR / tag
    spec["render"]["output_dir"] = str(out_dir)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=timeout,
    )
    Path(args_path).unlink(missing_ok=True)
    if "K70_VOXEL_HUMAN_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"shot {tag} failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print(f"  [{tag}] rendered -> {out_dir}")
    return out_dir


def frames_to_mp4(frames_dir: Path, out_mp4: Path, n_frames: int, duration_sec: float) -> Path:
    fps = n_frames / duration_sec
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    return out_mp4


def eng(samples=26):
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": samples, "width": W, "height": H}


async def fetch_real_footage(duration_sec: float) -> tuple[Path, bool]:
    """Returns (path, is_video). Pexels/Pixabay video first (same
    real-footage pipeline that supplied ~23% of the earlier longform
    video); falls back to a real photo (Ken-Burns-able) if no video
    clip clears the search, so shot 5 never silently goes missing."""
    from app.pipeline import broll
    terms = ["american city downtown financial district", "US city skyline street"]
    path = await broll._video(terms, duration_sec, 0, query_text="",
                              rank_key="k70_full_combo_cinematic_30s:shot5")
    if path is not None:
        return Path(path), True
    path = await broll._image(terms, 0, query_text="",
                              rank_key="k70_full_combo_cinematic_30s:shot5_img")
    if path is None:
        raise RuntimeError("no real footage/image resolved for shot 5")
    return Path(path), False


def main() -> None:
    print("K70 FULL COMBO PREMIUM CINEMATIC VOXEL -- 30s sequence")
    clips: list[tuple[Path, float]] = []  # (clip_path, duration_sec) already correct duration

    # ------------------------------------------------------------ #
    # SHOT 1 (5.0s): apartment -- John leaves for work, real Poly
    # Haven sofa/cabinet/clock, golden-hour dolly-in.
    # ------------------------------------------------------------ #
    spec1 = {
        "scene_type": "apartment",
        "lighting_preset": "golden_hour", "hdri_strength": 0.55,
        "characters": [{
            "role": "john", "location": [0, -0.3, 0], "rotation_z_deg": -30,
            "animation": {"type": "idle", "params": {"length": 50}},
        }],
        "camera_keyframes": [
            {"frame": 0, "location": [2.6, -3.0, 1.7], "look_at": [0.2, -0.3, 1.1]},
            {"frame": 50, "location": [1.3, -1.7, 1.3], "look_at": [0.0, -0.2, 0.95]},
        ],
        "dof": True, "fstop": 1.8, "lens": 40,
        "n_frames": 15, "frame_range": [0, 50],
        "render": eng(),
    }
    d1 = render_blender(spec1, "shot1_apartment")
    c1 = frames_to_mp4(d1, SHOTS_DIR / "shot1_apartment.mp4", spec1["n_frames"], 5.0)
    clips.append((c1, 5.0))

    # ------------------------------------------------------------ #
    # SHOT 2 (6.0s): street -- John walks a populated Procgen-backed
    # city block, CC0Tree trees, bank facade foreshadowed ahead.
    # ------------------------------------------------------------ #
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
        "show_bank_facade": True,
        "procgen_city_blend": str(PROCGEN_CITY_BLEND),
        "procgen_location": [0, 34, 0], "procgen_rotation_deg": 0,
        "procgen_scale": 0.10, "procgen_max_buildings": 24,
        "n_frames": 16, "frame_range": [0, 72],
        "render": eng(),
    }
    d2 = render_blender(spec2, "shot2_street", timeout=900)
    c2 = frames_to_mp4(d2, SHOTS_DIR / "shot2_street.mp4", spec2["n_frames"], 6.0)
    clips.append((c2, 6.0))

    # ------------------------------------------------------------ #
    # SHOT 3 (6.0s): bank interior -- John + Banker (sit + gesture),
    # real Poly Haven desk/chair/laptop/lamp/register/shelf, orbit.
    # ------------------------------------------------------------ #
    spec3 = {
        "scene_type": "bank",
        "lighting_preset": "office_interior", "hdri_strength": 0.7,
        "characters": [
            {"role": "john", "location": [-0.55, -0.6, 0], "rotation_z_deg": 15,
             "animation": {"type": "idle", "params": {"length": 55}}},
            {"role": "banker", "location": [0.55, 1.55, 0], "rotation_z_deg": 200,
             "animation": {"type": "sit_point", "params": {"length": 55}}},
        ],
        "camera_keyframes": [
            {"frame": 0, "location": [3.0, -3.2, 1.6], "look_at": [0.1, 0.7, 0.95]},
            {"frame": 55, "location": [-2.2, -3.0, 1.7], "look_at": [0.0, 0.7, 0.95]},
        ],
        "dof": True, "fstop": 2.8, "lens": 32,
        "n_frames": 16, "frame_range": [0, 55],
        "render": eng(),
    }
    d3 = render_blender(spec3, "shot3_bank")
    c3 = frames_to_mp4(d3, SHOTS_DIR / "shot3_bank.mp4", spec3["n_frames"], 6.0)
    clips.append((c3, 6.0))

    # ------------------------------------------------------------ #
    # SHOT 4 (5.0s): physical finance storytelling -- salary lands,
    # bills fly off, remainder becomes a visibly growing savings
    # pillar. K70 Voxelizer-style objects, staged in-scene.
    # ------------------------------------------------------------ #
    spec4 = {
        "scene_type": "finance_transform",
        "lighting_preset": "portrait_studio", "hdri_strength": 0.9,
        "characters": [],
        "finance_stage": {"f_in": 6, "f_split": 16, "f_grow": 28, "n_salary": 9, "n_bills": 3},
        "camera_keyframes": [
            {"frame": 0, "location": [1.9, -2.0, 1.1], "look_at": [-0.2, 0.5, 0.35]},
            {"frame": 28, "location": [1.3, -1.5, 1.0], "look_at": [-0.4, 0.5, 0.5]},
        ],
        "dof": True, "fstop": 2.2, "lens": 45,
        "n_frames": 15, "frame_range": [0, 28],
        "render": eng(),
    }
    d4 = render_blender(spec4, "shot4_finance")
    c4 = frames_to_mp4(d4, SHOTS_DIR / "shot4_finance.mp4", spec4["n_frames"], 5.0)
    clips.append((c4, 5.0))

    # ------------------------------------------------------------ #
    # SHOT 5 (3.0s): real stock footage -- reality cutaway grounding
    # the story in the actual US economy/city world.
    # ------------------------------------------------------------ #
    raw_stock, is_video = asyncio.run(fetch_real_footage(3.0))
    c5 = SHOTS_DIR / "shot5_stock.mp4"
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if is_video:
        cmd = ["ffmpeg", "-y", "-i", str(raw_stock), "-t", "3.0", "-vf", vf,
              "-pix_fmt", "yuv420p", "-an", str(c5)]
    else:
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(raw_stock), "-t", "3.0",
              "-vf", vf + ",zoompan=z='min(zoom+0.0015,1.08)':d=125:s=1920x1080",
              "-pix_fmt", "yuv420p", "-r", "24", str(c5)]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    clips.append((c5, 3.0))
    print(f"  [shot5_stock] real {'footage' if is_video else 'photo (ken burns)'} -> {raw_stock}")

    # ------------------------------------------------------------ #
    # SHOT 6 (5.0s): house ending -- John reaches the house he's
    # building toward, golden-hour pull-back reveal.
    # ------------------------------------------------------------ #
    spec6 = {
        "scene_type": "house", "house_location": [0, 2.3, 0], "house_scale": 1.0,
        "lighting_preset": "golden_hour", "hdri_strength": 1.0,
        "characters": [{
            "role": "john", "location": [0, -1.0, 0], "rotation_z_deg": -25,
            "animation": {"type": "idle", "params": {"length": 50}},
        }],
        "camera_keyframes": [
            {"frame": 0, "location": [-2.6, -3.2, 1.4], "look_at": [0, 0.3, 0.9]},
            {"frame": 50, "location": [-5.2, -6.5, 2.0], "look_at": [0, 0.7, 1.0]},
        ],
        "dof": True, "fstop": 2.5, "lens": 35,
        "n_frames": 15, "frame_range": [0, 50],
        "render": eng(),
    }
    d6 = render_blender(spec6, "shot6_house")
    c6 = frames_to_mp4(d6, SHOTS_DIR / "shot6_house.mp4", spec6["n_frames"], 5.0)
    clips.append((c6, 5.0))

    # ------------------------------------------------------------ #
    # Assemble
    # ------------------------------------------------------------ #
    concat_list = JOB_DIR / "concat.txt"
    concat_list.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c, _ in clips), encoding="utf-8")
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(final_mp4)],
        capture_output=True, text=True, check=True,
    )
    total_dur = sum(d for _, d in clips)
    print(f"\nFINAL VIDEO: {final_mp4} (~{total_dur:.1f}s target)")

    build_contact_sheet([c for c, _ in clips], JOB_DIR / "contact_sheet.jpg")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")


def build_contact_sheet(clips: list[Path], out_path: Path) -> None:
    from PIL import Image
    import subprocess as sp

    thumbs = []
    for i, clip in enumerate(clips):
        thumb_path = SHOTS_DIR / f"thumb_{i}.jpg"
        sp.run(["ffmpeg", "-y", "-i", str(clip), "-vf", "select=eq(n\\,3)", "-vframes", "1", str(thumb_path)],
              capture_output=True, text=True)
        if not thumb_path.exists():
            sp.run(["ffmpeg", "-y", "-i", str(clip), "-vframes", "1", str(thumb_path)],
                  capture_output=True, text=True)
        thumbs.append(Image.open(thumb_path))

    cols = 3
    rows = (len(thumbs) + cols - 1) // cols
    tw, th = 480, 270
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        im = im.resize((tw, th))
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
    sheet.save(out_path, quality=92)


if __name__ == "__main__":
    main()
