#!/usr/bin/env python3
"""K70 VFX Director -- 3 small benchmarks (financial_crisis, wealth_growth,
future_banking), reusing the ALREADY-RENDERED K70 Voxel V5.2 animation
test clip as the "before" footage for all three (a real compatible K70
visual-mode output, not a fresh scene built for this task -- per "reuse
existing systems, avoid unnecessary rebuilds").

Cheap LOW-quality previews are rendered and inspected FIRST; only after
a preview looks reasonable does the full HERO-quality benchmark render.

    .venv-win/Scripts/python.exe scripts/build_vfx_benchmarks.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/k70_scene_engine/vfx"))
from vfx_director import apply_vfx

BEFORE_FRAMES = ROOT / "data/jobs/k70_voxel_v52_visual_director/animation_test_frames"
JOB_DIR = ROOT / "data/jobs/k70_vfx_director_benchmarks"
# Reduced from 96 @ 24fps after a real run hung partway through the
# Natron/GMIC stage at HERO (full 1080x1920) resolution -- 16+ minutes
# with zero new frames despite the process still running. This build has
# proven fragile at scale (multiple format/exit bugs already found and
# fixed); a shorter, lower-fps clip still meets the requested 3-5s window
# while substantially cutting per-benchmark frame-processing exposure.
FPS = 12
BENCHMARK_FRAME_COUNT = 48  # 4s @ 12fps -- within the requested 3-5s window
PREVIEW_FRAME_COUNT = 8

BENCHMARKS = [
    ("financial_crisis", "financial_crisis", 0.65),
    ("wealth_growth", "wealth_growth", 0.65),
    ("future_banking", "future_banking", 0.65),
]


def build_contact_sheet(before_frame: Path, after_frame: Path, out_path: Path, label: str):
    from PIL import Image, ImageDraw
    before = Image.open(before_frame)
    after = Image.open(after_frame)
    target_h = 700
    def fit(im):
        w, h = im.size
        return im.resize((int(w * target_h / h), target_h))
    b, a = fit(before), fit(after)
    total_w = b.width + a.width + 20
    sheet = Image.new("RGB", (total_w, target_h + 40), (12, 12, 15))
    draw = ImageDraw.Draw(sheet)
    sheet.paste(b, (0, 40))
    sheet.paste(a, (b.width + 20, 40))
    draw.text((8, 10), f"{label} -- BEFORE", fill=(255, 255, 255))
    draw.text((b.width + 28, 10), f"{label} -- AFTER", fill=(255, 255, 255))
    sheet.save(out_path, quality=92)


def main():
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    report = {"benchmarks": {}}
    total_t0 = time.time()

    for name, preset, intensity in BENCHMARKS:
        print(f"\n=== {name} ===")
        bdir = JOB_DIR / name

        # ---- 1. cheap LOW-quality preview first ---- #
        preview_out = bdir / "preview"
        t0 = time.time()
        preview_result = apply_vfx(BEFORE_FRAMES, preview_out, preset=preset, intensity=intensity,
                                   scene_type="city", quality="LOW", frame_count=PREVIEW_FRAME_COUNT, fps=FPS)
        preview_time = round(time.time() - t0, 1)
        print(f"  preview done in {preview_time}s -> {preview_result['final_path']}")

        # ---- 2. full HERO-quality benchmark render ---- #
        full_out = bdir / "full"
        t1 = time.time()
        full_result = apply_vfx(BEFORE_FRAMES, full_out, preset=preset, intensity=intensity,
                                scene_type="city", quality="HERO", frame_count=BENCHMARK_FRAME_COUNT, fps=FPS)
        full_time = round(time.time() - t1, 1)
        print(f"  full benchmark done in {full_time}s -> {full_result['final_path']}")

        # ---- 3. before/after contact sheet (a representative mid-clip frame) ---- #
        mid = BENCHMARK_FRAME_COUNT // 2
        before_frame = BEFORE_FRAMES / f"frame_{mid:04d}.png"
        after_frame = Path(full_result["natron_pass_dir"]) / f"frame.{mid:04d}.png"
        sheet_path = bdir / f"{name}_before_after.jpg"
        build_contact_sheet(before_frame, after_frame, sheet_path, name)

        report["benchmarks"][name] = {
            "preset": preset, "intensity": intensity,
            "preview_time_sec": preview_time, "preview_path": preview_result["final_path"],
            "full_time_sec": full_time, "full_path": full_result["final_path"],
            "contact_sheet": str(sheet_path),
            "resolved_preset": full_result["resolved_preset"],
            "timings_detail": full_result["timings"],
        }

    report["total_time_sec"] = round(time.time() - total_t0, 1)
    (JOB_DIR / "benchmark_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nALL BENCHMARKS DONE in {report['total_time_sec']}s")
    print(f"Report: {JOB_DIR / 'benchmark_report.json'}")


if __name__ == "__main__":
    main()
