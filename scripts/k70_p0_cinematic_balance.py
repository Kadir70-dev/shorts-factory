"""P0.2: distribute 6-8 F1/F2 cinematic clips across a FINISHED documentary.

F4 put all six clips in the first 240 s of a 657 s film: F2 ranked by score and
the only AI stills that existed were for the opening. This script:

  1. works on the job's REAL (voiced) timing, never the authored estimates;
  2. re-uses F3's safety filter and P0 `spread_items` to choose stills over the
     whole timeline, recovering existing stills and generating only missing ones
     with the FREE provider (Pollinations); `--no-generate` stays offline;
  3. runs F2 `select_scenes(balanced=True)` and F1 `auto_apply` for the clips;
  4. copies ONLY the selected scenes' visuals onto a graph copy. Narration,
     overlays, charts, data and every other scene are byte-identical to input.

Nothing is composed. The job directory and its final.mp4 are never written.

    .venv/bin/python scripts/k70_p0_cinematic_balance.py \
        --job data/jobs/k70_f4_bitcoin_ep01 \
        --authored data/series/bitcoin_history/ep01_f4/scene_graph.json \
        --missing data/series/bitcoin_history/ep01/assets/missing_ai_images.json \
        --base-graph data/finance_p0/threejs_restore/scene_graph_p0_threejs.json \
        --out data/finance_p0/cinematic_balanced
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from tools.finance_cinematic_cpu.auto import auto_apply, select_scenes  # noqa: E402
from tools.finance_cinematic_cpu.p0 import spread_items  # noqa: E402
from tools.finance_cinematic_cpu.stills import (eligible, graph_with_stills,  # noqa: E402
                                                load_missing, resolve_stills)


def mmss(sec: float) -> str:
    return f"{int(sec // 60)}:{sec % 60:04.1f}"


def ai_working_copy(graph, authored: dict, scene_ids: set[str]):
    """Copy with authored AI-still scenes re-typed so F2's filter can judge them.

    The budget re-channelled them to stock/official; F4 restored them the same
    way. The copy is only used for SELECTION; the output graph takes nothing
    from it except the scenes that actually receive a clip.
    """
    types = {s["id"]: s["visual"]["type"] for s in authored.get("scenes", [])}
    work = graph.model_copy(deep=True)
    for scene in work.scenes:
        if scene.id in scene_ids and types.get(scene.id) == "ai_image":
            v = scene.visual
            v.type, v.budget_channel, v.asset_path, v.layers = "ai_image", "ai_broll", None, []
    return work


def timeline(graph, scene_ids: list[str]) -> list[dict]:
    total = sum(s.duration_sec for s in graph.scenes)
    rows, t = [], 0.0
    for s in graph.scenes:
        if s.id in scene_ids:
            rows.append({"scene_id": s.id, "start": mmss(t), "end": mmss(t + s.duration_sec),
                         "start_sec": round(t, 2), "duration_sec": round(s.duration_sec, 2),
                         "quarter": min(4, int(t / total * 4) + 1),
                         "asset": Path(s.visual.asset_path or "").name})
        t += s.duration_sec
    return rows


def protected_unchanged(before, after, changed: set[str]) -> list[str]:
    """Scene ids whose narration/overlays/data changed, or unselected visuals that did."""
    bad = []
    for a, b in zip(before.scenes, after.scenes):
        if (a.narration, a.overlays, a.data, a.duration_sec) != \
                (b.narration, b.overlays, b.data, b.duration_sec):
            bad.append(a.id)
        elif a.id not in changed and a.visual != b.visual:
            bad.append(a.id)
    return bad


def main(argv: list[str] | None = None) -> int:
    from app.schemas.scene import SceneGraph

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--job", type=Path, required=True)
    ap.add_argument("--authored", type=Path, required=True)
    ap.add_argument("--missing", type=Path, required=True)
    ap.add_argument("--base-graph", type=Path,
                    help="graph to patch (e.g. the P0.1 3D-restored copy); default job graph")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--clips", type=int, default=8)
    ap.add_argument("--min-clips", type=int, default=6)
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("--width", type=int, default=720)
    a = ap.parse_args(argv)
    if not 1 <= a.min_clips <= a.clips <= 12:
        ap.error("need 1 <= --min-clips <= --clips <= 12")
    out = a.out.resolve()
    if out == a.job.resolve() or out.is_relative_to(a.job.resolve()):
        ap.error("--out must be outside the job directory (the job is read-only)")
    out.mkdir(parents=True, exist_ok=True)

    job_graph = SceneGraph.model_validate_json((a.job / "scene_graph.json").read_text())
    base = SceneGraph.model_validate_json((a.base_graph or a.job / "scene_graph.json").read_text())
    if [s.id for s in base.scenes] != [s.id for s in job_graph.scenes]:
        ap.error("--base-graph scene ids differ from the job")
    authored = json.loads(a.authored.read_text())
    items = load_missing(a.missing)
    # A scene already carrying a restored 3D render keeps it.
    items = [i for i in items if next(s for s in base.scenes
                                      if s.id == i["scene_id"]).visual.type != "threejs"]
    work = ai_working_copy(base, authored, {i["scene_id"] for i in items})

    ok, skipped = eligible(work, items, limit=24)        # F3 safety, real timing
    wanted = spread_items(work, ok, limit=min(a.clips, len(ok))) if ok else []
    print("[p0.2] eligible:", [i["scene_id"] for i in ok])
    print("[p0.2] balanced still batch:", [i["scene_id"] for i in wanted])
    t0 = time.monotonic()
    stills = resolve_stills(wanted, a.authored.parent, out / "stills",
                            generate=not a.no_generate)
    for r in stills:
        print(f"[p0.2] still {r.scene_id:6} {r.status:9} {r.elapsed_sec:6.1f}s {r.path or r.detail}")
    with_stills = graph_with_stills(work, stills)
    total = sum(s.duration_sec for s in work.scenes)
    report = select_scenes(with_stills, max_clips=a.clips, balanced=True,
                           spacing_sec=round(total / (a.clips * 2.5), 1))
    picked = [p["scene_id"] for p in report["selected"]]
    print("[p0.2] F2 balanced selection:", picked)
    if len(picked) < a.min_clips:
        (out / "selection_report.json").write_text(json.dumps(report, indent=2))
        print(f"[p0.2] only {len(picked)} safe clips (< {a.min_clips}); graph not written")
        return 1
    animated = auto_apply(with_stills, report, out, width=a.width, fps=base.fps,
                          cache_dir=out / "cache")
    final = base.model_copy(deep=True)
    anim = {s.id: s for s in animated.scenes}
    for scene in final.scenes:
        if scene.id in picked:
            scene.visual = anim[scene.id].visual.model_copy(deep=True)
    bad = protected_unchanged(base, final, set(picked))
    rows = timeline(final, picked)
    summary = {"job": str(a.job), "base_graph": str(a.base_graph or a.job / "scene_graph.json"),
               "stills": {s: sum(r.status == s for r in stills)
                          for s in ("recovered", "generated", "failed", "skipped")},
               "clips": len(picked), "quarters": sorted({r["quarter"] for r in rows}),
               "timeline": rows, "protected_violations": bad,
               "elapsed_sec": round(time.monotonic() - t0, 1),
               "note": "Illustrative 2.5D motion from AI stills; not archival footage."}
    (out / "selection_report.json").write_text(json.dumps(report, indent=2))
    (out / "p0_cinematic_summary.json").write_text(json.dumps(summary, indent=2))
    if bad:
        print("[p0.2] protected content changed:", bad)
        return 1
    (out / "scene_graph_p0.json").write_text(final.model_dump_json(indent=2))
    for r in rows:
        print(f"[p0.2] clip {r['scene_id']:5} {r['start']:>7} - {r['end']:>7}  Q{r['quarter']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
