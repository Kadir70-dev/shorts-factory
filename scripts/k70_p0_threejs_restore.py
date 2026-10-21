"""P0.1: re-render the authored Three.js beats of a finished documentary.

The Visual Budget Manager re-channelled authored `visual.type: threejs` scenes
(official / motion_gfx / ai_broll), so their beats reached the worker as
non-candidates and the film delivered 2D cards instead. This script restores
ONLY those beats, scene by scene, through the real `threejs_engine.render()`.

Read-only for the job: the base graph, scene clips and final video are never
written. Rendered clips are copied into --out, together with a report and a
PATCHED graph copy. Nothing is composed — a documentary render needs approval.

    .venv/bin/python scripts/k70_p0_threejs_restore.py \
        --job data/jobs/k70_f4_bitcoin_ep01 \
        --authored data/series/bitcoin_history/ep01_f4/scene_graph.json \
        --out data/finance_p0/threejs_restore --quality preview
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))


def authored_threejs(authored: dict) -> dict[str, str]:
    """scene id -> the place the author named in `visual.query`."""
    return {s["id"]: (s["visual"].get("query") or "").strip()
            for s in authored.get("scenes", [])
            if s.get("visual", {}).get("type") == "threejs"}


def restore_beat(graph, scene_id: str, place: str):
    """First storyboard beat of the scene, re-marked as an explicit 3D beat.

    `location` is set to the authored place: map_template lets an explicit
    location win over prose, and the prose often names the ORIGIN of the story
    ("Dollars that flowed out into the world") rather than the subject (Japan).
    """
    if graph.storyboard is None:
        return None
    beat = next((b for b in graph.storyboard.scenes
                 if b.source_scene_id == scene_id), None)
    if beat is None:
        return None
    update = {"threejs_candidate": True, "recommended_visual_type": "threejs",
              "ai_broll_candidate": False}
    if place:
        update["location"] = place
    return beat.model_copy(update=update)


def probe(path: Path) -> dict:
    """Decoded duration/frames plus mean luma, so 'rendered' means watchable."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,nb_read_frames:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, timeout=120)
    info = json.loads(out.stdout or "{}")
    stream = (info.get("streams") or [{}])[0]
    luma = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
         "signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"],
        capture_output=True, text=True, timeout=180).stderr
    yavg = [float(line.rsplit("=", 1)[1]) for line in luma.splitlines()
            if "YAVG=" in line]
    return {"width": stream.get("width"), "height": stream.get("height"),
            "frames": int(stream.get("nb_read_frames") or 0),
            "duration_sec": round(float(info.get("format", {}).get("duration", 0)), 3),
            "mean_yavg": round(sum(yavg) / len(yavg), 1) if yavg else None,
            "yavg_range": round(max(yavg) - min(yavg), 1) if yavg else None}


async def restore(job: Path, authored_path: Path, out: Path, quality: str,
                  only: set[str]) -> dict:
    from app.pipeline import threejs_engine
    from app.schemas.scene import SceneGraph

    graph = SceneGraph.model_validate_json((job / "scene_graph.json").read_text())
    planned = authored_threejs(json.loads(authored_path.read_text()))
    if only:
        planned = {k: v for k, v in planned.items() if k in only}
    by_id = {s.id: s for s in graph.scenes}
    (out / "clips").mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        for sid, place in planned.items():
            scene = by_id.get(sid)
            beat = restore_beat(graph, sid, place) if scene else None
            row = {"scene_id": sid, "authored_place": place,
                   "delivered_before": scene.visual.type if scene else None}
            spec = threejs_engine.map_template(beat) if beat else None
            if spec is None:
                rows.append({**row, "status": "unmapped",
                             "error": "no scene/beat or no clarity template"})
                continue
            started = time.perf_counter()
            result = await threejs_engine.render(graph, scene, beat, quality=quality)
            row.update(template=result.template, label=spec.label,
                       status=result.status, error=result.error,
                       wall_sec=round(time.perf_counter() - started, 1),
                       peak_rss_mb=result.peak_rss_mb)
            if result.status in ("rendered", "cache_hit") and result.render_path:
                clip = out / "clips" / f"{sid}_threejs.mp4"
                shutil.copy2(result.render_path, clip)
                row.update(clip=str(clip), probe=probe(clip),
                           expected_sec=round(scene.duration_sec, 3))
            rows.append(row)
            print(f"[restore] {sid} {row['status']} {row.get('label', '')} "
                  f"{row.get('wall_sec', '')}s {row.get('error') or ''}", flush=True)
    finally:
        await threejs_engine.close_worker()

    ok = [r for r in rows if r["status"] in ("rendered", "cache_hit")]
    for r in ok:                                   # patched COPY, never the job
        s = by_id[r["scene_id"]]
        s.visual.type, s.visual.asset_path, s.visual.motion = "threejs", r["clip"], "none"
        s.visual.layers = []
        s.visual.decision_reason = f"[p0-restore] authored threejs → {r['template']}"
    (out / "scene_graph_p0_threejs.json").write_text(graph.model_dump_json(indent=2))
    report = {"job": str(job), "quality": quality, "planned": len(planned),
              "rendered": len(ok), "failed": [r["scene_id"] for r in rows if r not in ok],
              "scenes": rows}
    (out / "threejs_restore_report.json").write_text(json.dumps(report, indent=2))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--authored", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--quality", choices=("preview", "final"), default="preview")
    ap.add_argument("--only", default="", help="comma-separated scene ids")
    args = ap.parse_args(argv)
    if args.out.resolve() == args.job.resolve():
        ap.error("--out must differ from --job (the job is read-only)")
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    report = asyncio.run(restore(args.job, args.authored, args.out, args.quality, only))
    print(f"[restore] {report['rendered']}/{report['planned']} rendered; "
          f"failed: {report['failed'] or 'none'}")
    return 0 if report["rendered"] == report["planned"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
