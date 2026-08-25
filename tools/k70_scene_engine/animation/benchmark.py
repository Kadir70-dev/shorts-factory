from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from ..blender.bpy_bridge import find_blender
from .mesh2motion_adapter import HUMAN_BASE

SCRIPT = Path(__file__).with_name("_benchmark_blender.py")
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "benchmarks" / "local_animation_stack"


def _ffmpeg() -> Path:
    candidates = list((ROOT / "tools/k70_scene_engine/vendor/natron_win/extracted").rglob("ffmpeg.exe"))
    candidates.append(ROOT / "tools/k70_scene_engine/vendor/synfig_win/extracted/bin/ffmpeg.exe")
    return next((p for p in candidates if p.exists()), Path("ffmpeg"))


def run_one(kind: str, *, force: bool = False) -> dict:
    out = OUT / f"test_{kind.lower()}"; frames = out / "frames"; out.mkdir(parents=True, exist_ok=True)
    spec = {"benchmark": kind, "mesh2motion_human": str(HUMAN_BASE.resolve()),
            "frames_dir": str(frames.resolve()), "blend_path": str((out / "scene.blend").resolve()),
            "result_json": str((out / "structural.json").resolve())}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f); arg = f.name
    started = time.perf_counter()
    structural = out / "structural.json"
    if force or not structural.exists() or len(list(frames.glob("frame_*.png"))) < 48:
        proc = subprocess.run([str(find_blender()), "--background", "--python", str(SCRIPT), "--", arg],
                              capture_output=True, text=True, timeout=1200)
    else:
        proc = subprocess.CompletedProcess([], 0, "K70_LOCAL_ANIMATION_BENCHMARK_OK", "")
    Path(arg).unlink(missing_ok=True)
    if "K70_LOCAL_ANIMATION_BENCHMARK_OK" not in proc.stdout:
        raise RuntimeError(proc.stdout[-4000:] + "\n" + proc.stderr[-3000:])
    clip = out / "benchmark.mp4"
    ff = subprocess.run([str(_ffmpeg()), "-y", "-framerate", "12", "-i", str(frames / "frame_%04d.png"),
                         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
                        capture_output=True, text=True)
    if ff.returncode or not clip.exists(): raise RuntimeError(ff.stderr[-2000:])
    result = json.loads((out / "structural.json").read_text(encoding="utf-8"))
    result.update({"clip": str(clip), "seconds": round(time.perf_counter() - started, 3)})
    return result


def run_all() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {kind: run_one(kind) for kind in ("A", "B", "C")}
    path = OUT / "benchmark_report.json"; path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2))
