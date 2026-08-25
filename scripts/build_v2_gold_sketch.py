#!/usr/bin/env python3
"""K70 Visual Engine V2 -- gold-standard benchmark for Style 7 (Hand-Drawn
/ Sketch Documentary). Pencil2D/OpenToonz/Krita were license-audited but
none has a reliable headless automation surface (see
V2_LICENSE_MANIFEST.md). Per the brief's own "choose the smallest
reliable automation stack" and this session's style-over-repository
priority, this uses Blender's native Grease Pencil directly: real text
converted to GP strokes, revealed progressively via the native Build
modifier -- the brief's own test case ($10,000 x 8% = $800 vs $100,000 x
8% = $8,000), drawn in as if by hand. See _sketch_script.py for two real
bugs found and fixed while building this (fill rendering as undifferentiated
blobs -- switched to stroke-only line art; and text initially invisible/
flat because it wasn't rotated to match this session's camera convention).

    .venv-win/Scripts/python.exe scripts/build_v2_gold_sketch.py
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
SCRIPT = ROOT / "tools/k70_scene_engine/blender/_sketch_script.py"

JOB_DIR = ROOT / "data" / "jobs" / "k70_v2_gold_sketch"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24


def main() -> None:
    t0 = time.time()
    print("K70 V2 GOLD -- Style 7: Hand-Drawn / Sketch Documentary")

    spec = {
        "lines": [
            {"text": "$10,000 x 8% = $800", "y": 0.6, "size": 0.42, "f_start": 2, "f_end": 34},
            {"text": "$100,000 x 8% = $8,000", "y": -0.6, "size": 0.42, "f_start": 38, "f_end": 70},
        ],
        "ortho_scale": 6.4,
        "n_frames": 22, "frame_range": [0, 74],
        "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 32, "width": W, "height": H,
                  "output_dir": str(SHOTS_DIR / "formula")},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=900,
    )
    Path(args_path).unlink(missing_ok=True)
    if "K70_SKETCH_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"sketch render failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print("  [formula] rendered ->", SHOTS_DIR / "formula")

    fps = spec["n_frames"] / 10.0
    clip = SHOTS_DIR / "formula.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(SHOTS_DIR / "formula" / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(clip)],
        capture_output=True, text=True, check=True,
    )
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(clip), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    from PIL import Image
    frame_files = sorted((SHOTS_DIR / "formula").glob("frame_*.png"))
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
        "style": "sketch_handdrawn",
        "renderer": "Blender 4.2.4 LTS (EEVEE_NEXT), native Grease Pencil "
                   "(_sketch_script.py, built this pass)",
        "tools_used": [
            "Blender 4.2.4 LTS (portable, vendored) -- real text converted to "
            "Grease Pencil strokes (object.convert(target='GPENCIL')), revealed "
            "progressively via the native GP_BUILD modifier",
        ],
        "pencil2d_opentoonz_krita_evaluation": {
            "attempted": False,
            "reason": "All three were license-audited (Pencil2D GPL-2.0 weakest "
                     "automation surface; OpenToonz BSD-3-Clause core but a real "
                     "thirdparty-brush caveat in its own LICENSE.txt; Krita GUI-"
                     "first, no headless render loop). Per the brief's own "
                     "'smallest reliable automation stack' instruction and this "
                     "session's style-over-repository priority, used Blender's "
                     "native Grease Pencil instead -- a real, dedicated NPR tool, "
                     "not an approximation.",
        },
        "source_assets": {},
        "licenses": {"blender": "GPL (output not restricted)"},
        "render_time_sec": render_time_sec,
        "resolution": f"{W}x{H}",
        "fps": FPS,
        "duration_sec": float(dur) if dur else None,
        "brief_test_case": "$10,000 x 8% = $800  vs  $100,000 x 8% = $8,000 -- "
                           "both lines drawn in progressively, confirmed via a "
                           "mid-build smoke-test frame showing partially-revealed "
                           "letterforms before this final render.",
        "known_defects": [
            "Real bug found and fixed: with GP fill enabled and a thick stroke "
            "width, converted letterforms rendered as undifferentiated black "
            "blobs (fill did not correctly handle inner counter-shapes, e.g. the "
            "hole in '0', via this conversion path). Fixed by using stroke-only "
            "line art at a modest width -- also the more correct look for a "
            "hand-drawn sketch regardless.",
            "Real bug found and fixed: text was initially invisible/collapsed "
            "into flat horizontal lines because Blender text objects are "
            "authored in the XY plane while this session's camera convention "
            "(shapes face camera in the XZ plane, camera looks along +Y) was "
            "applied to every other style but missed here at first -- confirmed "
            "via a render showing only thin horizontal segments, no glyphs. "
            "Fixed by rotating the text object 90deg at creation, matching every "
            "other flat-shape script this session.",
            "Line art only, no hand-drawn wobble/jitter modifier applied (a "
            "cleaner 'technical sketch' look rather than a loose hand style) -- "
            "a real stylistic choice under time constraints, not attempted "
            "further.",
        ],
        "production_status": "WORKING -- both real bugs found during testing were "
                             "root-caused and fixed, and the progressive draw-in "
                             "(the brief's specific requirement for this style) is "
                             "confirmed via a real GP_BUILD modifier, not simulated.",
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Render time: {render_time_sec}s")


if __name__ == "__main__":
    main()
