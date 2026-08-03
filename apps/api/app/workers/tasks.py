"""
arq worker. ONE task = ONE video, run as a linear staged pipeline with status
checkpoints written to the DB after every stage (resumable / observable).

Run:  arq app.workers.tasks.WorkerSettings
"""
from __future__ import annotations

from pathlib import Path

from arq.connections import RedisSettings

from ..config import load_channel, settings
from ..db import Job, get_job, set_status, upsert_job
from ..director import get_director
from ..brand import load_theme
from ..director import structures
from ..pipeline import (
    broll, captions, compliance, music, postprocess, render, sfx, storyboard,
    tts, variety,
)
from ..schemas.scene import SceneGraph
from ..schemas.video_spec import VideoSpec


async def run_pipeline(ctx, job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        return {"error": "job gone"}

    spec = VideoSpec.model_validate_json(job.spec_json)
    channel = load_channel(spec.channel_id)

    try:
        # 1. RESEARCH + 2. HOOK + 3. SCRIPT + 4. SCENE TIMELINE  (Phase 2)
        set_status(job_id, "scripting")
        director = get_director(channel)
        graph: SceneGraph = await director.build_scene_graph(spec)

        # 4.5 VARIETY PLAN — this video's caption animation, transition palette,
        #     camera motion, grade and music family, drawn with a cooldown against
        #     the channel's recent uploads. Runs BEFORE assets so the visual
        #     engine and renderer both see the same plan.
        theme = load_theme(graph.brand_id or "k70")
        choice = (structures.get(graph.meta.structure_id) and
                  structures.choose(spec.id, spec.channel_id, spec.niche.value,
                                    forced=graph.meta.structure_id, record=False))
        plan = variety.plan(spec.id, spec.channel_id, theme, choice or None)
        variety.apply(graph, plan)
        print(f"[variety] {plan.summary()}", flush=True)

        # 5. VOICEOVER — the channel's CLONED voice, measured per scene so the
        #    timeline matches the audio that actually exists.
        set_status(job_id, "voicing")
        graph = await tts.synthesize(graph, spec, channel)

        # 6. CAPTIONS — Whisper.cpp word-level over the stitched VO
        set_status(job_id, "captioning")
        graph = await captions.transcribe(graph)

        # 7. ASSETS — route each scene's visual to pexels / manim / ai-video
        set_status(job_id, "assets")
        graph = await broll.resolve_assets(graph, spec)

        # 7.1 LAYERED CINEMATIC STACK (Phase 3 — gated by LAYERED_RENDER, default
        #     OFF). The Storyboard Agent nominates ONE hero beat (bg ▸ subject ▸ fx)
        #     and resolve_layers fills the layer assets CACHE-FIRST under a hard
        #     ≤2-AI-stills / ≤1-hero budget. Inert + byte-identical when off.
        if settings().layered_render:
            graph = storyboard.storyboard(
                graph, character_name=spec.character_name,
                character_desc=spec.character_desc, style=spec.character_style)
            graph = await broll.resolve_layers(graph, spec)

        # 7.5 SOUND DESIGN — rotated music bed + beat-aware envelope, then SFX
        graph = await music.add_music(graph, channel, family=plan.music_family)
        graph = await sfx.add_sound_design(graph)

        # 7.6 COMPLIANCE BACKSTOP — the Director already ran this strictly inside
        #     its repair loop. This non-strict pass catches anything introduced
        #     downstream and attaches the disclaimer + AI-disclosure flags that the
        #     renderer burns in and the metadata reports.
        report = compliance.apply(graph, strict=False)
        print(report.format(), flush=True)

        # persist the finalized SceneGraph (what Remotion will render)
        job = get_job(job_id)
        job.scene_graph_json = graph.model_dump_json()
        upsert_job(job)

        # 8. RENDER — hand SceneGraph to Remotion -> raw mp4
        set_status(job_id, "rendering")
        import time as _time
        _t_render = _time.perf_counter()
        raw_mp4 = await render.render_remotion(graph)

        # 9. POST — ffmpeg loudnorm, music duck, thumbnail, metadata
        set_status(job_id, "post")
        final = await postprocess.finalize(graph, raw_mp4, channel)
        _render_secs = _time.perf_counter() - _t_render

        job = get_job(job_id)
        job.output_mp4 = final["mp4"]
        job.metadata_json = final["metadata_json"]
        upsert_job(job)

        # 9.5 QA (Phase 4) — non-fatal post-render audit (gated QA_ENABLED, default
        #     OFF). Reports black frames / RAM peak / wall-time budget; NEVER fails
        #     the job (a QA error is swallowed) so it's pure observability.
        if settings().qa_enabled:
            try:
                from ..pipeline import qa, ram
                rep = qa.analyze(graph, final["mp4"], render_seconds=_render_secs,
                                 ram_peak_mb=ram.child_peak_mb(), min_free_mb=-1.0)
                print(qa.format_report(rep), flush=True)
            except Exception as _e:  # noqa: BLE001
                print(f"[qa] skipped ({type(_e).__name__}: {_e})", flush=True)

        # Phase 8 is intentionally different from the legacy observability pass:
        # when explicitly enabled it is a production gate and a failed report
        # fails the job before approval/export.
        if settings().visual_qa_engine_enabled:
            from ..pipeline import qa
            qa_path = str(Path(final["mp4"]).with_suffix(".qa.json"))
            rep = qa.production_analyze(
                graph, final["mp4"], thumbnail=final["thumbnail"],
                metadata_path=final["metadata_path"], report_path=qa_path)
            print(qa.format_production_report(rep), flush=True)
            if rep.status == "FAIL":
                raise RuntimeError(f"production visual QA failed; report={qa_path}")

        # 10. APPROVAL GATE — human reviews in dashboard before upload
        set_status(job_id, "awaiting_approval")
        return {"job_id": job_id, "mp4": final["mp4"]}

    except Exception as e:  # noqa: BLE001 — top-level pipeline guard
        set_status(job_id, "failed", error=f"{type(e).__name__}: {e}")
        raise


class WorkerSettings:
    functions = [run_pipeline]
    redis_settings = RedisSettings.from_dsn(settings().redis_url)
    max_jobs = 2          # bound concurrent renders (CPU/GPU heavy)
    job_timeout = 1800    # 30 min hard cap per video
