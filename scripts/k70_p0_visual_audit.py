"""P0 pre-render visual readiness + optional actual-video freeze/darkness audit.

Read-only by default. No npm install, no paid APIs, no file mutations.
Examples:
    python3 scripts/k70_p0_visual_audit.py --graph data/series/bitcoin_history/ep01/scene_graph.json
    python3 scripts/k70_p0_visual_audit.py --graph data/jobs/ID/scene_graph.json --video data/jobs/ID/final.mp4
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))
from tools.finance_cinematic_cpu.p0 import timeline_report


def _which_node() -> Path | None:
    found = shutil.which("node")
    if found:
        return Path(found)
    base = Path.home() / ".nvm" / "versions" / "node"
    if base.is_dir():
        for directory in sorted(base.iterdir(), reverse=True):
            path = directory / "bin" / "node"
            if path.is_file():
                return path
    return None


def threejs_readiness(project_root: Path) -> dict:
    """Inspect installed packages without installing or launching a renderer."""
    app = Path(project_root) / "apps" / "remotion"
    node = _which_node()
    packages = {name: (app / "node_modules" / name / "package.json").is_file()
                for name in ("three", "puppeteer", "typescript")}
    compiler = (app / "node_modules" / ".bin" / "tsc").is_file()
    ready = bool(node and compiler and all(packages.values()))
    return {
        "node": str(node) if node else None,
        "tsc_installed": compiler,
        "packages": packages,
        "dependency_preflight_passed": ready,
        "browser_launch": "not_checked",
        "worker_typescript_compile": "not_checked",
        "fix_if_missing": ("After current production ends, run: cd apps/remotion && npm ci "
                           "&& npm run threejs:build"),
    }


def _scene_at(graph, t: float):
    offset = 0.0
    for scene in graph.scenes:
        offset += float(scene.duration_sec)
        if t < offset:
            return scene
    return graph.scenes[-1] if graph.scenes else None


def video_static_audit(graph, mp4: Path) -> dict:
    """Actual decoded-media scan. FFmpeg CPU-heavy; run only with --video."""
    if not Path(mp4).is_file():
        raise FileNotFoundError(mp4)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(mp4)],
        check=True, capture_output=True, text=True, timeout=30)
    info = json.loads(probe.stdout)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    # A single decode pass reports both darkness and static intervals.
    scan = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-v", "info", "-i", str(mp4),
         "-an", "-vf",
         "blackdetect=d=0.3:pix_th=0.07,freezedetect=n=-55dB:d=1.0",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800, check=False)
    if scan.returncode:
        raise RuntimeError("FFmpeg visual scan failed: " + scan.stderr[-700:])
    black = [{"start_sec": float(a), "end_sec": float(b)}
             for a, b in re.findall(
                 r"black_start:\s*([0-9.]+)\s+black_end:\s*([0-9.]+)",
                 scan.stderr)]
    freezes = []
    for m in re.finditer(
            r"freeze_start:\s*([0-9.]+).*?freeze_end:\s*([0-9.]+).*?"
            r"freeze_duration:\s*([0-9.]+)", scan.stderr, re.S):
        start, end, seconds = (float(m.group(i)) for i in (1, 2, 3))
        scene = _scene_at(graph, start)
        freezes.append({"start_sec": start, "end_sec": end,
                        "duration_sec": seconds,
                        "scene_id": scene.id if scene else None,
                        "visual_type": scene.visual.type if scene else None})
    # Do not call all static shots errors: a deliberate archival still is valid.
    # Only genuine ~1+ second freezes on motion graphics need immediate review.
    bad = [x for x in freezes if x["duration_sec"] >= 1.0 and
           x["visual_type"] == "motion_gfx"]
    return {
        "video": str(mp4.resolve()),
        "duration_sec": float(info.get("format", {}).get("duration", 0)),
        "width": video.get("width"), "height": video.get("height"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "black_intervals": black[:80],
        "freeze_intervals": freezes[:80],
        "motion_card_freezes_over_1s": bad[:40],
        "motion_card_static_pass": not bad,
        "warning": "Freeze/black filters are diagnostic; review scene transitions and intentional stills."
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="K70 P0 read-only visual QA/readiness audit")
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--video", type=Path, default=None,
                        help="Optional existing finished MP4, decoded for freeze/darkness analysis")
    parser.add_argument("--report", type=Path, default=None,
                        help="Optional NEW JSON report path (never overwrite)")
    parser.add_argument("--strict", action="store_true",
                        help="Nonzero exit when planned 3D lacks dependencies or cards freeze")
    args = parser.parse_args()
    from app.schemas.scene import SceneGraph
    graph = SceneGraph.model_validate_json(args.graph.read_text(encoding="utf-8"))
    mix = timeline_report(graph)
    three = threejs_readiness(ROOT)
    planned_3d = mix["allocated_channels"].get("threejs", 0)
    result = {
        "mode": "read_only",
        "graph": str(args.graph.resolve()),
        "timeline": mix,
        "planned_threejs_scenes": planned_3d,
        "threejs_readiness": three,
        "source_media": {
            "voiceover_file_exists": bool(graph.audio.voiceover_path and
                                          Path(graph.audio.voiceover_path).is_file()),
            "available_visual_files": sum(bool(s.visual.asset_path and
                                               Path(s.visual.asset_path).is_file())
                                          for s in graph.scenes),
        },
    }
    if args.video:
        result["decoded_video_qa"] = video_static_audit(graph, args.video)
    print(json.dumps(result, indent=2))
    if args.report:
        target = args.report.resolve()
        if target.exists():
            parser.error("--report destination already exists; not overwriting")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.strict and ((planned_3d and not three["dependency_preflight_passed"]) or
                        (args.video and not result["decoded_video_qa"]["motion_card_static_pass"])):
        sys.exit(2)


if __name__ == "__main__":
    main()
