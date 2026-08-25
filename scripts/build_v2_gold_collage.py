#!/usr/bin/env python3
"""K70 Visual Engine V2 -- gold-standard benchmark for Style 3 (Paper-Cut /
Editorial Collage). Krita (GPL-3.0, license-clear) was the brief's named
tool but is GUI-first with no headless render loop (flagged in
V2_LICENSE_MANIFEST.md before this style was attempted). Per this
session's explicit "the STYLE must work, a particular repository does
not have to," this builds the look directly in Blender: flat paper-grain
cutouts at distinct Z-depths with a real perspective-camera dolly for
parallax. See _paper_collage_script.py for the one real framing issue
found and fixed while building this (an over-aggressive camera push-in
that ended in an unreadable extreme close-up).

    .venv-win/Scripts/python.exe scripts/build_v2_gold_collage.py
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

BLENDER = ROOT / "tools/k70_scene_engine/.blender_portable/blender-4.2.4-windows-x64/blender.exe"
SCRIPT = ROOT / "tools/k70_scene_engine/blender/_paper_collage_script.py"

JOB_DIR = ROOT / "data" / "jobs" / "k70_v2_gold_collage"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24


def main() -> None:
    t0 = time.time()
    print("K70 V2 GOLD -- Style 3: Paper-Cut / Editorial Collage")

    spec = {
        "stage": {"f_bills": 10, "f_doc": 26, "f_house": 44},
        "camera_keyframes": [
            {"frame": 0, "location": [0.4, -2.6, 1.6], "look_at": [-0.1, 1.5, 1.0]},
            {"frame": 60, "location": [0.0, -1.9, 1.35], "look_at": [-0.1, 1.3, 0.95]},
        ],
        "lens": 45, "fstop": 2.2,
        "n_frames": 22, "frame_range": [0, 60],
        "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 32, "width": W, "height": H,
                  "output_dir": str(SHOTS_DIR / "editorial")},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=900,
    )
    Path(args_path).unlink(missing_ok=True)
    if "K70_PAPER_COLLAGE_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"collage render failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print("  [editorial] rendered ->", SHOTS_DIR / "editorial")

    fps = spec["n_frames"] / 10.0
    clip = SHOTS_DIR / "editorial.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(SHOTS_DIR / "editorial" / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(clip)],
        capture_output=True, text=True, check=True,
    )
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(clip), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    from PIL import Image
    frame_files = sorted((SHOTS_DIR / "editorial").glob("frame_*.png"))
    pick_idx = [0, len(frame_files) // 3, 2 * len(frame_files) // 3, len(frame_files) - 1]
    thumbs = [Image.open(frame_files[i]).resize((480, 270)) for i in pick_idx]
    sheet = Image.new("RGB", (480 * 2, 270 * 2), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % 2) * 480, (i // 2) * 270))
    sheet.save(JOB_DIR / "contact_sheet.jpg", quality=92)

    render_time_sec = round(time.time() - t0, 1)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)],
                         capture_output=True, text=True).stdout.strip()

    metadata = {
        "style": "paper_collage",
        "renderer": "Blender 4.2.4 LTS (EEVEE_NEXT), new K70 paper-cutout system "
                   "(_paper_collage_script.py, built this pass)",
        "tools_used": [
            "Blender 4.2.4 LTS (portable, vendored) -- flat cutout planes with a "
            "noise-driven paper-grain material, perspective camera dolly for "
            "genuine parallax through Z-depth layers",
        ],
        "krita_natron_evaluation": {
            "attempted": False,
            "reason": "Krita is GUI-first with no headless render loop (flagged in "
                     "V2_LICENSE_MANIFEST.md); Natron has a real CLI renderer but "
                     "is a compositor, not a layer-art authoring tool, so it doesn't "
                     "replace the Krita step this style's paper art would need. "
                     "Built directly in Blender per this session's explicit "
                     "style-over-repository priority.",
        },
        "source_assets": {},
        "licenses": {"blender": "GPL (output not restricted)"},
        "render_time_sec": render_time_sec,
        "resolution": f"{W}x{H}",
        "fps": FPS,
        "duration_sec": float(dur) if dur else None,
        "known_defects": [
            "Real framing bug found and fixed: the initial camera push-in ended in "
            "an extreme, unreadable close-up (confirmed via a 4-frame test render -- "
            "the final frame showed only two flat color fields with no readable "
            "composition). Fixed by pulling the ending camera position back to a "
            "distance that keeps all 5 collage elements (map/news/doc/house/bills) "
            "in frame throughout.",
            "Cutout edges are clean die-cut rectangles/bevels, not the more textured "
            "hand-torn-paper edge a premium version might want (noted as a future "
            "improvement, not attempted this pass).",
            "Money bills are small and appear briefly near the bottom of frame -- "
            "a documentary cut would likely want a dedicated closer beat for them.",
        ],
        "production_status": "WORKING -- the one real defect found (camera framing) "
                             "was fixed and confirmed via a clean re-render showing "
                             "all elements, real parallax depth, and readable paper "
                             "grain texture before this final render.",
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Render time: {render_time_sec}s")


if __name__ == "__main__":
    main()
