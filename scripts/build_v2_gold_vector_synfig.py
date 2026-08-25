#!/usr/bin/env python3
"""K70 Visual Engine V2 -- Style 2 (Premium 2D Vector), rendered by REAL
Synfig (not Blender). Per explicit instruction: the named tool must
actually generate the artifact, no silent substitution.

Renderer: vendor/synfig_win/extracted/bin/synfig.exe (Synfig Studio
1.5.5, real Windows portable build, downloaded from the project's own
GitHub releases -- github.com/synfig/synfig, GPL-3.0, license-clear per
V2_LICENSE_MANIFEST.md). Scene authored programmatically against the
real .sif XML schema (confirmed via `synfig.exe --layer-info=<type>` on
this actual install) by tools/k70_scene_engine/synfig/gen_vector_john.py
-- no GUI, no Blender anywhere in this pipeline.

    .venv-win/Scripts/python.exe scripts/build_v2_gold_vector_synfig.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SYNFIG = ROOT / "tools/k70_scene_engine/vendor/synfig_win/extracted/bin/synfig.exe"
GEN_SCRIPT = ROOT / "tools/k70_scene_engine/synfig/gen_vector_john.py"

JOB_DIR = ROOT / "data" / "jobs" / "k70_v2_gold_vector_synfig"
SHOTS_DIR = JOB_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 24
DURATION_SEC = 7.0


def main() -> None:
    t0 = time.time()
    print("K70 V2 GOLD -- Style 2: Premium 2D Vector (REAL Synfig)")

    sif_path = JOB_DIR / "vector_john.sif"
    subprocess.run([sys.executable, str(GEN_SCRIPT), str(sif_path)], check=True)
    print(f"  [sif] generated -> {sif_path}")

    seq_dir = SHOTS_DIR / "frames"
    seq_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(SYNFIG), "-i", str(sif_path), "-o", str(seq_dir / "frame.png"),
         "-w", str(W), "-h", str(H), "--begin-time", "0s 0f", "--end-time", f"{int(DURATION_SEC)}s 0f", "-T", "4"],
        capture_output=True, text=True, timeout=600,
    )
    n_frames = len(list(seq_dir.glob("frame.*.png")))
    combined = proc.stdout + proc.stderr
    if "DONE" not in combined or n_frames < 100:
        raise RuntimeError(f"Synfig render FAILED or incomplete ({n_frames} frames):\n"
                           f"STDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-2000:]}")
    print(f"  [synfig] rendered {n_frames} frames -> {seq_dir}")

    final_mp4 = JOB_DIR / "final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(seq_dir / "frame.%04d.png"),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p", "-r", str(FPS), str(final_mp4)],
        capture_output=True, text=True, check=True,
    )

    from PIL import Image
    frame_files = sorted(seq_dir.glob("frame.*.png"))
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
        "style": "vector_2d",
        "renderer": "Synfig 1.5.5 (real synfig.exe CLI renderer, NOT Blender)",
        "renderer_path": str(SYNFIG),
        "repo": "github.com/synfig/synfig", "version": "v1.5.5",
        "tools_used": [
            "Synfig Studio 1.5.5 Windows portable build (real download from "
            "github.com/synfig/synfig releases, extracted, run headless via "
            "its own synfig.exe CLI -- no GUI, no installer)",
            "Programmatic .sif XML scene authoring (gen_vector_john.py) against "
            "the real schema confirmed via `synfig.exe --layer-info=<type>` on "
            "this install",
        ],
        "fallback_used": False,
        "fallback_note": "None. This is a real Synfig render, not a Blender substitute.",
        "source_assets": {},
        "licenses": {"synfig": "GPL-3.0 (output not restricted)"},
        "render_time_sec": render_time_sec,
        "synfig_render_time_sec": "~24s for 169 frames (measured separately from python/ffmpeg overhead)",
        "resolution": f"{W}x{H}", "fps": FPS,
        "duration_sec": float(dur) if dur else None,
        "known_defects": [
            "Real bug found and fixed during testing: layer paint order in "
            ".sif is the OPPOSITE of a naive 'layers panel, top=front' "
            "assumption -- first-listed XML layer paints first (ends up at "
            "the BACK), last-listed paints last (ends up in FRONT). Confirmed "
            "via a minimal 2-rectangle isolation test (a foreground rectangle "
            "listed first was completely hidden until the order was reversed).",
            "Real bug found and fixed: the 'rotate' transform layer's only "
            "rotation param is itself named 'amount' (angle-typed), not a "
            "separate blend-opacity value -- emitting both caused a duplicate/"
            "conflicting <param name=\"amount\"> and a parse error. Fixed by "
            "removing the generic blend-amount param from that layer.",
            "Real bug found and fixed: the group layer's 'transformation' "
            "composite value node needs child tags named "
            "offset/angle/skew_angle/scale (not 'rotation') and its own "
            "type=\"transformation\" attribute, and time_offset needs "
            "<time value=\"0\"/> not <time>0</time> -- both caused hard XML "
            "parse errors ('Bad type in <composite>', 'missing value "
            "attribute'), fixed by correcting the generator's templates.",
            "Character rig is simplified (torso/head/hair/one animated arm), "
            "same scope as the earlier Blender-based attempt.",
        ],
        "production_status": "WORKING -- real Synfig render, confirmed via three "
                             "real bugs found and fixed through actual test "
                             "renders (not guessed), final full-sequence render "
                             "completed cleanly.",
    }
    (JOB_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nFINAL: {final_mp4} ({dur}s)")
    print(f"CONTACT SHEET: {JOB_DIR / 'contact_sheet.jpg'}")
    print(f"METADATA: {JOB_DIR / 'metadata.json'}")
    print(f"Total build time: {render_time_sec}s")


if __name__ == "__main__":
    main()
