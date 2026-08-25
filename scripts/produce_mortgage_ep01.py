#!/usr/bin/env python3
"""Production driver for the mortgage long-form video -- the first real
production use of tools/k70_scene_engine/ alongside the existing proven
pipeline (motiongfx/dataviz/broll/tts/render_ffmpeg), used directly rather
than through scripts/produce.py to avoid the known visual_budget.allocate()
channel-scrambling bug documented from the Forex/XAU-USD productions (every
asset here is resolved deterministically, once, by this script).

Checkpointed per brief section: voice -> assets -> render -> qa. Re-running
this script skips any stage already marked done in
data/jobs/mortgage_ep01_how_500k_mortgage_works/*.checkpoint.

    .venv-win/Scripts/python.exe scripts/produce_mortgage_ep01.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))

JOB_ID = "mortgage_ep01_how_500k_mortgage_works"
JOB_DIR = ROOT / "data" / "jobs" / JOB_ID
SPEC_DIR = ROOT / "data" / "series" / "mortgage_explainer" / "ep01"


async def main() -> None:
    import yaml, os
    preset = yaml.safe_load((ROOT / "config" / "presets" / "documentary_finance.yaml").read_text())
    for k, v in (preset.get("env") or {}).items():
        os.environ[k] = str(v)

    from app.brand.manager import theme_for
    from app.pipeline import motiongfx, dataviz, render_ffmpeg, qa, visual_budget, broll
    from app.pipeline.util import ffprobe_duration, ffmpeg_concat_audio, normalize_narration_joins
    from app.schemas.scene import SceneGraph
    from app.voice.manager import VoiceManager

    from tools.k70_scene_engine.blender import bpy_bridge, voxelizer
    from tools.k70_scene_engine.characters.roster import get as get_character
    from tools.k70_scene_engine.checkpoint.pipeline_checkpoint import PipelineCheckpoint
    from tools.k70_scene_engine.qa.validators import validate_still

    JOB_DIR.mkdir(parents=True, exist_ok=True)
    visuals_dir = JOB_DIR / "visuals"
    visuals_dir.mkdir(exist_ok=True)
    ckpt = PipelineCheckpoint(JOB_DIR)

    graph_path = JOB_DIR / "scene_graph.json"
    if not graph_path.exists():
        graph_path.write_text((SPEC_DIR / "scene_graph.json").read_text(encoding="utf-8"),
                              encoding="utf-8")
    def load_graph() -> SceneGraph:
        # Measured TTS duration can exceed the Director-estimate schema
        # ceiling (le=12.0) on long beats -- clamp for validation, then
        # restore the true measured value via plain attribute assignment
        # (no validate_assignment on this model), same pattern used for
        # the Forex/XAU-USD remediation.
        raw = json.loads(graph_path.read_text(encoding="utf-8"))
        overflow = {}
        for sc in raw["scenes"]:
            if sc["duration_sec"] > 12.0:
                overflow[sc["id"]] = sc["duration_sec"]
                sc["duration_sec"] = 12.0
        g = SceneGraph.model_validate(raw)
        gb = {s.id: s for s in g.scenes}
        for sid, real_dur in overflow.items():
            gb[sid].duration_sec = real_dur
        return g

    graph = load_graph()
    by_id = {s.id: s for s in graph.scenes}
    asset_plan = {a["scene_id"]: a for a in
                 json.loads((SPEC_DIR / "asset_plan.json").read_text(encoding="utf-8"))}

    def save_graph():
        graph_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")

    # ---------------------------------------------------------------- #
    # STAGE: voice
    # ---------------------------------------------------------------- #
    if not ckpt.done("voice"):
        voice = VoiceManager()
        voice.require_voice()
        vo_dir = JOB_DIR / "vo"
        vo_dir.mkdir(exist_ok=True)
        clips = []
        for scene in graph.scenes:
            out = vo_dir / f"{scene.id}.wav"
            if not out.exists():
                await voice.synthesize(scene.narration, out)
            scene.duration_sec = round(ffprobe_duration(out), 3)
            clips.append(out.resolve())
        # Build the master narration track and wire it into the graph --
        # render_ffmpeg._finish() reads graph.audio.voiceover_path directly;
        # skipping this step produces a fully-composited but SILENT video
        # (caught here after it happened once -- see FINAL_REPORT addendum).
        normalize_narration_joins(clips)
        master = (vo_dir / "voiceover.wav").resolve()
        ffmpeg_concat_audio(clips, master)
        graph.audio.voiceover_path = str(master)
        save_graph()
        total = sum(s.duration_sec for s in graph.scenes)
        ckpt.mark_done("voice", {"total_narration_s": round(total, 1)})
        print(f"[voice] done, total narration {total:.1f}s")
    else:
        print("[voice] skipped (checkpointed)")

    # ---------------------------------------------------------------- #
    # STAGE: assets
    # ---------------------------------------------------------------- #
    if not ckpt.done("asset_resolution"):
        theme = theme_for(graph, "compositor")
        rejected_from_scene_engine: list[str] = []

        for scene in graph.scenes:
            plan = asset_plan[scene.id]
            vis = plan["vis"]

            if vis == "mgfx":
                out = visuals_dir / f"{scene.id}_mgfx.mp4"
                if not out.exists():
                    await motiongfx.kinetic(theme, out, graph.width, graph.height, graph.fps,
                                            scene.duration_sec, headline=scene.visual.query,
                                            seed=int(scene.id[1:]))
                scene.visual.asset_path = str(out.resolve())
                scene.visual.layers = []

            elif vis == "chart":
                out = visuals_dir / f"{scene.id}_chart.mp4"
                if not out.exists():
                    await dataviz.render(scene.data, theme, out, graph.width, graph.height,
                                         graph.fps, scene.duration_sec)
                scene.visual.asset_path = str(out.resolve())
                scene.visual.layers = []

            elif vis == "character":
                char = get_character(plan["character"])
                base_asset = str((ROOT / "tools" / "k70_scene_engine" / "vendor" /
                                  "gobkit-free-assets" /
                                  f"{char.base_asset_id.split(':', 1)[1]}.glb").resolve())
                png = bpy_bridge.render_still(
                    assets=[{"path": base_asset, "format": "glb", "tint": list(char.accent_color)}],
                    camera={"auto_frame": True, "distance_multiplier": 1.6,
                           "angle": plan["character_angle"]},
                    lighting=None, width=graph.width, height=graph.height,
                    out_dir=visuals_dir, cache_key_extra=f"{char.character_id}_{plan['character_angle']}",
                    samples_override=48,
                )
                qa_result = validate_still(png)
                if not qa_result.passed:
                    rejected_from_scene_engine.append(f"{scene.id} (character render QA failed)")
                    raise RuntimeError(f"{scene.id}: character render failed QA:\n{qa_result.format()}")
                scene.visual.type = "image"
                scene.visual.strategy = "real"
                scene.visual.budget_channel = "stock"
                scene.visual.motion = "ken_burns"
                scene.visual.asset_path = str(png)
                scene.visual.layers = []

            elif vis == "voxel":
                char = get_character(plan["character"])
                base_asset = str((ROOT / "tools" / "k70_scene_engine" / "vendor" /
                                  "gobkit-free-assets" /
                                  f"{char.base_asset_id.split(':', 1)[1]}.glb").resolve())
                png = voxelizer.voxelize_and_render(
                    source_asset_path=base_asset, source_format="glb", block_size=0.08,
                    width=graph.width, height=graph.height, out_dir=visuals_dir,
                )
                qa_result = validate_still(png)
                if not qa_result.passed:
                    rejected_from_scene_engine.append(f"{scene.id} (voxel render QA failed)")
                    raise RuntimeError(f"{scene.id}: voxel render failed QA:\n{qa_result.format()}")
                scene.visual.type = "image"
                scene.visual.strategy = "real"
                scene.visual.budget_channel = "stock"
                scene.visual.motion = "ken_burns"
                scene.visual.asset_path = str(png)
                scene.visual.layers = []

            elif vis in ("stock", "archival"):
                terms = plan["search_terms"] or [plan["query_or_prompt"]]
                path = await broll._video(terms, scene.duration_sec, 0, query_text="",
                                          rank_key=f"{JOB_ID}:{scene.id}")
                if path is None:
                    path = await broll._image(terms, 0, query_text="",
                                              rank_key=f"{JOB_ID}:{scene.id}:img")
                    if path is None:
                        raise RuntimeError(f"{scene.id}: no real footage/image resolved for {terms}")
                    scene.visual.type = "image"
                else:
                    scene.visual.type = "broll"
                scene.visual.strategy = "real"
                scene.visual.budget_channel = "stock"
                scene.visual.motion = "ken_burns"
                scene.visual.asset_path = path
                scene.visual.layers = []

            print(f"  [{scene.id}] {vis} -> {scene.visual.asset_path}")

        save_graph()
        ckpt.mark_done("asset_resolution", {"rejected_from_scene_engine": rejected_from_scene_engine})
        print(f"[assets] done. K70 scene-engine components rejected: {rejected_from_scene_engine or 'none'}")
    else:
        print("[assets] skipped (checkpointed)")

    # ---------------------------------------------------------------- #
    # STAGE: render
    # ---------------------------------------------------------------- #
    graph = load_graph()
    if not ckpt.done("render"):
        out_mp4 = JOB_DIR / "final.mp4"
        await render_ffmpeg.render(graph, out_mp4)
        ckpt.mark_done("render", {"output": str(out_mp4)})
        print(f"[render] done -> {out_mp4}")
    else:
        print("[render] skipped (checkpointed)")

    # ---------------------------------------------------------------- #
    # STAGE: qa
    # ---------------------------------------------------------------- #
    if not ckpt.done("qa"):
        out_mp4 = JOB_DIR / "final.mp4"
        delivered = visual_budget.measure(graph)
        rep = qa.analyze(graph, str(out_mp4), render_seconds=0, ram_peak_mb=0, min_free_mb=-1,
                         consistency=None, timed_out=False, budget_report=delivered)
        report_text = qa.format_report(rep)
        (JOB_DIR / "qa_report.txt").write_text(report_text, encoding="utf-8")
        print(report_text)
        ckpt.mark_done("qa", {"passed": getattr(rep, "passed", None)})
    else:
        print("[qa] skipped (checkpointed) -- see qa_report.txt")
        print((JOB_DIR / "qa_report.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(main())
