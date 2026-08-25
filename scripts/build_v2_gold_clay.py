#!/usr/bin/env python3
"""K70 Visual Engine V2 -- gold-standard benchmark for Style 4 (Clay /
Miniature 3D). Pure Blender, no new external repository. See
_clay_miniature_script.py for the clay-material + growth-choreography
implementation and the real bug found/fixed during its own smoke testing
(floating-block staircase -> fixed to pop-in-place at true resting spot).

    .venv-win/Scripts/python.exe scripts/build_v2_gold_clay.py
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
SCRIPT = ROOT / "tools/k70_scene_engine/blender/_clay_miniature_script.py"

JOB_DIR = ROOT / "data" / "jobs" / "k70_v2_gold_clay"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24


def main() -> None:
    t0 = time.time()
    print("K70 V2 GOLD -- Style 4: Clay / Miniature 3D")

    spec = {
        "growth_stage": {"f_each": 14, "n_blocks": 5},
        "camera_keyframes": [
            {"frame": 0, "location": [1.6, -1.6, 1.0], "look_at": [0, 0, 0.28]},
            {"frame": 70, "location": [1.15, -1.25, 1.15], "look_at": [0, 0, 0.38]},
        ],
        "lens": 65, "fstop": 2.0,
        "n_frames": 22, "frame_range": [0, 70],
        "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 28, "width": W, "height": H,
                  "output_dir": str(SHOTS_DIR / "growth")},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=900,
    )
    Path(args_path).unlink(missing_ok=True)
    if "K70_CLAY_MINIATURE_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"clay render failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print("  [growth] rendered ->", SHOTS_DIR / "growth")

    fps = spec["n_frames"] / 10.0
    clip = SHOTS_DIR / "growth.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(SHOTS_DIR / "growth" / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(clip)],
        capture_output=True, text=True, check=True,
    )
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(clip), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    from PIL import Image
    frame_files = sorted((SHOTS_DIR / "growth").glob("frame_*.png"))
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
        "style": "clay_miniature",
        "renderer": "Blender 4.2.4 LTS (EEVEE_NEXT), new K70 clay-material system "
                   "(_clay_miniature_script.py, built this pass)",
        "tools_used": [
            "Blender 4.2.4 LTS (portable, vendored) -- no new external repository",
            "New K70 clay material: matte Principled BSDF + noise-driven bump for "
            "hand-worked surface imperfection (not shiny generic CGI)",
            "Stop-Motion-Blender-Addon (bkurdali) evaluated per the brief but NOT "
            "adopted -- the plain scripted squash/pop-in-place keyframe technique "
            "achieved the stop-motion feel without adding a new addon dependency",
        ],
        "source_assets": {},
        "licenses": {"blender": "GPL (output not restricted)"},
        "render_time_sec": render_time_sec,
        "resolution": f"{W}x{H}",
        "fps": FPS,
        "duration_sec": float(dur) if dur else None,
        "known_defects": [
            "Real bug found and fixed during testing: the first choreography "
            "attempt dropped each not-yet-arrived block in from high above, held "
            "via constant keyframe extrapolation -- since every future block's "
            "waiting position stayed visible for most of the timeline, this read "
            "as a broken floating staircase, not clay stop-motion. Fixed by "
            "switching to a squash-then-settle SCALE key at each block's own true "
            "resting position (pop-in-place), the same technique already proven "
            "for the voxel style's savings-pillar shot -- confirmed clean via a "
            "4-frame timeline smoke test before this final render.",
            "Single object type (stacked blocks) -- the brief's 'produces "
            "additional money blocks' beat is shown as a vertical stack only; a "
            "richer version could show blocks branching sideways into separate "
            "purchases/investments, not attempted in this pass.",
        ],
        "production_status": "PARTIAL -- material system and core choreography are "
                             "solid and bug-fixed, but this is the FIRST render of a "
                             "brand-new script (no prior track record like the voxel "
                             "style has), and only one shot/composition has been tested.",
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Render time: {render_time_sec}s")


if __name__ == "__main__":
    main()
