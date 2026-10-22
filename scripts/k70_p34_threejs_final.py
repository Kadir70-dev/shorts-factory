#!/usr/bin/env python3
"""P3.4: validate staged final-quality Three.js batches and build the P3.4 graph.

Rendering itself stays in `scripts/k70_p0_threejs_restore.py --quality final`.
This tool only READS batch folders and writes a NEW graph:

  validate  per batch: resolution, duration (±1 frame), black/flat frames, and
            structural match against the validated 360x640 preview of the same
            seed/template (SSIM after downscale) — labels, coastlines and
            borders must land where they did in the preview.
  build     copy the P3.3 graph, repoint ONLY the 20 Three.js asset paths to
            validated final clips, and assert every other field is unchanged.

  .venv/bin/python scripts/k70_p34_threejs_final.py validate \
      --graph data/finance_p33/bitcoin_release_v1/scene_graph_p33.json \
      --batch data/finance_p34/threejs_final/batch_1
  .venv/bin/python scripts/k70_p34_threejs_final.py build \
      --graph data/finance_p33/bitcoin_release_v1/scene_graph_p33.json \
      --manifest data/finance_p34/threejs_final/validation_manifest.json \
      --out data/finance_p34/bitcoin_final_v1
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W, H = 1080, 1920
SSIM_MIN = 0.95          # same scene ≈0.99; a different globe scene ≈0.82
BLACK_YAVG = 16.0        # mean luma below this is a black frame
FLAT_RANGE = 2.0         # per-frame luma range below this is a broken/flat frame


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=width,height,nb_read_frames,codec_name:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    s = data["streams"][0]
    return {"width": s["width"], "height": s["height"], "frames": int(s["nb_read_frames"]),
            "codec": s["codec_name"], "duration_sec": float(data["format"]["duration"])}


def _frame_stats(path: Path) -> list[tuple[float, float]]:
    """(YAVG, YMAX-YMIN) for every frame, via ffmpeg signalstats."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf",
         "signalstats,metadata=print:file=-", "-f", "null", "-"],
        capture_output=True, text=True, check=True).stdout
    avg = [float(x) for x in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", out)]
    lo = [float(x) for x in re.findall(r"lavfi\.signalstats\.YMIN=([\d.]+)", out)]
    hi = [float(x) for x in re.findall(r"lavfi\.signalstats\.YMAX=([\d.]+)", out)]
    return [(a, h - l) for a, l, h in zip(avg, lo, hi)]


def _ssim(final: Path, preview: Path) -> float:
    """Mean SSIM of the final clip downscaled to the preview's 360x640 grid."""
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(final), "-i", str(preview), "-filter_complex",
         "[0:v]scale=360:640:flags=area,setpts=PTS-STARTPTS[a];"
         "[1:v]scale=360:640,setpts=PTS-STARTPTS[b];[a][b]ssim", "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.search(r"SSIM .*All:([\d.]+)", out.stderr)
    return float(m.group(1)) if m else 0.0


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_clip(scene: dict, final: Path, preview: Path, fps: int) -> dict:
    probe = _probe(final)
    stats = _frame_stats(final)
    expected = float(scene["duration_sec"])
    checks = {
        "resolution": probe["width"] == W and probe["height"] == H,
        "duration": abs(probe["duration_sec"] - expected) <= 1.0 / fps + 1e-3,
        "frames_decoded": len(stats) == probe["frames"] and probe["frames"] > 0,
        "no_black_frames": all(a >= BLACK_YAVG for a, _ in stats),
        "no_flat_frames": all(r >= FLAT_RANGE for _, r in stats),
    }
    ssim = _ssim(final, preview)
    checks["matches_preview_structure"] = ssim >= SSIM_MIN
    return {"scene_id": scene["id"], "clip": str(final), "sha256": _sha(final),
            "preview": str(preview), "expected_sec": expected, "probe": probe,
            "min_yavg": round(min(a for a, _ in stats), 1) if stats else None,
            "ssim_vs_preview": round(ssim, 4), "checks": checks,
            "passed": all(checks.values())}


def cmd_validate(args) -> int:
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    scenes = {s["id"]: s for s in graph["scenes"] if s["visual"]["type"] == "threejs"}
    report_file = args.batch / "threejs_restore_report.json"
    report = json.loads(report_file.read_text(encoding="utf-8"))
    results = []
    for row in report["scenes"]:
        sid = row["scene_id"]
        if sid not in scenes:
            raise SystemExit(f"{sid} is not a Three.js scene in the P3.3 graph")
        final = (ROOT / row["clip"]).resolve() if not Path(row["clip"]).is_absolute() else Path(row["clip"])
        preview = Path(scenes[sid]["visual"]["asset_path"])
        res = validate_clip(scenes[sid], final, preview, int(graph.get("fps", 30)))
        res["render_status"] = row["status"]
        res["checks"]["render_report_ok"] = row["status"] in ("rendered", "cache_hit") and not row["error"]
        res["passed"] = all(res["checks"].values())
        results.append(res)
        print(f"{sid}: {'PASS' if res['passed'] else 'FAIL'} ssim={res['ssim_vs_preview']} "
              f"dur={res['probe']['duration_sec']:.3f}/{res['expected_sec']} min_yavg={res['min_yavg']}")
    (args.batch / "validation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0 if all(r["passed"] for r in results) else 2


def build_graph(source: dict, manifest: dict) -> dict:
    graph = copy.deepcopy(source)
    want = {s["id"] for s in graph["scenes"] if s["visual"]["type"] == "threejs"}
    clips = {r["scene_id"]: r for r in manifest["clips"] if r["passed"]}
    if set(clips) != want:
        raise ValueError(f"need 20 validated clips; missing {sorted(want - set(clips))}")
    for scene in graph["scenes"]:
        if scene["id"] in clips:
            path = Path(clips[scene["id"]]["clip"])
            if not path.is_file() or _sha(path) != clips[scene["id"]]["sha256"]:
                raise ValueError(f"{scene['id']}: validated clip changed or missing")
            scene["visual"]["asset_path"] = str(path)
            scene["visual"]["decision_reason"] = "[P3.4] validated final-quality 1080x1920 Three.js render"
    # Only the Three.js asset_path / decision_reason may differ.
    for a, b in zip(source["scenes"], graph["scenes"]):
        va, vb = dict(a["visual"]), dict(b["visual"])
        if a["id"] in want:
            for k in ("asset_path", "decision_reason"):
                va.pop(k, None)
                vb.pop(k, None)
        if {**a, "visual": va} != {**b, "visual": vb}:
            raise AssertionError(f"{a['id']}: unexpected change")
    for key in set(source) | set(graph):
        if key != "scenes" and source.get(key) != graph.get(key):
            raise AssertionError(f"top-level {key} changed")
    return graph


def cmd_build(args) -> int:
    source = json.loads(args.graph.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / "data"):
        raise SystemExit("--out must be under data/")
    target = out / "scene_graph_p34.json"
    if target.exists():
        raise SystemExit(f"{target} exists; refusing to overwrite")
    graph = build_graph(source, manifest)
    out.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {target}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="K70 P3.4 Three.js final-quality validation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--graph", type=Path, required=True)
    v.add_argument("--batch", type=Path, required=True)
    b = sub.add_parser("build")
    b.add_argument("--graph", type=Path, required=True)
    b.add_argument("--manifest", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    raise SystemExit(cmd_validate(args) if args.cmd == "validate" else cmd_build(args))


if __name__ == "__main__":
    main()
