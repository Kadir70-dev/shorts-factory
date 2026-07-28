"""
Phase 2B — topic-intelligence review and approval workflow.

Phase 2A decides. Phase 2B is where a HUMAN agrees before anything is produced.
Deliberately out of scope here: YouTube upload, publishing, and any scheduler.
Nothing in this module runs on a timer — every action is an explicit request, and
`TI_AUTO_ENQUEUE` stays false so the only path from a decision to the pipeline is
a person pressing Approve.

Storage discipline: this phase adds NO tables. Every piece of review state lives
in the Phase 2A schema, which already modelled it:

    ti_ranking_run.selected_topic_id   which candidate is currently chosen
    ti_ranking_run.enqueued_job_id     the ONE job a run may ever produce
    ti_ranking_result.selected         the per-candidate selection flag
    ti_topic_candidate.*               scores, evidence links, dedup verdict
    ti_topic_ledger.status             the review verdict itself
    ti_topic_ledger.override_reason    the append-only audit trail (JSON)

`ti_topic_ledger.status` carries the whole workflow:

    selected   -> awaiting review           (blocks reuse: we committed to it)
    queued     -> approved AND enqueued     (blocks reuse)
    rejected   -> a reviewer said no        (blocks reuse; override to undo)
    abandoned  -> replaced by an alternate  (does NOT block: free to re-propose)

Idempotence is the safety property that matters most: a run may produce at most
ONE job, ever. Every write path that could enqueue checks `enqueued_job_id` and
the channel-wide ledger first, so a double-clicked Approve cannot double-produce.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional

from ..config import load_channel
from .models import (
    NO_SAFE_TOPIC_AVAILABLE,
    EvidenceItem,
    RankedTopic,
    SourceTier,
    TopicScores,
)
from .repository import TopicIntelligenceRepository
from .settings import TopicIntelligenceSettings, ti_settings
from .tables import (
    TopicCandidateRow,
    TopicEvidence,
    TopicLedger,
    TopicRankingResult,
    TopicRankingRun,
)

# Ledger states that mean "this topic is already committed to the pipeline".
# Approving anything that collides with one of these is a duplicate enqueue.
IN_PIPELINE_STATUSES = ("queued", "rendering", "published")

# Review verdicts surfaced to the dashboard, derived from the ledger row.
REVIEW_PENDING = "pending_review"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_SUPERSEDED = "superseded"
REVIEW_NONE = "no_topic"

AUDIT_ACTIONS = (
    "approve", "reject", "select_alternate", "supersede", "override_duplicate",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewError(Exception):
    """A refusal with an HTTP shape. Raised by the service so the router stays
    a thin translation layer and the service stays testable without FastAPI."""

    def __init__(self, status_code: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.extra = extra

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}


# --------------------------------------------------------------------------- #
# Audit trail — stored in ti_topic_ledger.override_reason as a JSON array
# --------------------------------------------------------------------------- #
def decode_audit(raw: str | None) -> list[dict[str, Any]]:
    """Read the audit trail, tolerating the Phase 2A plain-string form."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [{"at": None, "action": "override_duplicate", "actor": "system",
                 "reason": raw}]
    if isinstance(parsed, list):
        return [e for e in parsed if isinstance(e, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return [{"at": None, "action": "override_duplicate", "actor": "system",
             "reason": str(parsed)}]


def encode_audit(entries: list[dict[str, Any]]) -> str:
    return json.dumps(entries, default=str)


def audit_entry(
    action: str,
    *,
    actor: str,
    reason: str | None = None,
    run_id: str | None = None,
    topic_id: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "at": _now().isoformat(),
        "action": action,
        "actor": actor or "unknown",
        "reason": (reason or "").strip() or None,
        "run_id": run_id,
        "topic_id": topic_id,
        "from_status": from_status,
        "to_status": to_status,
        **extra,
    }


# --------------------------------------------------------------------------- #
# Row -> view helpers
# --------------------------------------------------------------------------- #
def _split(value: str | None, sep: str = ",") -> list[str]:
    return [p.strip() for p in (value or "").split(sep) if p.strip()]


def _loads(value: str | None, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except json.JSONDecodeError:
        return default
    return parsed if parsed is not None else default


def evidence_view(rows: Iterable[TopicEvidence]) -> list[dict[str, Any]]:
    """Source evidence with its URLs — the citation list the reviewer reads."""
    return [
        {
            "provider": e.provider,
            "title": e.title,
            "url": e.url,
            "external_id": e.external_id,
            "published_at": e.published_at,
            "collected_at": e.collected_at,
            "source_tier": e.source_tier,
            "source_credibility": e.source_credibility,
            "excerpt": e.excerpt,
            "metrics": _loads(e.metrics_json, {}),
            "grounded": e.grounded,
            "grounding_complete": e.grounding_complete,
        }
        for e in rows
    ]


def candidate_view(
    *,
    result: TopicRankingResult | None,
    candidate: TopicCandidateRow | None,
    evidence: list[TopicEvidence],
) -> dict[str, Any]:
    """One reviewable candidate, merged from the ranking result (the judgement)
    and the candidate row (the measured facts). Either side may be missing: a
    dedup-blocked topic never reaches ranking, and a ranking result always has a
    candidate row unless the run predates this phase."""
    scores = _loads(result.scores_json, {}) if result else (
        _loads(candidate.deterministic_scores_json, {}) if candidate else {}
    )
    reasons = _split(
        (result.rejection_reasons if result else candidate.rejection_reasons
         if candidate else ""), sep=" | ",
    )
    flags = _split(result.risk_flags if result else
                   (candidate.risk_flags if candidate else ""))
    eligible = (
        result.eligible_for_production if result
        else (candidate.eligible_for_production if candidate else False)
    )
    return {
        "topic_id": (result.topic_id if result else candidate.topic_id),
        "rank": result.rank if result else None,
        "canonical_topic": (
            result.canonical_topic if result and result.canonical_topic
            else (candidate.canonical_topic if candidate else "")
        ),
        "proposed_angle": result.proposed_angle if result else "",
        "target_viewer": result.target_viewer if result else "",
        "hook_concept": result.hook_concept if result else "",
        "why_now": result.why_now if result else "",
        # Every score dimension, not just the overall.
        "scores": scores,
        "overall_score": (
            result.overall_score if result
            else float(scores.get("overall_score", 0.0))
        ),
        "confidence": result.confidence if result else 0.0,
        "ranker": result.ranker if result else "none",
        # The Gemini (or deterministic) explanation of the score.
        "score_explanation": result.score_explanation if result else "",
        "safety_flags": flags,
        "rejection_reasons": reasons,
        "eligible_for_production": eligible,
        "selected": bool(result.selected) if result else False,
        "recommended_publish_window": (
            result.recommended_publish_window if result else None
        ),
        "expires_at": (
            result.expires_at if result
            else (candidate.expires_at if candidate else None)
        ),
        # Measured, provider-derived facts.
        "dedup_status": candidate.dedup_status if candidate else "unknown",
        "factual_state": candidate.factual_state if candidate else "unknown",
        "event_type": candidate.event_type if candidate else "other",
        "asset_classes": _split(candidate.asset_classes if candidate else ""),
        "tickers": _split(candidate.tickers if candidate else ""),
        "source_count": candidate.source_count if candidate else 0,
        "independent_source_count": (
            candidate.independent_source_count if candidate else 0
        ),
        "source_names": _split(candidate.source_names if candidate else ""),
        "metrics": _loads(candidate.metrics_json, {}) if candidate else {},
        "evidence": evidence_view(evidence),
    }


def ranked_topic_from_rows(
    result: TopicRankingResult, evidence: list[TopicEvidence]
) -> RankedTopic:
    """Rebuild the domain object the existing enqueue bridge expects.

    Approval happens minutes or hours after the run, in a different process, so
    the decision is reconstituted from the persisted rows rather than kept in
    memory. The bridge, Director and pipeline see exactly what Phase 2A produced.
    """
    return RankedTopic(
        topic_id=result.topic_id,
        canonical_topic=result.canonical_topic,
        proposed_angle=result.proposed_angle,
        target_viewer=result.target_viewer,
        hook_concept=result.hook_concept,
        why_now=result.why_now,
        scores=TopicScores(**_loads(result.scores_json, {})),
        supporting_evidence=[
            EvidenceItem(
                provider=e.provider, title=e.title, url=e.url,
                external_id=e.external_id, published_at=e.published_at,
                collected_at=e.collected_at,
                source_tier=_tier(e.source_tier),
                source_credibility=e.source_credibility,
                excerpt=e.excerpt, metrics=_loads(e.metrics_json, {}),
                grounded=e.grounded, grounding_complete=e.grounding_complete,
            )
            for e in evidence
        ],
        source_names=[],
        source_count=len(evidence),
        confidence=result.confidence,
        expires_at=result.expires_at,
        recommended_publish_window=result.recommended_publish_window,
        risk_flags=_split(result.risk_flags),
        rejection_reasons=_split(result.rejection_reasons, sep=" | "),
        ranker=result.ranker,
        eligible_for_production=result.eligible_for_production,
        score_explanation=result.score_explanation,
    )


def _tier(value: str | None) -> SourceTier:
    try:
        return SourceTier(value or "unknown")
    except ValueError:
        return SourceTier.unknown


# --------------------------------------------------------------------------- #
# The service
# --------------------------------------------------------------------------- #
EnqueueFn = Callable[..., Awaitable[str]]


class TopicReviewService:
    """Read model + the five review actions. Framework-free on purpose."""

    def __init__(
        self,
        *,
        repo: TopicIntelligenceRepository | None = None,
        settings: TopicIntelligenceSettings | None = None,
        enqueue: EnqueueFn | None = None,
    ) -> None:
        self.repo = repo or TopicIntelligenceRepository()
        self.settings = settings or ti_settings()
        self._enqueue = enqueue

    # ------------------------------------------------------------------ reads
    def list_runs(
        self, *, channel_id: str | None = None, limit: int = 25
    ) -> list[dict[str, Any]]:
        out = []
        for run in self.repo.list_runs(channel_id=channel_id, limit=limit):
            ledger = (
                self.repo.ledger_row(run_id=run.run_id,
                                     topic_id=run.selected_topic_id)
                if run.selected_topic_id else None
            )
            selected = (
                self.repo.ranking_result(run.run_id, run.selected_topic_id)
                if run.selected_topic_id else None
            )
            out.append({
                "run_id": run.run_id,
                "channel_id": run.channel_id,
                "status": run.status,
                "review_status": review_status(run, ledger),
                "ranker_used": run.ranker_used,
                "gemini_model": run.gemini_model,
                "selected_topic_id": run.selected_topic_id,
                "selected_topic": selected.canonical_topic if selected else None,
                "overall_score": selected.overall_score if selected else None,
                "enqueued_job_id": run.enqueued_job_id,
                "cluster_count": run.cluster_count,
                "finalist_count": run.finalist_count,
                "estimated_usd": run.estimated_usd,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            })
        return out

    def run_review(self, run_id: str) -> dict[str, Any]:
        """The whole decision, assembled for a reviewer: ranked candidates, all
        score dimensions, evidence with URLs, the model's explanation, safety
        flags, rejections with their reasons, and the publish window."""
        run = self._run_or_404(run_id)
        results = {r.topic_id: r for r in self.repo.run_results(run_id)}
        candidates = {c.topic_id: c for c in self.repo.run_candidates(run_id)}
        evidence: dict[str, list[TopicEvidence]] = {}
        for e in self.repo.run_evidence(run_id):
            evidence.setdefault(e.topic_id, []).append(e)

        views: list[dict[str, Any]] = []
        for topic_id in list(results) + [
            t for t in candidates if t not in results
        ]:
            views.append(candidate_view(
                result=results.get(topic_id),
                candidate=candidates.get(topic_id),
                evidence=evidence.get(topic_id, []),
            ))
        views.sort(key=lambda v: (
            not v["eligible_for_production"],
            v["rank"] if v["rank"] is not None else 10**6,
            -v["overall_score"],
        ))

        ranked = [v for v in views if v["eligible_for_production"]]
        rejected = [v for v in views if not v["eligible_for_production"]]
        selected = next(
            (v for v in views if v["topic_id"] == run.selected_topic_id), None
        )
        ledger = (
            self.repo.ledger_row(run_id=run_id, topic_id=run.selected_topic_id)
            if run.selected_topic_id else None
        )
        status = review_status(run, ledger)
        in_pipeline = bool(run.enqueued_job_id) or (
            ledger is not None and ledger.status in IN_PIPELINE_STATUSES
        )
        return {
            "run": {
                "run_id": run.run_id,
                "channel_id": run.channel_id,
                "status": run.status,
                "ranker_used": run.ranker_used,
                "gemini_model": run.gemini_model,
                "prompt_version": run.prompt_version,
                "ranking_version": run.ranking_version,
                "selected_topic_id": run.selected_topic_id,
                "enqueued_job_id": run.enqueued_job_id,
                "funnel": {
                    "raw_signals": run.raw_signal_count,
                    "clusters": run.cluster_count,
                    "finalists": run.finalist_count,
                },
                "cost": {
                    "gemini_calls": run.gemini_calls,
                    "input_tokens": run.input_tokens,
                    "output_tokens": run.output_tokens,
                    "estimated_usd": run.estimated_usd,
                    "budget_exhausted": run.budget_exhausted,
                },
                "warnings": _loads(run.warnings_json, []),
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            },
            "review": {
                "status": status,
                "ledger_status": ledger.status if ledger else None,
                "job_id": ledger.job_id if ledger else run.enqueued_job_id,
                "in_pipeline": in_pipeline,
                "can_approve": status == REVIEW_PENDING and not in_pipeline,
                "can_reject": status == REVIEW_PENDING and not in_pipeline,
                "can_select_alternate": not in_pipeline and len(views) > 0,
                "recommended_publish_window": (
                    selected["recommended_publish_window"] if selected else None
                ),
            },
            "selected": selected,
            "ranked": ranked,
            "rejected": rejected,
            "providers": [p.model_dump() for p in self.repo.provider_runs(run_id)],
            "audit_trail": self._audit_for_run(run_id),
        }

    def _audit_for_run(self, run_id: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for row in self.repo.run_candidates(run_id):
            led = self.repo.ledger_row(run_id=run_id, topic_id=row.topic_id)
            if led is not None:
                entries.extend(decode_audit(led.override_reason))
        entries.sort(key=lambda e: e.get("at") or "")
        return entries

    # ---------------------------------------------------------------- actions
    async def approve(
        self, run_id: str, *, actor: str = "reviewer", reason: str | None = None
    ) -> dict[str, Any]:
        """Approve the selected topic and enqueue it into the EXISTING pipeline.

        This is the only enqueue path in Phase 2B, and it is human-triggered:
        TI_AUTO_ENQUEUE stays false. Publishing is NOT part of this — the job
        renders, nothing is uploaded.
        """
        run = self._run_or_404(run_id)
        topic_id = self._selected_topic_or_409(run)
        ledger = self._ledger_or_409(run_id, topic_id)

        # --- duplicate enqueue prevention, two independent guards ---
        if run.enqueued_job_id:
            raise ReviewError(
                409, "ALREADY_ENQUEUED",
                f"run {run_id} already enqueued job {run.enqueued_job_id}",
                job_id=run.enqueued_job_id, topic_id=topic_id,
            )
        if ledger.status in IN_PIPELINE_STATUSES:
            raise ReviewError(
                409, "ALREADY_ENQUEUED",
                f"topic {topic_id} is already {ledger.status}",
                job_id=ledger.job_id, topic_id=topic_id,
            )
        if ledger.status == "rejected":
            raise ReviewError(
                409, "ALREADY_REJECTED",
                f"topic {topic_id} was rejected by review; select an alternate or "
                "re-run topic intelligence",
                topic_id=topic_id,
            )
        clash = [
            r for r in self.repo.ledger_rows_by_key(
                channel_id=run.channel_id,
                canonical_key=ledger.canonical_key,
                statuses=IN_PIPELINE_STATUSES,
            )
            if r.id != ledger.id
        ]
        if clash:
            raise ReviewError(
                409, "DUPLICATE_TOPIC",
                f"this story is already in the pipeline as topic "
                f"{clash[0].topic_id} (status={clash[0].status})",
                job_id=clash[0].job_id, topic_id=clash[0].topic_id,
            )

        result = self.repo.ranking_result(run_id, topic_id)
        if result is None:
            raise ReviewError(
                409, "NO_RANKING_RESULT",
                f"no persisted ranking result for topic {topic_id}",
                topic_id=topic_id,
            )

        evidence = self.repo.evidence_for(topic_id, run_id=run_id)
        topic = ranked_topic_from_rows(result, evidence)
        candidate = self.repo.candidate_in_run(run_id, topic_id)
        entry = audit_entry(
            "approve", actor=actor, reason=reason, run_id=run_id,
            topic_id=topic_id, from_status=ledger.status, to_status="queued",
        )
        bundle = approval_bundle(
            run=run, result=result, candidate=candidate, evidence=evidence,
            approval=entry,
        )

        # Enqueue FIRST. If the queue is down nothing is mutated, so the reviewer
        # can simply press Approve again — no half-approved state to clean up.
        try:
            job_id = await self._do_enqueue(topic, run.channel_id, bundle)
        except Exception as e:  # noqa: BLE001
            raise ReviewError(
                502, "ENQUEUE_FAILED",
                f"could not enqueue the approved topic ({type(e).__name__}: {e}); "
                "nothing was changed — retry when the queue is reachable",
                topic_id=topic_id,
            ) from e

        entry["job_id"] = job_id
        self.repo.update_ledger_row(
            ledger.id, status="queued", job_id=job_id,
            override_reason=encode_audit(decode_audit(ledger.override_reason) + [entry]),
        )
        self.repo.set_run_enqueued(run_id, job_id)
        self.repo.append_run_warning(
            run_id, f"approved by {actor}: enqueued job {job_id}"
        )
        print(f"[ti.review] run={run_id} APPROVED topic={topic_id} "
              f"job={job_id} actor={actor}", flush=True)
        return self.run_review(run_id)

    def reject(
        self, run_id: str, *, reason: str, actor: str = "reviewer"
    ) -> dict[str, Any]:
        """Turn the selected topic down. The topic stops being reusable so it does
        not resurface tomorrow; `override_duplicate` is the way back."""
        reason = (reason or "").strip()
        if not reason:
            raise ReviewError(
                422, "REASON_REQUIRED", "a rejection reason is required"
            )
        run = self._run_or_404(run_id)
        topic_id = self._selected_topic_or_409(run)
        ledger = self._ledger_or_409(run_id, topic_id)

        if run.enqueued_job_id or ledger.status in IN_PIPELINE_STATUSES:
            raise ReviewError(
                409, "ALREADY_ENQUEUED",
                f"topic {topic_id} is already in the pipeline "
                f"(job {run.enqueued_job_id or ledger.job_id}); it cannot be rejected",
                job_id=run.enqueued_job_id or ledger.job_id, topic_id=topic_id,
            )
        if ledger.status == "rejected":
            raise ReviewError(
                409, "ALREADY_REJECTED",
                f"topic {topic_id} was already rejected", topic_id=topic_id,
            )

        entry = audit_entry(
            "reject", actor=actor, reason=reason, run_id=run_id,
            topic_id=topic_id, from_status=ledger.status, to_status="rejected",
        )
        self.repo.update_ledger_row(
            ledger.id, status="rejected",
            override_reason=encode_audit(decode_audit(ledger.override_reason) + [entry]),
        )
        self.repo.annotate_topic(
            run_id, topic_id, eligible_for_production=False,
            add_rejection_reason=f"REVIEW REJECTED by {actor}: {reason}",
        )
        self.repo.append_run_warning(run_id, f"rejected by {actor}: {reason}")
        print(f"[ti.review] run={run_id} REJECTED topic={topic_id} "
              f"actor={actor} reason={reason!r}", flush=True)
        return self.run_review(run_id)

    def select_alternate(
        self,
        run_id: str,
        topic_id: str,
        *,
        actor: str = "reviewer",
        reason: str | None = None,
        override: bool = False,
    ) -> dict[str, Any]:
        """Pick a different ranked candidate from the same run.

        The previous selection becomes `abandoned` — replaced, not refused — so it
        remains available to a future run.
        """
        run = self._run_or_404(run_id)
        if run.enqueued_job_id:
            raise ReviewError(
                409, "ALREADY_ENQUEUED",
                f"run {run_id} already enqueued job {run.enqueued_job_id}; the "
                "selection is final",
                job_id=run.enqueued_job_id,
            )
        if topic_id == run.selected_topic_id:
            raise ReviewError(
                409, "ALREADY_SELECTED",
                f"topic {topic_id} is already the selection for run {run_id}",
                topic_id=topic_id,
            )

        result = self.repo.ranking_result(run_id, topic_id)
        candidate = self.repo.candidate_in_run(run_id, topic_id)
        if result is None and candidate is None:
            raise ReviewError(
                404, "TOPIC_NOT_IN_RUN",
                f"topic {topic_id} is not part of run {run_id}", topic_id=topic_id,
            )
        eligible = (
            result.eligible_for_production if result
            else candidate.eligible_for_production
        )
        if not eligible and not override:
            raise ReviewError(
                409, "TOPIC_NOT_ELIGIBLE",
                f"topic {topic_id} is not eligible for production; override it "
                "with an audit reason first",
                topic_id=topic_id,
                rejection_reasons=_split(
                    (result.rejection_reasons if result
                     else candidate.rejection_reasons), sep=" | ",
                ),
            )
        if override and not (reason or "").strip():
            raise ReviewError(
                422, "REASON_REQUIRED",
                "overriding an ineligible candidate requires an audit reason",
            )

        # Retire the outgoing selection. `abandoned` is intentionally non-blocking.
        previous = (
            self.repo.ledger_row(run_id=run_id, topic_id=run.selected_topic_id)
            if run.selected_topic_id else None
        )
        if previous is not None and previous.status not in IN_PIPELINE_STATUSES:
            prev_entry = audit_entry(
                "supersede", actor=actor, reason=reason, run_id=run_id,
                topic_id=previous.topic_id, from_status=previous.status,
                to_status="abandoned", superseded_by=topic_id,
            )
            self.repo.update_ledger_row(
                previous.id, status="abandoned",
                override_reason=encode_audit(
                    decode_audit(previous.override_reason) + [prev_entry]
                ),
            )

        self.repo.set_run_selection(run_id, topic_id)
        entry = audit_entry(
            "select_alternate", actor=actor, reason=reason, run_id=run_id,
            topic_id=topic_id, from_status=None, to_status="selected",
            replaced=run.selected_topic_id, override=bool(override),
        )
        existing = self.repo.ledger_row(run_id=run_id, topic_id=topic_id)
        if existing is not None:
            self.repo.update_ledger_row(
                existing.id, status="selected",
                override_reason=encode_audit(
                    decode_audit(existing.override_reason) + [entry]
                ),
            )
        else:
            self.repo.create_ledger_row(
                channel_id=run.channel_id, topic_id=topic_id,
                canonical_key=_canonical_key_for(candidate, result),
                canonical_topic=(
                    result.canonical_topic if result else candidate.canonical_topic
                ),
                proposed_angle=result.proposed_angle if result else "",
                hook_concept=result.hook_concept if result else "",
                factual_state=candidate.factual_state if candidate else "unknown",
                event_type=candidate.event_type if candidate else "other",
                tickers=candidate.tickers if candidate else "",
                status="selected", run_id=run_id,
                overall_score=(
                    result.overall_score if result
                    else float(_loads(candidate.deterministic_scores_json, {})
                               .get("overall_score", 0.0))
                ),
                override_reason=encode_audit([entry]),
            )
        self.repo.append_run_warning(
            run_id,
            f"selection changed by {actor}: {run.selected_topic_id} -> {topic_id}"
            + (f" ({reason})" if reason else ""),
        )
        print(f"[ti.review] run={run_id} SELECTION {run.selected_topic_id} -> "
              f"{topic_id} actor={actor}", flush=True)
        return self.run_review(run_id)

    def override_duplicate(
        self, run_id: str, topic_id: str, *, reason: str, actor: str = "reviewer"
    ) -> dict[str, Any]:
        """Clear a dedup rejection so the topic becomes selectable again.

        The reason is MANDATORY and is written to the ledger's audit trail: an
        override that nobody has to justify is not a control.
        """
        reason = (reason or "").strip()
        if not reason:
            raise ReviewError(
                422, "REASON_REQUIRED",
                "overriding a duplicate rejection requires an audit reason",
            )
        run = self._run_or_404(run_id)
        candidate = self.repo.candidate_in_run(run_id, topic_id)
        result = self.repo.ranking_result(run_id, topic_id)
        if candidate is None and result is None:
            raise ReviewError(
                404, "TOPIC_NOT_IN_RUN",
                f"topic {topic_id} is not part of run {run_id}", topic_id=topic_id,
            )

        previous_status = candidate.dedup_status if candidate else "unknown"
        entry = audit_entry(
            "override_duplicate", actor=actor, reason=reason, run_id=run_id,
            topic_id=topic_id, from_status=previous_status, to_status="override",
            previous_rejection_reasons=_split(
                (candidate.rejection_reasons if candidate
                 else result.rejection_reasons), sep=" | ",
            ),
        )
        self.repo.annotate_topic(
            run_id, topic_id, eligible_for_production=True,
            dedup_status="override",
            add_rejection_reason=f"ADMIN OVERRIDE by {actor}: {reason}",
        )
        existing = self.repo.ledger_row(run_id=run_id, topic_id=topic_id)
        if existing is not None:
            self.repo.update_ledger_row(
                existing.id,
                override_reason=encode_audit(
                    decode_audit(existing.override_reason) + [entry]
                ),
            )
        else:
            # No ledger row yet: a dedup-blocked topic was never selected. Record
            # the override as `abandoned` so the audit survives without the row
            # itself blocking anything.
            self.repo.create_ledger_row(
                channel_id=run.channel_id, topic_id=topic_id,
                canonical_key=_canonical_key_for(candidate, result),
                canonical_topic=(
                    candidate.canonical_topic if candidate
                    else result.canonical_topic
                ),
                proposed_angle=result.proposed_angle if result else "",
                hook_concept=result.hook_concept if result else "",
                factual_state=candidate.factual_state if candidate else "unknown",
                event_type=candidate.event_type if candidate else "other",
                tickers=candidate.tickers if candidate else "",
                status="abandoned", run_id=run_id,
                override_reason=encode_audit([entry]),
            )
        self.repo.append_run_warning(
            run_id, f"duplicate override by {actor} on {topic_id}: {reason}"
        )
        print(f"[ti.review] run={run_id} OVERRIDE topic={topic_id} "
              f"actor={actor} reason={reason!r}", flush=True)
        return self.run_review(run_id)

    # ------------------------------------------------------------- internals
    async def _do_enqueue(self, topic: RankedTopic, channel_id: str, bundle: dict) -> str:
        if self._enqueue is not None:
            return await self._enqueue(topic, load_channel(channel_id),
                                       evidence_bundle=bundle)
        from .bridge import enqueue_topic

        return await enqueue_topic(topic, load_channel(channel_id),
                                   evidence_bundle=bundle)

    def _run_or_404(self, run_id: str) -> TopicRankingRun:
        run = self.repo.get_run(run_id)
        if run is None:
            raise ReviewError(404, "RUN_NOT_FOUND", f"run {run_id} not found")
        return run

    def _selected_topic_or_409(self, run: TopicRankingRun) -> str:
        if not run.selected_topic_id:
            raise ReviewError(
                409, "NO_TOPIC_SELECTED",
                f"run {run.run_id} selected no topic "
                f"(status={run.status}); nothing to act on",
                run_status=run.status,
            )
        return run.selected_topic_id

    def _ledger_or_409(self, run_id: str, topic_id: str) -> TopicLedger:
        ledger = self.repo.ledger_row(run_id=run_id, topic_id=topic_id)
        if ledger is None:
            raise ReviewError(
                409, "NO_LEDGER_ENTRY",
                f"topic {topic_id} has no ledger entry for run {run_id}; the run "
                "was not persisted",
                topic_id=topic_id,
            )
        return ledger


# --------------------------------------------------------------------------- #
# Free functions used by both the service and the router
# --------------------------------------------------------------------------- #
def review_status(run: TopicRankingRun, ledger: TopicLedger | None) -> str:
    if run.status == NO_SAFE_TOPIC_AVAILABLE or not run.selected_topic_id:
        return REVIEW_NONE
    if run.enqueued_job_id or (ledger is not None
                               and ledger.status in IN_PIPELINE_STATUSES):
        return REVIEW_APPROVED
    if ledger is None:
        return REVIEW_PENDING
    if ledger.status == "rejected":
        return REVIEW_REJECTED
    if ledger.status == "abandoned":
        return REVIEW_SUPERSEDED
    return REVIEW_PENDING


def _canonical_key_for(
    candidate: TopicCandidateRow | None, result: TopicRankingResult | None
) -> str:
    from .models import FactualState
    from .normalizer import canonical_key

    topic = (
        candidate.canonical_topic if candidate
        else (result.canonical_topic if result else "")
    )
    try:
        state = FactualState(candidate.factual_state) if candidate \
            else FactualState.unknown
    except ValueError:
        state = FactualState.unknown
    return canonical_key(topic, state)


def approval_bundle(
    *,
    run: TopicRankingRun,
    result: TopicRankingResult,
    candidate: Optional[TopicCandidateRow],
    evidence: list[TopicEvidence],
    approval: dict[str, Any],
) -> dict[str, Any]:
    """The evidence bundle attached to the approved job.

    Same intent as `provenance.evidence_bundle`, rebuilt from persisted rows and
    extended with the human approval record, so a finished video can answer both
    "why this topic?" and "who signed off, and why?".
    """
    from .provenance import BUNDLE_VERSION

    return {
        "bundle_version": BUNDLE_VERSION,
        "run_id": run.run_id,
        "channel_id": run.channel_id,
        "decided_at": _now().isoformat(),
        "ranking_version": run.ranking_version,
        "prompt_version": run.prompt_version,
        "ranker_used": run.ranker_used,
        "gemini_model": run.gemini_model,
        "topic": {
            "topic_id": result.topic_id,
            "canonical_topic": result.canonical_topic,
            "proposed_angle": result.proposed_angle,
            "target_viewer": result.target_viewer,
            "hook_concept": result.hook_concept,
            "why_now": result.why_now,
            "confidence": result.confidence,
            "expires_at": result.expires_at,
            "recommended_publish_window": result.recommended_publish_window,
            "factual_state": candidate.factual_state if candidate else None,
            "event_type": candidate.event_type if candidate else None,
            "asset_classes": _split(candidate.asset_classes if candidate else ""),
            "tickers": _split(candidate.tickers if candidate else ""),
        },
        "scores": _loads(result.scores_json, {}),
        "score_explanation": result.score_explanation,
        "risk_flags": _split(result.risk_flags),
        "rejection_reasons": _split(result.rejection_reasons, sep=" | "),
        "eligible_for_production": result.eligible_for_production,
        "evidence": evidence_view(evidence),
        "measured_metrics": _loads(candidate.metrics_json, {}) if candidate else {},
        "source_names": _split(candidate.source_names if candidate else ""),
        "source_count": candidate.source_count if candidate else len(evidence),
        "independent_source_count": (
            candidate.independent_source_count if candidate else 0
        ),
        "funnel": {
            "raw_signals": run.raw_signal_count,
            "clusters": run.cluster_count,
            "finalists": run.finalist_count,
        },
        "cost": {
            "gemini_calls": run.gemini_calls,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "estimated_usd": run.estimated_usd,
        },
        "warnings": _loads(run.warnings_json, []),
        # Phase 2B: the human decision is part of the provenance.
        "approval": approval,
    }


__all__ = [
    "TopicReviewService", "ReviewError", "review_status", "candidate_view",
    "ranked_topic_from_rows", "approval_bundle", "decode_audit", "encode_audit",
    "audit_entry", "IN_PIPELINE_STATUSES", "REVIEW_PENDING", "REVIEW_APPROVED",
    "REVIEW_REJECTED", "REVIEW_SUPERSEDED", "REVIEW_NONE",
]
