"""
Additive SQLModel tables for topic intelligence.

Design constraints:
  * PURELY ADDITIVE — the existing `Job` table is not touched and its JSON blobs
    are not overloaded with trend data.
  * SQLite-compatible (str/float/int/datetime only; structured payloads are TEXT
    holding JSON). Right-sized for ~3 videos/day; no premature Postgres rewrite.
  * `SQLModel.metadata.create_all()` is the whole migration: new tables appear,
    existing tables are untouched. Rollback = drop the tables (or just leave them;
    nothing else reads them).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderRun(SQLModel, table=True):
    """One provider's outcome inside one collection run — the health ledger."""

    __tablename__ = "ti_provider_run"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    provider: str = Field(index=True)
    enabled: bool = False
    configured: bool = False
    ok: bool = False
    signal_count: int = 0
    latency_ms: float = 0.0
    circuit_open: bool = False
    stale: bool = False
    error: Optional[str] = None
    skipped_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class TrendSignal(SQLModel, table=True):
    """A raw+normalized signal, retained for provenance and audit."""

    __tablename__ = "ti_trend_signal"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    provider: str = Field(index=True)
    external_id: Optional[str] = Field(default=None, index=True)
    title: str = ""
    canonical_title: str = ""
    canonical_key: str = Field(default="", index=True)
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=_now)
    region: Optional[str] = None
    source_tier: str = "unknown"
    credibility: float = 0.35
    factual_state: str = "unknown"
    event_type: str = "other"
    topic_id: Optional[str] = Field(default=None, index=True)
    engagement_json: str = "{}"
    raw_metrics_json: str = "{}"
    normalized_metrics_json: str = "{}"


class TopicCandidateRow(SQLModel, table=True):
    """A clustered candidate with its deterministic scores and dedup verdict."""

    __tablename__ = "ti_topic_candidate"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    topic_id: str = Field(index=True)
    channel_id: str = Field(index=True)
    canonical_topic: str = ""
    factual_state: str = "unknown"
    event_type: str = "other"
    asset_classes: str = ""              # comma-separated
    tickers: str = ""
    entities: str = ""
    source_count: int = 0
    provider_count: int = 0
    independent_source_count: int = 0
    source_names: str = ""
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metrics_json: str = "{}"
    deterministic_scores_json: str = "{}"
    risk_flags: str = ""
    rejection_reasons: str = ""
    eligible_for_production: bool = True
    dedup_status: str = "new"
    created_at: datetime = Field(default_factory=_now)


class TopicEvidence(SQLModel, table=True):
    """The citation ledger. Every row traces a candidate back to a real fetch."""

    __tablename__ = "ti_topic_evidence"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    topic_id: str = Field(index=True)
    provider: str = ""
    title: str = ""
    url: Optional[str] = None
    external_id: Optional[str] = None
    published_at: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=_now)
    source_tier: str = "unknown"
    source_credibility: float = 0.35
    excerpt: Optional[str] = None
    metrics_json: str = "{}"
    grounded: bool = False
    grounding_complete: bool = True


class TopicRankingRun(SQLModel, table=True):
    """One end-to-end decision. The audit root."""

    __tablename__ = "ti_ranking_run"

    run_id: str = Field(primary_key=True)
    channel_id: str = Field(index=True)
    status: str = "ok"
    ranker_used: str = "deterministic"
    gemini_model: Optional[str] = None
    prompt_version: str = ""
    ranking_version: str = ""
    raw_signal_count: int = 0
    cluster_count: int = 0
    finalist_count: int = 0
    selected_topic_id: Optional[str] = None
    enqueued_job_id: Optional[str] = None
    gemini_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_usd: float = 0.0
    budget_exhausted: bool = False
    warnings_json: str = "[]"
    started_at: datetime = Field(default_factory=_now)
    finished_at: Optional[datetime] = None


class TopicRankingResult(SQLModel, table=True):
    """Per-candidate ranking outcome, including WHY a candidate lost."""

    __tablename__ = "ti_ranking_result"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    topic_id: str = Field(index=True)
    rank: int = 0
    canonical_topic: str = ""
    proposed_angle: str = ""
    target_viewer: str = ""
    hook_concept: str = ""
    why_now: str = ""
    scores_json: str = "{}"
    overall_score: float = 0.0
    confidence: float = 0.0
    ranker: str = "deterministic"
    selected: bool = False
    eligible_for_production: bool = True
    risk_flags: str = ""
    rejection_reasons: str = ""
    score_explanation: str = ""
    recommended_publish_window: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_now)


class TopicLedger(SQLModel, table=True):
    """What this channel has ALREADY committed to — the dedup memory.

    One row per topic the channel selected (and later published). Queried on every
    run to reject repeats. Kept separate from `Job` so a purged job history does
    not silently make old topics reusable.
    """

    __tablename__ = "ti_topic_ledger"

    id: Optional[int] = Field(default=None, primary_key=True)
    channel_id: str = Field(index=True)
    topic_id: str = Field(index=True)
    canonical_key: str = Field(default="", index=True)
    canonical_topic: str = ""
    proposed_angle: str = ""
    hook_concept: str = ""
    factual_state: str = "unknown"
    event_type: str = "other"
    tickers: str = ""
    status: str = "selected"     # selected | queued | rendering | published | abandoned
    job_id: Optional[str] = Field(default=None, index=True)
    run_id: Optional[str] = None
    overall_score: float = 0.0
    override_reason: Optional[str] = None
    selected_at: datetime = Field(default_factory=_now)
    published_at: Optional[datetime] = None


TI_TABLES = (
    ProviderRun, TrendSignal, TopicCandidateRow, TopicEvidence,
    TopicRankingRun, TopicRankingResult, TopicLedger,
)
