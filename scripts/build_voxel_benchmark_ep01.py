#!/usr/bin/env python3
"""K70 VOXEL CHARACTER BENCHMARK EP01 -- 15-20s premium stylized voxel
human benchmark. Direct build (no shorts-factory voice/QA pipeline --
this is a fast visual-only benchmark for manual approval before any
scaling to long-form).

    .venv-win/Scripts/python.exe scripts/build_voxel_benchmark_ep01.py
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
SCRIPT = ROOT / "tools/k70_scene_engine/blender/_voxel_human_script.py"

JOB_DIR = ROOT / "data" / "jobs" / "k70_voxel_character_benchmark_ep01"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24
STOCK_HOUSE = ROOT / "data" / "cache" / "f81a04784a281539938f601559af7aba6df704d2.mp4"


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


def frames_to_mp4(frames_dir: Path, out_mp4: Path, fps: int) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    return out_mp4


def render_engine():
    return {"engine": "BLENDER_EEVEE_NEXT", "samples": 32, "width": W, "height": H}


def main() -> None:
    print("K70 VOXEL BENCHMARK EP01 -- building shots")
    clips = []

    # -------------------------------------------------------------- #
    # Shot 1: real house exterior (reused stock footage, ~2.2s)
    # -------------------------------------------------------------- #
    shot1 = SHOTS_DIR / "shot1_house_stock.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(STOCK_HOUSE), "-t", "2.2",
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
         "-an", "-pix_fmt", "yuv420p", str(shot1)],
        capture_output=True, text=True, check=True,
    )
    clips.append(shot1)
    print("  [shot1] real house stock footage")

    # -------------------------------------------------------------- #
    # Shot 2: voxel John walks toward the house (~2.3s)
    # -------------------------------------------------------------- #
    spec2 = {
        "scene_type": "house", "house_location": [0, 2.6, 0], "house_scale": 1.0,
        "characters": [{
            "role": "john", "location": [0, -2.6, 0], "rotation_z_deg": 0,
            "animation": {"type": "walk", "params": {"length": 22, "n_cycles": 3, "stride_deg": 28, "forward_dist": 2.2}},
        }],
        "camera": {"location": [-5.5, -3.2, 1.6], "look_at": [0, -0.5, 0.85]},
        "lens": 32, "n_frames": 20,
        "frame_range": [0, 66],
        "render": render_engine(),
    }
    d2 = render_blender(spec2, "shot2_john_walk")
    shot2 = frames_to_mp4(d2, SHOTS_DIR / "shot2_john_walk.mp4", 10)
    clips.append(shot2)

    # -------------------------------------------------------------- #
    # Shot 3: close/medium John, idle (~1.6s)
    # -------------------------------------------------------------- #
    spec3 = {
        "scene_type": "plain",
        "characters": [{
            "role": "john", "location": [0, 0, 0], "rotation_z_deg": -18,
            "animation": {"type": "idle", "params": {"length": 48}},
        }],
        "camera": {"location": [1.6, -3.3, 1.15], "look_at": [0, 0, 0.95]},
        "lens": 50, "dof": True, "fstop": 2.8, "n_frames": 16,
        "frame_range": [0, 48],
        "render": render_engine(),
    }
    d3 = render_blender(spec3, "shot3_john_closeup")
    shot3 = frames_to_mp4(d3, SHOTS_DIR / "shot3_john_closeup.mp4", 10)
    clips.append(shot3)

    # -------------------------------------------------------------- #
    # Shots 4-6: office, John + Banker, Banker gestures (~2.8s)
    # -------------------------------------------------------------- #
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
        "render": render_engine(),
    }
    d456 = render_blender(spec456, "shot456_office")
    shot456 = frames_to_mp4(d456, SHOTS_DIR / "shot456_office.mp4", 10)
    clips.append(shot456)

    # -------------------------------------------------------------- #
    # Shot 7: $500k -> $50k -> $450k breakdown (PIL cards, ~3.6s)
    # -------------------------------------------------------------- #
    shot7 = build_chart_cards()
    clips.append(shot7)

    # -------------------------------------------------------------- #
    # Shot 8: cinematic ending, John + house (~2.2s)
    # -------------------------------------------------------------- #
    spec8 = {
        "scene_type": "house", "house_location": [0, 2.3, 0], "house_scale": 1.0,
        "characters": [{
            "role": "john", "location": [0, -1.0, 0], "rotation_z_deg": -25,
            "animation": {"type": "idle", "params": {"length": 50}},
        }],
        "camera": {"location": [-3.8, -4.5, 1.6], "look_at": [0, 0.6, 0.85]},
        "lens": 32, "dof": True, "fstop": 2.8, "n_frames": 16,
        "frame_range": [0, 50],
        "sun_rotation": [1.0, 0, 1.0], "sky_color": [0.75, 0.68, 0.55], "sky_strength": 1.1,
        "render": render_engine(),
    }
    d8 = render_blender(spec8, "shot8_ending")
    shot8 = frames_to_mp4(d8, SHOTS_DIR / "shot8_ending.mp4", 8)
    clips.append(shot8)

    # -------------------------------------------------------------- #
    # Assemble final.mp4
    # -------------------------------------------------------------- #
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


def build_chart_cards() -> Path:
    from PIL import Image, ImageDraw, ImageFont

    cards = [
        ("$500,000", "HOME PRICE", (0.35, 0.55, 0.95)),
        ("$50,000", "DOWN PAYMENT (10%)", (0.95, 0.75, 0.20)),
        ("$450,000", "MORTGAGE LOAN", (0.35, 0.85, 0.55)),
    ]
    try:
        font_big = ImageFont.truetype("arialbd.ttf", 140)
        font_small = ImageFont.truetype("arialbd.ttf", 46)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    frame_paths = []
    out_dir = SHOTS_DIR / "shot7_chart"
    out_dir.mkdir(exist_ok=True)
    for i, (value, label, color) in enumerate(cards):
        img = Image.new("RGB", (W, H), (12, 14, 20))
        draw = ImageDraw.Draw(img)
        c = tuple(int(x * 255) for x in color)
        bbox = draw.textbbox((0, 0), value, font=font_big)
        vw, vh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((W - vw) / 2, H / 2 - vh - 20), value, font=font_big, fill=c)
        bbox2 = draw.textbbox((0, 0), label, font=font_small)
        lw = bbox2[2] - bbox2[0]
        draw.text(((W - lw) / 2, H / 2 + 60), label, font=font_small, fill=(230, 230, 235))
        if i > 0:
            draw.polygon([(W / 2 - 25, H / 2 - vh - 90), (W / 2 + 25, H / 2 - vh - 90), (W / 2, H / 2 - vh - 40)],
                        fill=(180, 180, 190))
        p = out_dir / f"card_{i}.png"
        img.save(p)
        frame_paths.append(p)

    out_mp4 = SHOTS_DIR / "shot7_chart.mp4"
    inputs = []
    for p in frame_paths:
        inputs += ["-loop", "1", "-t", "1.2", "-i", str(p)]
    filter_str = "".join(f"[{i}:v]" for i in range(len(frame_paths))) + f"concat=n={len(frame_paths)}:v=1:a=0[outv]"
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", filter_str, "-map", "[outv]",
         "-pix_fmt", "yuv420p", "-r", str(FPS), str(out_mp4)],
        capture_output=True, text=True, check=True,
    )
    return out_mp4


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

    cols = 3
    rows = (len(thumbs) + cols - 1) // cols
    tw, th = 480, 270
    sheet = Image.new("RGB", (tw * cols, th * rows), (20, 20, 20))
    for i, im in enumerate(thumbs):
        im = im.resize((tw, th))
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
    sheet.save(out_path, quality=90)


if __name__ == "__main__":
    main()
