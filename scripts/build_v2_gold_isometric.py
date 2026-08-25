#!/usr/bin/env python3
"""K70 Visual Engine V2 -- gold-standard benchmark for Style 6 (Isometric
Miniature World). BuildingNodes (Durman/BuildingNodes) was downloaded and
inspected but NOT adopted -- its own README requires 3 manual GUI steps
with no bundled example/preset .blend to script against, which risked an
open-ended undocumented-internals debugging session (the Thomas Rig
precedent). Per the brief's own 10-minute anti-bug-loop rule this was
recognized quickly and the reliable beveled-box technique used instead. See
_isometric_miniature_script.py for the full integration note and the two
real bugs found/fixed while building this (money-flow objects doubling
their offset, then scaling around world origin instead of their own
center).

    .venv-win/Scripts/python.exe scripts/build_v2_gold_isometric.py
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
SCRIPT = ROOT / "tools/k70_scene_engine/blender/_isometric_miniature_script.py"

JOB_DIR = ROOT / "data" / "jobs" / "k70_v2_gold_isometric"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24


def main() -> None:
    t0 = time.time()
    print("K70 V2 GOLD -- Style 6: Isometric Miniature World")

    spec = {
        "entities": [
            {"name": "employer", "kind": "employer", "location": [-1.6, 1.2, 0]},
            {"name": "worker", "kind": "worker", "location": [-1.6, -0.6, 0]},
            {"name": "bank", "kind": "bank", "location": [0.2, 1.2, 0]},
            {"name": "business", "kind": "business", "location": [1.8, -0.4, 0]},
            {"name": "investor", "kind": "investor", "location": [0.2, -1.4, 0]},
            {"name": "house", "kind": "house", "location": [-0.2, -2.6, 0]},
        ],
        "roads": [[-1.6, 0.6, -1.6, -0.2], [-1.0, 1.2, -0.2, 1.2], [0.2, 0.6, 0.2, -0.6],
                 [0.2, -0.9, 0.2, -1.0], [-0.2, -1.8, -0.2, -2.2]],
        "flows": [
            {"from": [-1.6, 1.5, 0.3], "to": [-1.6, -0.3, 0.15], "f_start": 4, "f_end": 26,
             "color": [0.75, 0.6, 0.2]},
            {"from": [-1.6, -0.3, 0.15], "to": [0.2, 1.0, 0.4], "f_start": 30, "f_end": 52,
             "color": [0.2, 0.55, 0.28]},
            {"from": [0.2, 1.0, 0.4], "to": [0.2, -1.2, 0.65], "f_start": 56, "f_end": 78,
             "color": [0.55, 0.42, 0.8]},
        ],
        "lighting_preset": "exterior_day", "hdri_strength": 1.0,
        "yaw_deg": 40, "ortho_scale": 6.3, "look_at": [0, -0.4, 0.2],
        "orbit_deg": 22,
        "n_frames": 24, "frame_range": [0, 82],
        "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 24, "width": W, "height": H,
                  "output_dir": str(SHOTS_DIR / "economy")},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        args_path = f.name
    proc = subprocess.run(
        [str(BLENDER), "--background", "--python", str(SCRIPT), "--", args_path],
        capture_output=True, text=True, timeout=900,
    )
    Path(args_path).unlink(missing_ok=True)
    if "K70_ISOMETRIC_RENDER_OK" not in proc.stdout:
        raise RuntimeError(f"isometric render failed:\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print("  [economy] rendered ->", SHOTS_DIR / "economy")

    fps = spec["n_frames"] / 11.0
    clip = SHOTS_DIR / "economy.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(SHOTS_DIR / "economy" / "frame_%03d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", str(clip)],
        capture_output=True, text=True, check=True,
    )
    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(clip), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    from PIL import Image
    frame_files = sorted((SHOTS_DIR / "economy").glob("frame_*.png"))
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
        "style": "isometric_miniature",
        "renderer": "Blender 4.2.4 LTS (EEVEE_NEXT), new K70 isometric economy system "
                   "(_isometric_miniature_script.py, built this pass)",
        "tools_used": [
            "Blender 4.2.4 LTS (portable, vendored) -- true orthographic isometric camera",
            "New K70 beveled-box building system (6 distinct entity silhouettes: "
            "employer/worker/bank/business/investor/house)",
            "Real Poly Haven HDRI: hausdorf_clear_sky_2k.hdr (exterior_day preset)",
        ],
        "source_assets": {"hdri": "tools/k70_scene_engine/vendor/polyhaven_hdri/hausdorf_clear_sky_2k.hdr"},
        "licenses": {"blender": "GPL (output not restricted)", "polyhaven_hdri": "CC0"},
        "render_time_sec": render_time_sec,
        "resolution": f"{W}x{H}",
        "fps": FPS,
        "duration_sec": float(dur) if dur else None,
        "buildingnodes_evaluation": {
            "attempted": True,
            "outcome": "NOT ADOPTED -- downloaded v1.0.2 release, inspected the "
                      "3225-line addon source. Its own README requires 3 manual "
                      "GUI steps (hand-model a panel, hand-build a style in its "
                      "custom node editor, hand-model a base mesh) with NO bundled "
                      "example/preset .blend in the release -- no scriptable "
                      "one-liner exists. Recognized as a Thomas-Rig-class risk "
                      "within the 10-minute budget and deliberately not pursued.",
        },
        "known_defects": [
            "Real bug found and fixed during testing: money-flow objects initially "
            "rendered invisible/off-frame because _beveled_box left the object "
            "pivot at world origin after transform_apply, so scale keyframes (the "
            "pop-in/out beat) scaled the object toward (0,0,0) instead of in place "
            "-- confirmed via a bound-box-center diagnostic. Fixed at the root by "
            "re-centering each object's origin to its own geometry right after "
            "creation (bpy.ops.object.origin_set), confirmed via a zoomed-in "
            "single-frame render showing the money block correctly mid-flight.",
            "Money blocks are still visually small against the building scale at "
            "full-shot framing -- readable on close inspection but not a bold, "
            "unmissable visual beat; a documentary cut would likely want a closer "
            "insert shot for the money-movement beats specifically.",
            "Only 3 of many possible flows animated (employer->worker->bank->"
            "business); the brief's fuller ambition (mortgages, inflation, supply "
            "chains, taxes, insurance) is not attempted in this benchmark.",
            "No BuildingNodes integration -- entities are simple beveled-box "
            "silhouettes with per-kind accent shapes, not detailed procedural "
            "architecture.",
        ],
        "production_status": "PARTIAL -- core isometric camera, entity silhouettes, "
                             "and money-flow choreography all work and are bug-fixed, "
                             "but this is a first render of a brand-new system with "
                             "only one composition tested, and BuildingNodes (the "
                             "brief's named tool for this style) was not integrated.",
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Render time: {render_time_sec}s")


if __name__ == "__main__":
    main()
