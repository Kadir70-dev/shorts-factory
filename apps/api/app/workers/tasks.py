"""
arq worker. ONE task = ONE video, run as a linear staged pipeline with status
checkpoints written to the DB after every stage (resumable / observable).

Run:  arq app.workers.tasks.WorkerSettings
"""
from __future__ import annotations

from arq.connections import RedisSettings

from ..config import load_channel, settings
from ..db import Job, get_job, set_status, upsert_job
from ..director import get_director
from ..pipeline import (
    broll, captions, music, postprocess, render, sfx, storyboard, tts,
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

        # 5. VOICEOVER — TTS per scene, MEASURE real durations, rewrite timeline
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

        # 7.5 SOUND DESIGN — niche music bed + smart envelope, then retention SFX
        graph = await music.add_music(graph, channel)
        graph = await sfx.add_sound_design(graph)

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
