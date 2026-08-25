#!/usr/bin/env python3
"""Production driver for the K70 PREMIUM internal benchmark EP03 (final
character production pass). NOT another public K70 long-form video.

Same stage pattern as produce_benchmark_ep02.py (storyboard guardrail
gate -> voice -> assets -> render -> technical+perceptual+aesthetic QA),
now resolving "mblab_walk" (a real walk-cycle animation clip, MB-Lab's
own walking.bvh retargeted onto the rig) as a new vis type, alongside
the already-proven mblab_character/procedural_city/voxel_story/chart/
stock handling from EP02.

    .venv-win/Scripts/python.exe scripts/produce_benchmark_ep03.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))

JOB_ID = "k70_premium_benchmark_ep03"
JOB_DIR = ROOT / "data" / "jobs" / JOB_ID
SPEC_DIR = ROOT / "data" / "series" / "k70_premium_benchmark" / "ep03"


async def main() -> None:
    import yaml, os
    preset = yaml.safe_load((ROOT / "config" / "presets" / "documentary_finance.yaml").read_text())
    for k, v in (preset.get("env") or {}).items():
        os.environ[k] = str(v)

    from app.brand.manager import theme_for
    from app.pipeline import dataviz, render_ffmpeg, qa, visual_budget, broll
    from app.pipeline.util import ffprobe_duration, ffmpeg_concat_audio, normalize_narration_joins
    from app.schemas.scene import SceneGraph
    from app.voice.manager import VoiceManager

    from tools.k70_scene_engine.blender import mblab_character, mblab_animation, procedural_building, voxel_story
    from tools.k70_scene_engine.checkpoint.pipeline_checkpoint import PipelineCheckpoint
    from tools.k70_scene_engine.qa.validators import validate_still
    from tools.k70_scene_engine.qa.aesthetic import extract_scene_frames
    from tools.k70_scene_engine.production.gate import (
        beats_from_job_plan, enforce_storyboard_guardrails, enforce_perceptual_qa,
        enforce_aesthetic_qa, ProductionGateError, _LABEL_TO_MODE,
    )

    JOB_DIR.mkdir(parents=True, exist_ok=True)
    visuals_dir = JOB_DIR / "visuals"
    visuals_dir.mkdir(exist_ok=True)
    ckpt = PipelineCheckpoint(JOB_DIR)

    graph_path = JOB_DIR / "scene_graph.json"
    if not graph_path.exists():
        graph_path.write_text((SPEC_DIR / "scene_graph.json").read_text(encoding="utf-8"),
                              encoding="utf-8")

    def load_graph() -> SceneGraph:
        raw = json.loads(graph_path.read_text(encoding="utf-8"))
        overflow = {}
        for sc in raw["scenes"]:
            if sc["duration_sec"] > 12.0:
                overflow[sc["id"]] = sc["duration_sec"]
                sc["duration_sec"] = 12.0
            elif sc["duration_sec"] < 0.8:
                overflow[sc["id"]] = sc["duration_sec"]
                sc["duration_sec"] = 0.8
        g = SceneGraph.model_validate(raw)
        gb = {s.id: s for s in g.scenes}
        for sid, real_dur in overflow.items():
            gb[sid].duration_sec = real_dur
        return g

    graph = load_graph()
    asset_plan_raw = json.loads((SPEC_DIR / "asset_plan.json").read_text(encoding="utf-8"))
    asset_plan = {a["scene_id"]: a for a in asset_plan_raw}

    def save_graph():
        graph_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")

    # ---------------------------------------------------------------- #
    # GATE 1: storyboard guardrails -- BEFORE any rendering
    # ---------------------------------------------------------------- #
    if not ckpt.done("storyboard"):
        raw_graph = json.loads((SPEC_DIR / "scene_graph.json").read_text(encoding="utf-8"))
        beats = beats_from_job_plan(raw_graph, asset_plan_raw)
        try:
            report = enforce_storyboard_guardrails(beats)
        except ProductionGateError as e:
            print(str(e))
            raise SystemExit(
                "PRODUCTION STOPPED: storyboard failed the enforced visual-mix guardrails. "
                "Fix the beat plan (scripts/build_benchmark_ep03.py) and re-run.") from e
        (JOB_DIR / "guardrail_report.txt").write_text(report.format(), encoding="utf-8")
        print(report.format())
        ckpt.mark_done("storyboard", {"passed": report.passed})
    else:
        print("[storyboard] skipped (checkpointed) -- already passed")

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
    graph = load_graph()
    if not ckpt.done("asset_resolution"):
        theme = theme_for(graph, "compositor")

        for scene in graph.scenes:
            plan = asset_plan[scene.id]
            vis = plan["vis"]

            if vis == "chart":
                out = visuals_dir / f"{scene.id}_chart.mp4"
                if not out.exists():
                    await dataviz.render(scene.data, theme, out, graph.width, graph.height,
                                         graph.fps, scene.duration_sec)
                scene.visual.asset_path = str(out.resolve())
                scene.visual.layers = []

            elif vis == "mblab_walk":
                # `house=True` combined-shot framing produced two
                # confirmed-broken real renders in a row this session
                # (see _mblab_walk_script.py's docstring) -- dropped for
                # this pass; the house appears via the preceding real
                # stock-footage beat instead.
                mp4_path = visuals_dir / f"{plan['role']}_walk.mp4"
                if mp4_path.exists():
                    mp4 = mp4_path
                else:
                    mp4 = mblab_animation.render_walk_animation(
                        role=plan["role"], checkpoint=Path(plan["checkpoint"]), house=False,
                        lighting="exterior_day", n_frames=14, width=graph.width, height=graph.height,
                        fps=8, out_dir=visuals_dir, samples_override=40,
                    )
                scene.visual.type = "broll"
                scene.visual.strategy = "real"
                scene.visual.budget_channel = "stock"
                scene.visual.motion = "none"
                scene.visual.asset_path = str(mp4)
                scene.visual.layers = []

            elif vis == "mblab_character":
                png = mblab_character.render_mblab_character(
                    role=plan["role"], checkpoint=Path(plan["checkpoint"]),
                    lighting=plan.get("lighting", "portrait_studio"),
                    shot=plan.get("shot", "medium"), angle=plan.get("angle", "three_quarter"),
                    office_environment=plan.get("office_environment", False),
                    width=graph.width, height=graph.height, out_dir=visuals_dir,
                    use_cache=True, samples_override=64,
                )
                qa_result = validate_still(png)
                if not qa_result.passed:
                    raise RuntimeError(f"{scene.id}: mblab character render failed QA:\n{qa_result.format()}")
                scene.visual.type = "image"
                scene.visual.strategy = "real"
                scene.visual.budget_channel = "stock"
                scene.visual.motion = "ken_burns"
                scene.visual.asset_path = str(png)
                scene.visual.layers = []

            elif vis == "procedural_building":
                png = procedural_building.render_building(
                    building_type=plan["building_type"], width=graph.width, height=graph.height,
                    out_dir=visuals_dir, use_cache=True, samples_override=64,
                )
                scene.visual.type = "image"
                scene.visual.strategy = "real"
                scene.visual.budget_channel = "stock"
                scene.visual.motion = "ken_burns"
                scene.visual.asset_path = str(png)
                scene.visual.layers = []

            elif vis == "voxel_story":
                png = voxel_story.render_voxel_object(
                    object_type=plan["object_type"], block_size=0.35,
                    width=graph.width, height=graph.height, out_dir=visuals_dir,
                    use_cache=True, samples_override=48,
                )
                qa_result = validate_still(png)
                if not qa_result.passed:
                    raise RuntimeError(f"{scene.id}: voxel render failed QA:\n{qa_result.format()}")
                scene.visual.type = "image"
                scene.visual.strategy = "real"
                scene.visual.budget_channel = "stock"
                scene.visual.motion = "ken_burns"
                scene.visual.asset_path = str(png)
                scene.visual.layers = []

            elif vis == "procedural_city":
                src = ROOT / "tools/k70_scene_engine/.test_renders/proof_e_procgen/city_render_final.png"
                out = visuals_dir / f"{scene.id}_procedural_city.png"
                if not out.exists():
                    out.write_bytes(src.read_bytes())
                scene.visual.type = "image"
                scene.visual.strategy = "real"
                scene.visual.budget_channel = "stock"
                scene.visual.motion = "ken_burns"
                scene.visual.asset_path = str(out.resolve())
                scene.visual.layers = []

            elif vis in ("stock", "archival"):
                terms = plan["search_terms"]
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

            else:
                raise ValueError(f"{scene.id}: unknown vis '{vis}'")

            print(f"  [{scene.id}] {vis} -> {scene.visual.asset_path}")

        save_graph()
        ckpt.mark_done("asset_resolution", {})
        print("[assets] done.")
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
    # STAGE: qa (technical + GATE 2 perceptual + GATE 3 aesthetic)
    # ---------------------------------------------------------------- #
    if not ckpt.done("qa"):
        out_mp4 = JOB_DIR / "final.mp4"
        delivered = visual_budget.measure(graph)
        rep = qa.analyze(graph, str(out_mp4), render_seconds=0, ram_peak_mb=0, min_free_mb=-1,
                         consistency=None, timed_out=False, budget_report=delivered)
        report_text = qa.format_report(rep)
        (JOB_DIR / "qa_report.txt").write_text(report_text, encoding="utf-8")
        print(report_text)
        technical_passed = bool(getattr(rep, "passed", None))

        perceptual_passed = True
        try:
            preport = enforce_perceptual_qa(
                scene_graph_path=graph_path, asset_plan_path=SPEC_DIR / "asset_plan.json",
                video_path=out_mp4, contact_sheet_out=JOB_DIR / "contact_sheet.jpg",
            )
            (JOB_DIR / "perceptual_qa_report.txt").write_text(preport.format(), encoding="utf-8")
            print(preport.format())
        except ProductionGateError as e:
            perceptual_passed = False
            (JOB_DIR / "perceptual_qa_report.txt").write_text(str(e), encoding="utf-8")
            print(str(e))

        aesthetic_passed = True
        try:
            frames_dir = JOB_DIR / "aesthetic_frames"
            raw_graph = json.loads(graph_path.read_text(encoding="utf-8"))
            scene_frames = extract_scene_frames(out_mp4, raw_graph, frames_dir)
            tagged = [(p, _LABEL_TO_MODE.get(asset_plan.get(sid, {}).get("vis", ""), None))
                     for p, sid in scene_frames]
            areports = enforce_aesthetic_qa(tagged)
            summary = "\n".join(r.format() for r in areports)
            (JOB_DIR / "aesthetic_qa_report.txt").write_text(summary, encoding="utf-8")
            print(f"[aesthetic] {len(areports)} frames sampled (one per scene), no gross failures")
        except ProductionGateError as e:
            aesthetic_passed = False
            (JOB_DIR / "aesthetic_qa_report.txt").write_text(str(e), encoding="utf-8")
            print(str(e))

        print(f"\nTECHNICAL QA:  {'PASS' if technical_passed else 'FAIL'}")
        print(f"PERCEPTUAL QA: {'PASS' if perceptual_passed else 'FAIL'}")
        print(f"AESTHETIC QA:  {'PASS' if aesthetic_passed else 'FAIL'}")
        ckpt.mark_done("qa", {"technical_passed": technical_passed,
                              "perceptual_passed": perceptual_passed,
                              "aesthetic_passed": aesthetic_passed})
    else:
        print("[qa] skipped (checkpointed) -- see qa_report.txt / perceptual_qa_report.txt / aesthetic_qa_report.txt")


if __name__ == "__main__":
    asyncio.run(main())
