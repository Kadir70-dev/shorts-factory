"""
FastAPI surface for the topic-intelligence engine.

Additive router — mounted under /topic-intelligence, touching nothing that
/generate or /jobs already do.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..auth.deps import optional_auth
from .gemini_client import utc_day_start
from .models import NO_SAFE_TOPIC_AVAILABLE, SelectionResult
from .repository import TopicIntelligenceRepository
from .review import ReviewError, TopicReviewService
from .service import TopicIntelligenceService
from .settings import ti_settings

router = APIRouter(
    prefix="/topic-intelligence",
    tags=["topic-intelligence"],
    dependencies=[Depends(optional_auth)],
)


def _service() -> TopicIntelligenceService:
    return TopicIntelligenceService()


def _repo() -> TopicIntelligenceRepository:
    return TopicIntelligenceRepository()

def _review_service() -> TopicReviewService:
    return TopicReviewService()


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


class ReviewActionRequest(BaseModel):
    actor: str = "reviewer"
    reason: Optional[str] = None


class SelectAlternateRequest(ReviewActionRequest):
    topic_id: str
    override: bool = False


def _review_http_error(exc: ReviewError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail())


@router.get("/reviews")
def review_runs(channel_id: str | None = None, limit: int = Query(25, ge=1, le=100)):
    return _review_service().list_runs(channel_id=channel_id, limit=limit)


@router.get("/reviews/{run_id}")
def review_detail(run_id: str):
    try:
        return _review_service().run_review(run_id)
    except ReviewError as exc:
        raise _review_http_error(exc) from exc


@router.post("/reviews/{run_id}/approve")
async def approve_review(run_id: str, req: ReviewActionRequest):
    try:
        return await _review_service().approve(run_id, actor=req.actor, reason=req.reason)
    except ReviewError as exc:
        raise _review_http_error(exc) from exc


@router.post("/reviews/{run_id}/reject")
def reject_review(run_id: str, req: ReviewActionRequest):
    try:
        return _review_service().reject(run_id, actor=req.actor, reason=req.reason or "")
    except ReviewError as exc:
        raise _review_http_error(exc) from exc


@router.post("/reviews/{run_id}/select-alternate")
def select_alternate_review(run_id: str, req: SelectAlternateRequest):
    try:
        return _review_service().select_alternate(
            run_id, req.topic_id, actor=req.actor, reason=req.reason,
            override=req.override,
        )
    except ReviewError as exc:
        raise _review_http_error(exc) from exc


@router.post("/reviews/{run_id}/candidates/{topic_id}/override-duplicate")
def override_duplicate_review(run_id: str, topic_id: str, req: ReviewActionRequest):
    try:
        return _review_service().override_duplicate(
            run_id, topic_id, actor=req.actor, reason=req.reason or "",
        )
    except ReviewError as exc:
        raise _review_http_error(exc) from exc


@router.get("/review", response_class=HTMLResponse, include_in_schema=False)
def review_dashboard():
    return HTMLResponse("""<!doctype html><html><head><meta charset="utf-8">
<title>Topic review</title><style>
body{font:15px system-ui;max-width:1100px;margin:auto;padding:24px;background:#101525;color:#eef}
article{border:1px solid #394363;border-radius:8px;padding:14px;margin:12px 0}
button,input{font:inherit;padding:8px;margin:4px}a{color:#9cf}.bad{color:#faa}
</style></head><body><h1>Topic review</h1>
<label>Actor <input id="actor" value="reviewer"></label><button onclick="runs()">Refresh</button>
<main id="app">Loading...</main><script>
const B='/topic-intelligence';let run;
async function api(p,o={}){let r=await fetch(B+p,{headers:{'content-type':'application/json'},...o}),d=await r.json();if(!r.ok)throw Error(d.detail?.message||JSON.stringify(d.detail));return d}
const body=r=>JSON.stringify({actor:actor.value||'reviewer',reason:r});
async function runs(){try{let x=await api('/reviews');app.innerHTML=x.map(r=>`<article><button onclick="detail('${r.run_id}')">Review</button> <b>${r.selected_topic||r.run_id}</b> — ${r.review_status}</article>`).join('')||'No runs.'}catch(e){app.textContent=e}}
function card(c,sel){return `<article><h3>${sel?'Selected: ':''}${c.canonical_topic}</h3><p>${c.proposed_angle||''}</p><p>Score ${c.overall_score} · ${c.score_explanation||''}</p><p class="bad">${c.rejection_reasons.join(' · ')}</p><details><summary>Evidence</summary>${c.evidence.map(e=>`<p><a href="${e.url||'#'}" target="_blank">${e.title}</a></p>`).join('')}</details>${sel?'':`<button onclick="alternate('${c.topic_id}',${!c.eligible_for_production})">Select</button>`}</article>`}
function job(g){if(!g)return ``;return `<article><h3>Generation job ${g.job_id}</h3><p>Status: <b>${g.status}</b> · ${g.progress}%</p>${g.error?`<p class=bad>${g.error}</p>`:``}${g.output_mp4?`<p>${g.output_mp4}</p><video controls width=270 src=${g.video_url}></video>`:``}</article>`}
async function detail(id){try{run=id;let d=await api('/reviews/'+id),v=d.review;app.innerHTML=`<button onclick="runs()">Back</button><h2>${id} — ${v.status}</h2><button ${v.can_approve?'':'disabled'} onclick="act('approve')">Approve & enqueue</button><button ${v.can_reject?'':'disabled'} onclick="act('reject')">Reject</button>${job(v.generation)}${d.selected?card(d.selected,true):''}<h2>Alternatives</h2>${d.ranked.filter(x=>x.topic_id!==d.run.selected_topic_id).map(x=>card(x,false)).join('')}<h2>Rejected</h2>${d.rejected.map(x=>card(x,false)).join('')}<h2>Audit</h2><pre>${JSON.stringify(d.audit_trail,null,2)}</pre>`}catch(e){app.textContent=e}}
async function act(k){let r=prompt(k==='reject'?'Reason (required)':'Note')||'';if(k==='reject'&&!r)return;try{await api(`/reviews/${run}/${k}`,{method:'POST',body:body(r)});detail(run)}catch(e){alert(e)}}
async function alternate(t,o){let r=o?prompt('Override reason (required)'):prompt('Note')||'';if(o&&!r)return;try{await api(`/reviews/${run}/select-alternate`,{method:'POST',body:JSON.stringify({actor:actor.value,topic_id:t,reason:r,override:o})});detail(run)}catch(e){alert(e)}}
runs()</script></body></html>""")
