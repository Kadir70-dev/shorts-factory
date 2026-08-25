#!/usr/bin/env python3
"""One-off surgical fix: patch a single scene's resolved asset_path in an
already-rendered job's scene_graph.json, then re-render ONLY that scene's clip
(render_ffmpeg's fingerprint cache reuses every other clip unchanged) and
re-run postprocess/QA/provenance exactly like produce.py's tail does.

Used when the visual budget + asset resolver correctly picked a channel but
the actual search/rerank returned an off-topic clip for one beat — cheaper
than a full pipeline re-run when only one scene needs a different source.

    .venv/bin/python scripts/patch_scene_asset.py --job vid_fin_d04_a \
        --scene s2 --asset data/cache/<hash>.mp4 --type broll --motion ken_burns
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def run(args) -> int:
    from app.config import settings
    from app.pipeline import qa, render_ffmpeg
    from app.pipeline.qa import analyze, format_report
    from app.schemas.scene import SceneGraph

    job = settings().data_dir / "jobs" / args.job
    graph_raw = json.loads((job / "scene_graph.json").read_text(encoding="utf-8"))
    for sc in graph_raw.get("scenes", []):
        d = sc.get("duration_sec")
        if isinstance(d, (int, float)) and d < 0.8:
            sc["duration_sec"] = 0.8
    graph = SceneGraph.model_validate(graph_raw)

    scene = next(s for s in graph.scenes if s.id == args.scene)
    asset_abs = str(Path(args.asset).resolve())
    scene.visual.asset_path = asset_abs
    scene.visual.type = args.type
    scene.visual.motion = args.motion
    if scene.visual.layers:
        scene.visual.layers[0].asset_path = asset_abs
        scene.visual.layers[0].kind = "footage"

    (job / "scene_graph.json").write_text(graph.model_dump_json(indent=2),
                                          encoding="utf-8")

    # produce.py's render_backend=ffmpeg path writes DIRECTLY to final.mp4 —
    # render_ffmpeg._finish already does the loudnorm/export pass, there is no
    # separate postprocess step in this pipeline (that module is for the
    # Remotion backend / make_short.py path only).
    out_mp4 = job / "final.mp4"
    await render_ffmpeg.render(graph, out_mp4)

    rep = analyze(graph, str(out_mp4), render_seconds=0.0, ram_peak_mb=0.0,
                 min_free_mb=-1.0, consistency=None, timed_out=False)
    (job / "qa_report.json").write_text(
        json.dumps({"passed": rep.passed, "metrics": rep.metrics,
                    "checks": [c.__dict__ for c in rep.checks]}, indent=2,
                   default=str))
    (job / "qa_report.txt").write_text(format_report(rep), encoding="utf-8")
    print(format_report(rep))
    print(f"MP4: {out_mp4}")
    return 0 if rep.passed else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--asset", required=True)
    ap.add_argument("--type", default="broll")
    ap.add_argument("--motion", default="ken_burns")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
