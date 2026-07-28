"""
FastAPI surface for the topic-intelligence engine.

Additive router — mounted under /topic-intelligence, touching nothing that
/generate or /jobs already do.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .gemini_client import utc_day_start
from .models import NO_SAFE_TOPIC_AVAILABLE, SelectionResult
from .repository import TopicIntelligenceRepository
from .service import TopicIntelligenceService
from .settings import ti_settings

router = APIRouter(prefix="/topic-intelligence", tags=["topic-intelligence"])


def _service() -> TopicIntelligenceService:
    return TopicIntelligenceService()


def _repo() -> TopicIntelligenceRepository:
    return TopicIntelligenceRepository()


class RunRequest(BaseModel):
    channel_id: Optional[str] = None
    enqueue: Optional[bool] = None
    # Admin escape hatch: force-allow a topic the dedup layer would reject.
    override_topic_ids: list[str] = Field(default_factory=list)


@router.post("/collect")
async def collect(req: RunRequest):
    """Run the connectors only. Returns per-provider health and signal counts."""
    s = ti_settings()
    svc = _service()
    outcome = await svc.collect(channel_id=req.channel_id or s.ti_default_channel)
    return {
        "run_id": outcome.run_id,
        "signal_count": len(outcome.signals),
        "providers": [p.model_dump() for p in outcome.statuses],
    }


@router.post("/rank")
async def rank(req: RunRequest):
    """Collect + score + rank WITHOUT selecting or enqueuing."""
    s = ti_settings()
    svc = _service()
    channel_id = req.channel_id or s.ti_default_channel
    outcome = await svc.collect(channel_id=channel_id)
    finalists, all_candidates = svc.build_candidates(
        outcome.signals, channel_id=channel_id,
        override_topic_ids=set(req.override_topic_ids) or None,
    )
    if not finalists:
        return {
            "run_id": outcome.run_id,
            "status": NO_SAFE_TOPIC_AVAILABLE,
            "cluster_count": len(all_candidates),
            "ranked": [],
        }
    channel = svc._channel(channel_id)
    ranked, ranker_used, cost, warnings, model = await svc.rank(
        finalists, channel=channel, run_id=outcome.run_id
    )
    return {
        "run_id": outcome.run_id,
        "status": "ok",
        "ranker_used": ranker_used,
        "gemini_model": model,
        "cluster_count": len(all_candidates),
        "finalist_count": len(finalists),
        "cost": cost.model_dump(),
        "warnings": warnings,
        "ranked": [r.model_dump() for r in ranked],
    }


@router.post("/select", response_model=SelectionResult)
async def select(req: RunRequest):
    """Full run: collect -> rank -> select -> persist. Enqueue is opt-in.

    Returns 409 when NO_SAFE_TOPIC_AVAILABLE — an explicit refusal, not an error.
    """
    result = await _service().run(
        channel_id=req.channel_id,
        enqueue=req.enqueue,
        override_topic_ids=set(req.override_topic_ids) or None,
    )
    if result.status == NO_SAFE_TOPIC_AVAILABLE:
        raise HTTPException(
            409,
            detail={
                "status": NO_SAFE_TOPIC_AVAILABLE,
                "run_id": result.run_id,
                "warnings": result.warnings,
            },
        )
    return result


@router.get("/candidates")
def candidates(
    channel_id: str | None = None,
    run_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    rows = _repo().candidates(channel_id=channel_id, run_id=run_id, limit=limit)
    return [
        {
            "topic_id": r.topic_id,
            "run_id": r.run_id,
            "channel_id": r.channel_id,
            "canonical_topic": r.canonical_topic,
            "factual_state": r.factual_state,
            "event_type": r.event_type,
            "asset_classes": [a for a in r.asset_classes.split(",") if a],
            "source_count": r.source_count,
            "independent_source_count": r.independent_source_count,
            "source_names": [n for n in r.source_names.split(",") if n],
            "eligible_for_production": r.eligible_for_production,
            "dedup_status": r.dedup_status,
            "risk_flags": [f for f in r.risk_flags.split(",") if f],
            "scores": json.loads(r.deterministic_scores_json or "{}"),
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/candidates/{topic_id}")
def candidate_detail(topic_id: str):
    repo = _repo()
    row = repo.candidate(topic_id)
    if row is None:
        raise HTTPException(404, "candidate not found")
    evidence = repo.evidence_for(topic_id, run_id=row.run_id)
    return {
        "candidate": {
            **{k: v for k, v in row.model_dump().items()
               if k not in {"metrics_json", "deterministic_scores_json"}},
            "metrics": json.loads(row.metrics_json or "{}"),
            "scores": json.loads(row.deterministic_scores_json or "{}"),
        },
        "evidence": [
            {**{k: v for k, v in e.model_dump().items() if k != "metrics_json"},
             "metrics": json.loads(e.metrics_json or "{}")}
            for e in evidence
        ],
    }


@router.get("/providers/status")
def providers_status():
    """Config + live circuit state, plus the outcome of the most recent runs."""
    svc = _service()
    recent = _repo().latest_provider_runs(limit=40)
    last_by_provider: dict[str, dict] = {}
    for r in recent:
        if r.provider not in last_by_provider:
            last_by_provider[r.provider] = {
                "run_id": r.run_id, "ok": r.ok, "signal_count": r.signal_count,
                "latency_ms": r.latency_ms, "error": r.error,
                "skipped_reason": r.skipped_reason, "stale": r.stale,
                "at": r.created_at,
            }
    s = ti_settings()
    return {
        "gemini": {
            "ranker_enabled": s.gemini_ranker_enabled,
            "grounding_enabled": s.gemini_grounding_enabled,
            "configured": s.gemini_usable,
            "model": s.gemini_model,
            "daily_budget_usd": s.gemini_daily_budget_usd,
            "spent_today_usd": _repo().spend_since(utc_day_start()),
        },
        "providers": [
            {**p.model_dump(), "last_run": last_by_provider.get(p.name)}
            for p in svc.provider_status()
        ],
    }


@router.get("/runs/{run_id}")
def run_detail(run_id: str):
    repo = _repo()
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return {
        "run": {
            **{k: v for k, v in run.model_dump().items() if k != "warnings_json"},
            "warnings": json.loads(run.warnings_json or "[]"),
        },
        "providers": [p.model_dump() for p in repo.provider_runs(run_id)],
        "results": [
            {**{k: v for k, v in r.model_dump().items() if k != "scores_json"},
             "scores": json.loads(r.scores_json or "{}")}
            for r in repo.run_results(run_id)
        ],
    }
