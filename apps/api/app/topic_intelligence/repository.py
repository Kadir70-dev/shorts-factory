"""
Persistence for topic intelligence — the same SQLModel/SQLite setup the rest of
the app uses (`app.db._engine`), just additive tables.

`init_ti_db()` is idempotent and safe to call from the API lifespan, the CLI, or a
test; it only ever CREATEs missing tables.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlmodel import Session, select

from ..db import _engine, get_session
from .models import (
    CostReport,
    FactualState,
    ProviderStatus,
    RankedTopic,
    SelectionResult,
    TopicCandidate,
)
from .tables import (
    TI_TABLES,
    ProviderRun,
    TopicCandidateRow,
    TopicEvidence,
    TopicLedger,
    TopicRankingResult,
    TopicRankingRun,
    TrendSignal,
)


def init_ti_db() -> None:
    """Create the topic-intelligence tables if absent. Never alters existing ones."""
    from sqlmodel import SQLModel

    SQLModel.metadata.create_all(
        _engine, tables=[t.__table__ for t in TI_TABLES]
    )


def _csv(values: Iterable) -> str:
    return ",".join(str(getattr(v, "value", v)) for v in values)


def _dt(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite round-trips naive datetimes; normalize everything to aware UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class TopicIntelligenceRepository:
    """All reads/writes for the engine. One instance per run; sessions are short."""

    def __init__(self, session_factory=get_session) -> None:
        self._session_factory = session_factory
        init_ti_db()

    # ------------------------------------------------------------------ writes
    def save_provider_runs(self, run_id: str, statuses: list[ProviderStatus]) -> None:
        with self._session_factory() as s:
            for st in statuses:
                s.add(ProviderRun(
                    run_id=run_id, provider=st.name, enabled=st.enabled,
                    configured=st.configured, ok=st.ok,
                    signal_count=st.signal_count, latency_ms=st.latency_ms,
                    circuit_open=st.circuit_open, stale=st.stale,
                    error=st.error, skipped_reason=st.skipped_reason,
                ))
            s.commit()

    def save_candidates(
        self, run_id: str, channel_id: str, candidates: list[TopicCandidate]
    ) -> None:
        """Persists candidates, every underlying signal, and the evidence ledger."""
        with self._session_factory() as s:
            for c in candidates:
                s.add(TopicCandidateRow(
                    run_id=run_id, topic_id=c.topic_id, channel_id=channel_id,
                    canonical_topic=c.canonical_topic,
                    factual_state=c.factual_state.value,
                    event_type=c.event_type.value,
                    asset_classes=_csv(c.asset_classes),
                    tickers=_csv(c.tickers), entities=_csv(c.entities),
                    source_count=c.source_count, provider_count=c.provider_count,
                    independent_source_count=c.independent_source_count,
                    source_names=_csv(c.source_names),
                    first_seen=c.first_seen, last_seen=c.last_seen,
                    expires_at=c.expires_at,
                    metrics_json=json.dumps(c.metrics),
                    deterministic_scores_json=c.deterministic_scores.model_dump_json(),
                    risk_flags=_csv(c.risk_flags),
                    rejection_reasons=" | ".join(c.rejection_reasons),
                    eligible_for_production=c.eligible_for_production,
                    dedup_status=c.dedup_status,
                ))
                for sig in c.signals:
                    s.add(TrendSignal(
                        run_id=run_id, provider=sig.provider,
                        external_id=sig.raw.external_id, title=sig.raw.title,
                        canonical_title=sig.canonical_title,
                        canonical_key=sig.canonical_key, url=sig.raw.url,
                        published_at=sig.raw.published_at,
                        collected_at=sig.raw.collected_at, region=sig.raw.region,
                        source_tier=sig.source_tier.value, credibility=sig.credibility,
                        factual_state=sig.factual_state.value,
                        event_type=sig.event_type.value, topic_id=c.topic_id,
                        engagement_json=json.dumps(sig.raw.engagement),
                        raw_metrics_json=json.dumps(sig.raw.raw_metrics, default=str),
                        normalized_metrics_json=json.dumps(sig.normalized_metrics),
                    ))
                for ev in c.evidence:
                    s.add(TopicEvidence(
                        run_id=run_id, topic_id=c.topic_id, provider=ev.provider,
                        title=ev.title, url=ev.url, external_id=ev.external_id,
                        published_at=ev.published_at, collected_at=ev.collected_at,
                        source_tier=ev.source_tier.value,
                        source_credibility=ev.source_credibility,
                        excerpt=ev.excerpt, metrics_json=json.dumps(ev.metrics),
                        grounded=ev.grounded,
                        grounding_complete=ev.grounding_complete,
                    ))
            s.commit()

    def save_run(self, result: SelectionResult) -> None:
        with self._session_factory() as s:
            s.merge(TopicRankingRun(
                run_id=result.run_id, channel_id=result.channel_id,
                status=result.status, ranker_used=result.ranker_used,
                gemini_model=result.gemini_model,
                prompt_version=result.prompt_version,
                ranking_version=result.ranking_version,
                raw_signal_count=result.raw_signal_count,
                cluster_count=result.cluster_count,
                finalist_count=result.finalist_count,
                selected_topic_id=result.selected.topic_id if result.selected else None,
                enqueued_job_id=result.enqueued_job_id,
                gemini_calls=result.cost.gemini_calls,
                input_tokens=result.cost.input_tokens,
                output_tokens=result.cost.output_tokens,
                estimated_usd=result.cost.estimated_usd,
                budget_exhausted=result.cost.budget_exhausted,
                warnings_json=json.dumps(result.warnings),
                started_at=result.started_at, finished_at=result.finished_at,
            ))
            selected_id = result.selected.topic_id if result.selected else None
            for i, rt in enumerate(list(result.ranked) + list(result.rejected)):
                s.add(TopicRankingResult(
                    run_id=result.run_id, topic_id=rt.topic_id, rank=i,
                    canonical_topic=rt.canonical_topic,
                    proposed_angle=rt.proposed_angle,
                    target_viewer=rt.target_viewer, hook_concept=rt.hook_concept,
                    why_now=rt.why_now, scores_json=rt.scores.model_dump_json(),
                    overall_score=rt.scores.overall_score, confidence=rt.confidence,
                    ranker=rt.ranker, selected=rt.topic_id == selected_id,
                    eligible_for_production=rt.eligible_for_production,
                    risk_flags=_csv(rt.risk_flags),
                    rejection_reasons=" | ".join(rt.rejection_reasons),
                    score_explanation=rt.score_explanation[:2000],
                    recommended_publish_window=rt.recommended_publish_window,
                    expires_at=rt.expires_at,
                ))
            s.commit()

    def record_selection(
        self,
        *,
        channel_id: str,
        topic: RankedTopic,
        candidate: TopicCandidate | None,
        run_id: str,
        job_id: str | None = None,
        status: str = "selected",
        override_reason: str | None = None,
    ) -> None:
        """Append to the ledger — this is what makes the topic un-reusable."""
        from .normalizer import canonical_key

        state = candidate.factual_state if candidate else None
        with self._session_factory() as s:
            s.add(TopicLedger(
                channel_id=channel_id, topic_id=topic.topic_id,
                canonical_key=canonical_key(
                    topic.canonical_topic, state or FactualState.unknown
                ),
                canonical_topic=topic.canonical_topic,
                proposed_angle=topic.proposed_angle,
                hook_concept=topic.hook_concept,
                factual_state=state.value if state else "unknown",
                event_type=candidate.event_type.value if candidate else "other",
                tickers=_csv(candidate.tickers) if candidate else "",
                status=status, job_id=job_id, run_id=run_id,
                overall_score=topic.scores.overall_score,
                override_reason=override_reason,
            ))
            s.commit()

    def mark_ledger_status(self, topic_id: str, status: str) -> None:
        with self._session_factory() as s:
            rows = list(s.exec(select(TopicLedger).where(TopicLedger.topic_id == topic_id)))
            for r in rows:
                r.status = status
                if status == "published":
                    r.published_at = datetime.now(timezone.utc)
                s.add(r)
            s.commit()

    # ------------------------------------------------------------------- reads
    def ledger_entries(
        self, channel_id: str, *, days: int, statuses: tuple[str, ...] | None = None
    ) -> list[TopicLedger]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._session_factory() as s:
            stmt = select(TopicLedger).where(TopicLedger.channel_id == channel_id)
            rows = [r for r in s.exec(stmt) if _dt(r.selected_at) >= cutoff]
        if statuses:
            rows = [r for r in rows if r.status in statuses]
        return rows

    def get_run(self, run_id: str) -> Optional[TopicRankingRun]:
        with self._session_factory() as s:
            return s.get(TopicRankingRun, run_id)

    def run_results(self, run_id: str) -> list[TopicRankingResult]:
        with self._session_factory() as s:
            stmt = select(TopicRankingResult).where(
                TopicRankingResult.run_id == run_id
            ).order_by(TopicRankingResult.rank)
            return list(s.exec(stmt))

    def candidates(
        self, *, channel_id: str | None = None, run_id: str | None = None,
        limit: int = 50,
    ) -> list[TopicCandidateRow]:
        with self._session_factory() as s:
            stmt = select(TopicCandidateRow)
            if channel_id:
                stmt = stmt.where(TopicCandidateRow.channel_id == channel_id)
            if run_id:
                stmt = stmt.where(TopicCandidateRow.run_id == run_id)
            stmt = stmt.order_by(TopicCandidateRow.id.desc()).limit(limit)
            return list(s.exec(stmt))

    def candidate(self, topic_id: str) -> Optional[TopicCandidateRow]:
        with self._session_factory() as s:
            stmt = select(TopicCandidateRow).where(
                TopicCandidateRow.topic_id == topic_id
            ).order_by(TopicCandidateRow.id.desc()).limit(1)
            return next(iter(s.exec(stmt)), None)

    def evidence_for(self, topic_id: str, run_id: str | None = None) -> list[TopicEvidence]:
        with self._session_factory() as s:
            stmt = select(TopicEvidence).where(TopicEvidence.topic_id == topic_id)
            if run_id:
                stmt = stmt.where(TopicEvidence.run_id == run_id)
            return list(s.exec(stmt))

    def provider_runs(self, run_id: str) -> list[ProviderRun]:
        with self._session_factory() as s:
            stmt = select(ProviderRun).where(ProviderRun.run_id == run_id)
            return list(s.exec(stmt))

    def latest_provider_runs(self, limit: int = 40) -> list[ProviderRun]:
        with self._session_factory() as s:
            stmt = select(ProviderRun).order_by(ProviderRun.id.desc()).limit(limit)
            return list(s.exec(stmt))

    def spend_since(self, since: datetime) -> float:
        """Total estimated Gemini spend since `since` — the daily budget guard."""
        with self._session_factory() as s:
            rows = list(s.exec(select(TopicRankingRun)))
        return round(
            sum(r.estimated_usd for r in rows if _dt(r.started_at) >= since), 6
        )


__all__ = [
    "TopicIntelligenceRepository", "init_ti_db", "CostReport", "Session",
]
