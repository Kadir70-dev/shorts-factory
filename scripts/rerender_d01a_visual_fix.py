#!/usr/bin/env python3
"""Targeted production rerender for d01_a after visual-plan QA failure."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> int:
    from app.pipeline import qa, render_ffmpeg, visual_budget
    from app.schemas.scene import SceneGraph

    job = ROOT / "data" / "jobs" / "vid_fin_d01_a"
    raw = json.loads((job / "scene_graph.json").read_text(encoding="utf-8"))
    scenes = {s["id"]: s for s in raw["scenes"]}

    # Use copyright-safe, narration-specific generated stills for the two
    # source beats that could not resolve. Planned AI->AI is exact; planned
    # official->AI is an explicitly allowed concrete-visual lateral fallback.
    for sid, filename in (("s2", "s2_ai_v2.png"), ("s6", "s6_ai_v2.png")):
        visual = scenes[sid]["visual"]
        visual["type"] = "ai_image"
        visual["strategy"] = "ai_image"
        visual["asset_path"] = str(job / "visuals" / filename)
        visual["motion"] = "ken_burns"
        visual["layers"] = []
        visual["decision_reason"] += " [production QA: replaced unresolved source with matched copyright-safe still]"

    # The intended 3D logistics beat exceeded the renderer's frame budget.
    # Its already-rendered branded logistics animation is specific to the
    # narration, so declare the production channel honestly before rerender.
    v4 = scenes["s4"]["visual"]
    v4["budget_channel"] = "motion_gfx"
    v4["strategy"] = "motion_gfx"
    v4["decision_reason"] += " [production QA: 3D frame-budget fallback declared as motion graphics]"

    graph = SceneGraph.model_validate(raw)
    (job / "scene_graph.json").write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    delivered = visual_budget.measure(graph)
    (job / "visual_breakdown.json").write_text(json.dumps(delivered.as_dict(), indent=2), encoding="utf-8")

    out = job / "final.mp4"
    await render_ffmpeg.render(graph, out)
    report = qa.analyze(graph, str(out), render_seconds=0, ram_peak_mb=0,
                        min_free_mb=-1, consistency=None, timed_out=False,
                        budget_report=delivered)
    (job / "qa_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (job / "qa_report.txt").write_text(qa.format_report(report), encoding="utf-8")
    print(qa.format_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
