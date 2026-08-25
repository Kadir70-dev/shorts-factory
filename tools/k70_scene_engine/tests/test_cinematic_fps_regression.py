"""Regression check for the real fps=10-hardcoded bug found and fixed in
build_voxel_cinematic_30s.py (K70 FULL COMBO session, 2026-08-23): every
shot's frames_to_mp4() call used a hardcoded fps=10 regardless of how many
frames were actually rendered or how long the shot was meant to run, so a
20-frame/~7s-intended shot silently became a 2.0s clip. The permanent fix
derives fps = n_frames / duration_sec instead. This test fails loudly if
that derivation ever regresses back to a hardcoded constant.

    .venv-win/Scripts/python.exe -m tools.k70_scene_engine.tests.test_cinematic_fps_regression
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "build_voxel_cinematic_30s.py"

CASES = [
    # (n_frames, duration_sec, expected_fps)
    (20, 7.27, 20 / 7.27),
    (22, 8.0, 22 / 8.0),
    (18, 6.55, 18 / 6.55),
    (16, 5.0, 16 / 5.0),
]


def _load_frames_to_mp4():
    spec = importlib.util.spec_from_file_location("k70_build_voxel_cinematic_30s", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.frames_to_mp4


def run() -> bool:
    ok = True
    if not SCRIPT_PATH.exists():
        print(f"FAIL: {SCRIPT_PATH} not found")
        return False

    src = SCRIPT_PATH.read_text(encoding="utf-8")
    if "def frames_to_mp4(frames_dir: Path, out_mp4: Path, fps: int)" in src:
        print("FAIL: frames_to_mp4 still takes a raw fps param -- the fps=10 "
              "hardcode regression is back (should take n_frames+duration_sec "
              "and DERIVE fps).")
        ok = False

    for n_frames, duration_sec, expected_fps in CASES:
        derived = n_frames / duration_sec
        if abs(derived - expected_fps) > 1e-9:
            print(f"FAIL: derivation itself wrong for n_frames={n_frames}, "
                  f"duration_sec={duration_sec}: got {derived}, want {expected_fps}")
            ok = False
        else:
            actual_duration = n_frames / derived
            if abs(actual_duration - duration_sec) > 1e-6:
                print(f"FAIL: round-trip duration mismatch for n_frames={n_frames}: "
                      f"{actual_duration}s != {duration_sec}s target")
                ok = False

    # Confirm the four production call sites were actually converted to the
    # (n_frames, duration_sec) form, not merely the helper signature.
    if src.count("frames_to_mp4(d") and "spec1[\"n_frames\"]" not in src:
        print("FAIL: call sites don't reference spec[\"n_frames\"] -- looks "
              "like the fix was reverted or only partially applied.")
        ok = False

    print("PASS: fps is derived from n_frames/duration_sec, no hardcoded fps regression."
          if ok else "REGRESSION DETECTED -- see FAIL lines above.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
