"""
POST /generate         — single VideoSpec -> enqueue
POST /generate/batch   — "Generate 5 USA election shorts for today"

The router only validates + enqueues. The arq worker runs the pipeline.
"""
from __future__ import annotations

import inspect

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException

from ..auth.deps import optional_auth
from ..config import load_channel, settings
from ..db import Job, get_job, upsert_job
from ..schemas.video_spec import BatchRequest, VideoSpec

router = APIRouter(
    prefix="/generate", tags=["generate"], dependencies=[Depends(optional_auth)]
)


class EnqueueError(RuntimeError):
    """The job row was persisted but the queue would not accept it.

    Subclasses RuntimeError so existing broad handlers (e.g. the topic-
    intelligence bridge) keep behaving as they did when a raw
    redis.ConnectionError propagated from here.

    The distinction matters for recovery: the Job row is already committed
    with status `queued`, so the work is not lost — it can be re-enqueued
    once the queue is reachable.
    """


def _require_channel(channel_id: str) -> None:
    """Validate the channel id, or 404.

    `load_channel` raises FileNotFoundError for an unknown id. That escaped
    both endpoints unhandled, producing a 500 with a traceback — and the
    exception text embeds the server's absolute config path, so the response
    also disclosed the deployment's filesystem layout.
    """
    try:
        load_channel(channel_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"unknown channel '{channel_id}'") from exc


async def _close_pool(pool) -> None:
    """Release an arq pool.

    `create_pool` returns an ArqRedis (a redis.asyncio client) holding a
    connection pool. Nothing closed it, so every enqueue leaked one — 50 of
    them for a max-size batch. redis-py renamed `close()` to `aclose()`, so
    both are probed rather than pinning a version.
    """
    closer = getattr(pool, "aclose", None) or getattr(pool, "close", None)
    if closer is None:
        return
    try:
        result = closer()
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001 - a failed close must not fail the enqueue
        pass


async def enqueue_spec(spec: VideoSpec, pool=None) -> None:
    """Persist the job row and hand it to the arq worker.

    Public because Phase 2A's topic-intelligence engine enqueues its selected
    topic through this exact path — one enqueue implementation, not two.

    `pool` lets a caller reuse one connection pool across several enqueues
    (see `generate_batch`); when omitted, one is created and closed here.
    """
    # Stable topic-intelligence ids make approval retries idempotent. A queued
    # row is allowed to re-submit the SAME ARQ job id so a prior Redis outage
    # can recover; ARQ suppresses concurrent/double-click duplicates.
    existing = get_job(spec.id)
    if existing is not None and existing.status != "queued":
        return
    if existing is None:
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

    owns_pool = pool is None
    try:
        if owns_pool:
            pool = await create_pool(RedisSettings.from_dsn(settings().redis_url))
        await pool.enqueue_job("run_pipeline", spec.id, _job_id=spec.id)
    except Exception as exc:  # noqa: BLE001 - re-raised as a typed queue error
        raise EnqueueError(
            f"could not enqueue {spec.id}: {exc.__class__.__name__}. "
            "The job row is persisted as 'queued' and can be re-enqueued."
        ) from exc
    finally:
        if owns_pool and pool is not None:
            await _close_pool(pool)


# Backwards-compatible alias for the original private name.
_enqueue = enqueue_spec


@router.post("")
async def generate_one(spec: VideoSpec):
    _require_channel(spec.channel_id)
    try:
        await enqueue_spec(spec)
    except EnqueueError as exc:
        # 503: the request was valid and the job is recorded; the queue is the
        # thing that is unavailable, and retrying is the correct client action.
        raise HTTPException(503, str(exc)) from exc
    return {"job_id": spec.id, "status": "queued"}


@router.post("/batch")
async def generate_batch(req: BatchRequest):
    _require_channel(req.channel_id)
    ids: list[str] = []
    pool = None
    try:
        # One pool for the whole batch instead of one per spec.
        pool = await create_pool(RedisSettings.from_dsn(settings().redis_url))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"queue unavailable: {exc.__class__.__name__}") from exc

    try:
        for i in range(req.count):
            spec = VideoSpec(
                channel_id=req.channel_id,
                niche=req.niche,
                # if no topic, Director will pick a trending angle per-slot (Phase 2)
                topic=req.topic or f"__trending__:{req.niche.value}:{i}",
                platforms=req.platforms,
                allow_ai_video=req.allow_ai_video,
            )
            try:
                await enqueue_spec(spec, pool=pool)
            except EnqueueError as exc:
                # Partial success is reported honestly: the specs already
                # accepted stay queued rather than being rolled back.
                raise HTTPException(
                    503,
                    f"queue failed after {len(ids)} of {req.count} jobs: {exc}",
                ) from exc
            ids.append(spec.id)
    finally:
        await _close_pool(pool)

    return {"job_ids": ids, "count": len(ids), "status": "queued"}
