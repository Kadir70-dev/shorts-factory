"""
POST /generate         — single VideoSpec -> enqueue
POST /generate/batch   — "Generate 5 USA election shorts for today"

The router only validates + enqueues. The arq worker runs the pipeline.
"""
from __future__ import annotations

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter

from ..config import load_channel, settings
from ..db import Job, upsert_job
from ..schemas.video_spec import BatchRequest, VideoSpec

router = APIRouter(prefix="/generate", tags=["generate"])


async def enqueue_spec(spec: VideoSpec) -> None:
    """Persist the job row and hand it to the arq worker.

    Public because Phase 2A's topic-intelligence engine enqueues its selected
    topic through this exact path — one enqueue implementation, not two.
    """
    upsert_job(
        Job(
            id=spec.id,
            channel_id=spec.channel_id,
            niche=spec.niche.value,
            topic=spec.topic,
            status="queued",
            spec_json=spec.model_dump_json(),
        )
    )
    pool = await create_pool(RedisSettings.from_dsn(settings().redis_url))
    await pool.enqueue_job("run_pipeline", spec.id)


# Backwards-compatible alias for the original private name.
_enqueue = enqueue_spec


@router.post("")
async def generate_one(spec: VideoSpec):
    load_channel(spec.channel_id)        # validates channel exists
    await _enqueue(spec)
    return {"job_id": spec.id, "status": "queued"}


@router.post("/batch")
async def generate_batch(req: BatchRequest):
    load_channel(req.channel_id)
    ids: list[str] = []
    for i in range(req.count):
        spec = VideoSpec(
            channel_id=req.channel_id,
            niche=req.niche,
            # if no topic, Director will pick a trending angle per-slot (Phase 2)
            topic=req.topic or f"__trending__:{req.niche.value}:{i}",
            platforms=req.platforms,
            allow_ai_video=req.allow_ai_video,
        )
        await _enqueue(spec)
        ids.append(spec.id)
    return {"job_ids": ids, "count": len(ids), "status": "queued"}
