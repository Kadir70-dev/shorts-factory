"""
Domain models for the topic-intelligence engine.

Layering (each stage adds meaning, nothing is destroyed):

    RawTrendSignal      what a provider actually returned  (raw_metrics preserved)
        -> NormalizedSignal   + canonical form, entities, factual state, normalized metrics
        -> TopicCandidate     a cluster of normalized signals = one story
        -> RankedTopic        a scored, explained, production-ready decision

Hard rule encoded here: metrics from different providers are NEVER coerced into a
single shared meaning. `raw_metrics` is verbatim; `normalized_metrics` is a small,
explicitly-named, provider-agnostic vocabulary computed by the normalizer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# Returned (as `selected_topic_id`/status) when nothing credible and safe survives.
# The caller must NOT generate filler content in this case.
NO_SAFE_TOPIC_AVAILABLE = "NO_SAFE_TOPIC_AVAILABLE"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FactualState(str, Enum):
    """What KIND of claim a signal makes. Never merged across states — "markets
    expect a Fed cut" and "the Fed cut rates" are different facts about the world."""

    confirmed = "confirmed"        # it happened; an official/primary source says so
    forecast = "forecast"          # a scheduled release with a published consensus
    expectation = "expectation"    # market pricing / anticipation, not yet fact
    opinion = "opinion"            # analysis, commentary, prediction
    rumour = "rumour"              # unverified claim, typically social
    historical = "historical"      # explainer / evergreen / past event
    unknown = "unknown"


class AssetClass(str, Enum):
    equities = "equities"
    crypto = "crypto"
    gold = "gold"
    oil = "oil"
    forex = "forex"
    rates = "rates"
    macro = "macro"
    ai_tech = "ai_tech"
    market_structure = "market_structure"
    unknown = "unknown"


class EventType(str, Enum):
    fed_decision = "fed_decision"
    fomc_minutes = "fomc_minutes"
    cpi = "cpi"
    pce = "pce"
    nonfarm_payrolls = "nonfarm_payrolls"
    unemployment = "unemployment"
    gdp = "gdp"
    retail_sales = "retail_sales"
    ism = "ism"
    jobless_claims = "jobless_claims"
    treasury = "treasury"
    earnings = "earnings"
    price_move = "price_move"
    regulation = "regulation"
    education = "education"
    other = "other"


class EventStatus(str, Enum):
    scheduled = "scheduled"
    released = "released"
    revised = "revised"
    cancelled = "cancelled"


class SourceTier(str, Enum):
    """Credibility CLASS, not a truth claim. Reddit upvotes never buy a better tier."""

    primary = "primary"            # Fed, BLS, Treasury, SEC, company IR
    wire = "wire"                  # major wires / established financial press
    reputable = "reputable"        # known outlets, secondary reporting
    aggregator = "aggregator"      # syndicators, roundups
    social = "social"              # Reddit / X — interest signal ONLY
    unknown = "unknown"


TIER_CREDIBILITY: dict[SourceTier, float] = {
    SourceTier.primary: 1.0,
    SourceTier.wire: 0.85,
    SourceTier.reputable: 0.7,
    SourceTier.aggregator: 0.45,
    SourceTier.social: 0.25,
    SourceTier.unknown: 0.35,
}


# --------------------------------------------------------------------------- #
# Stage 1 — raw provider output
# --------------------------------------------------------------------------- #
class RawTrendSignal(BaseModel):
    """Exactly what a provider observed. Providers must not interpret."""

    provider: str
    external_id: Optional[str] = None
    title: str
    summary: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=_utcnow)
    region: Optional[str] = None
    # Provider-native engagement, verbatim key names (views/score/likes/…).
    engagement: dict[str, float] = Field(default_factory=dict)
    # Anything else the provider gave us, untouched. Never interpreted downstream
    # except by that provider's own normalizer hook.
    raw_metrics: dict[str, Any] = Field(default_factory=dict)
    author_or_channel: Optional[str] = None
    source_credibility: Optional[float] = None


class EconomicEvent(BaseModel):
    """A scheduled macro event. Values are OPTIONAL and stay None when the provider
    did not publish them — Gemini is never asked to fill these in."""

    name: str
    scheduled_at: datetime
    importance: str = "medium"                 # low | medium | high
    affected_assets: list[AssetClass] = Field(default_factory=list)
    previous_value: Optional[str] = None
    forecast_value: Optional[str] = None
    actual_value: Optional[str] = None
    source: str = ""
    source_url: Optional[str] = None
    status: EventStatus = EventStatus.scheduled


# --------------------------------------------------------------------------- #
# Stage 2 — normalized
# --------------------------------------------------------------------------- #
class NormalizedSignal(BaseModel):
    """A raw signal with canonical text + extracted meaning + a small, comparable
    metric vocabulary. `raw` is retained in full for provenance."""

    raw: RawTrendSignal
    canonical_title: str
    canonical_key: str                          # deterministic dedup key
    entities: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    asset_classes: list[AssetClass] = Field(default_factory=list)
    event_type: EventType = EventType.other
    factual_state: FactualState = FactualState.unknown
    source_tier: SourceTier = SourceTier.unknown
    credibility: float = 0.35
    # Provider-agnostic, explicitly-named metrics. Absent key == not measurable
    # from this provider; NEVER defaulted to a fake number.
    normalized_metrics: dict[str, float] = Field(default_factory=dict)
    age_hours: float = 0.0

    @property
    def provider(self) -> str:
        return self.raw.provider


# --------------------------------------------------------------------------- #
# Stage 3 — candidates
# --------------------------------------------------------------------------- #
class EvidenceItem(BaseModel):
    """One citable observation supporting a candidate. Every field traces to a
    provider response — nothing here may originate from an LLM without being
    flagged via `provider='gemini_grounding'`."""

    provider: str
    title: str
    url: Optional[str] = None
    external_id: Optional[str] = None
    published_at: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=_utcnow)
    source_tier: SourceTier = SourceTier.unknown
    source_credibility: float = 0.35
    excerpt: Optional[str] = None
    metrics: dict[str, float] = Field(default_factory=dict)
    # Set when the item came from Gemini grounding metadata rather than a
    # deterministic provider call.
    grounded: bool = False
    grounding_complete: bool = True


class TopicScores(BaseModel):
    """All dimensions are 0-100 relative scores. `risk_penalty` is subtractive."""

    trend_momentum: float = Field(0.0, ge=0.0, le=100.0)
    audience_relevance: float = Field(0.0, ge=0.0, le=100.0)
    competition_opportunity: float = Field(0.0, ge=0.0, le=100.0)
    freshness: float = Field(0.0, ge=0.0, le=100.0)
    credibility: float = Field(0.0, ge=0.0, le=100.0)
    ctr_potential: float = Field(0.0, ge=0.0, le=100.0)
    retention_potential: float = Field(0.0, ge=0.0, le=100.0)
    subscriber_potential: float = Field(0.0, ge=0.0, le=100.0)
    monetization_potential: float = Field(0.0, ge=0.0, le=100.0)
    production_feasibility: float = Field(0.0, ge=0.0, le=100.0)
    risk_penalty: float = Field(0.0, ge=0.0, le=100.0)
    overall_score: float = Field(0.0, ge=0.0, le=100.0)

    @field_validator("*", mode="before")
    @classmethod
    def _coerce_and_clamp(cls, v: Any) -> Any:
        """Gemini occasionally emits 0-1 floats, strings, or out-of-range values.
        Coerce what is coercible and clamp the rest; validation still rejects
        anything non-numeric."""
        if isinstance(v, str):
            try:
                v = float(v.strip().rstrip("%"))
            except ValueError:
                return v
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return max(0.0, min(100.0, float(v)))
        return v


class TopicCandidate(BaseModel):
    """One clustered story, pre-Gemini. Carries the deterministic truth."""

    topic_id: str
    canonical_topic: str
    factual_state: FactualState = FactualState.unknown
    event_type: EventType = EventType.other
    asset_classes: list[AssetClass] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)

    signals: list[NormalizedSignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    source_count: int = 0
    provider_count: int = 0
    independent_source_count: int = 0     # syndicated copies collapsed

    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    scheduled_event_at: Optional[datetime] = None

    # Deterministic, provider-derived aggregate metrics (views_per_hour, etc.).
    metrics: dict[str, float] = Field(default_factory=dict)
    deterministic_scores: TopicScores = Field(default_factory=TopicScores)

    risk_flags: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    eligible_for_production: bool = True
    dedup_status: str = "new"             # new | duplicate | recent_semantic | requeued

    @property
    def is_stale(self) -> bool:
        return self.expires_at is not None and self.expires_at < _utcnow()


# --------------------------------------------------------------------------- #
# Stage 4 — ranked output
# --------------------------------------------------------------------------- #
class RankedTopic(BaseModel):
    topic_id: str
    canonical_topic: str
    proposed_angle: str = ""
    target_viewer: str = ""
    hook_concept: str = ""
    why_now: str = ""
    scores: TopicScores = Field(default_factory=TopicScores)
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    source_count: int = 0
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    expires_at: Optional[datetime] = None
    recommended_publish_window: Optional[datetime] = None
    risk_flags: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    # Bookkeeping — not part of the LLM contract, filled by our code.
    ranker: str = "deterministic"
    eligible_for_production: bool = True
    score_explanation: str = ""


class GeminiTopicVerdict(BaseModel):
    """The SHAPE we accept from Gemini. Note what is absent: no overall_score, no
    evidence, no metrics, no source list. Gemini judges; it does not report facts."""

    topic_id: str
    proposed_angle: str = ""
    target_viewer: str = ""
    hook_concept: str = ""
    why_now: str = ""
    score_explanation: str = ""
    confidence: float = 0.5
    risk_flags: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    recommended_publish_window: Optional[datetime] = None
    # Qualitative judgements ONLY. Deterministic dimensions are ignored if present.
    audience_relevance: Optional[float] = None
    ctr_potential: Optional[float] = None
    retention_potential: Optional[float] = None
    subscriber_potential: Optional[float] = None
    monetization_potential: Optional[float] = None
    production_feasibility: Optional[float] = None
    cited_source_names: list[str] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                v = float(v.strip())
            except ValueError:
                return 0.5
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            f = float(v)
            if f > 1.0:            # model answered on a 0-100 scale
                f /= 100.0
            return max(0.0, min(1.0, f))
        return v

    @field_validator(
        "audience_relevance", "ctr_potential", "retention_potential",
        "subscriber_potential", "monetization_potential", "production_feasibility",
        mode="before",
    )
    @classmethod
    def _score_field(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            try:
                v = float(v.strip().rstrip("%"))
            except ValueError:
                return None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return max(0.0, min(100.0, float(v)))
        return None


class GeminiRankingResponse(BaseModel):
    ranked: list[GeminiTopicVerdict] = Field(default_factory=list)
    notes: str = ""


# --------------------------------------------------------------------------- #
# Run bookkeeping
# --------------------------------------------------------------------------- #
class ProviderStatus(BaseModel):
    name: str
    enabled: bool = False
    configured: bool = False
    ok: bool = False
    signal_count: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None
    circuit_open: bool = False
    stale: bool = False
    skipped_reason: Optional[str] = None


class CostReport(BaseModel):
    gemini_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_usd: float = 0.0
    budget_usd: float = 0.0
    budget_exhausted: bool = False


class SelectionResult(BaseModel):
    """The complete, persistable decision for one run."""

    run_id: str
    channel_id: str
    status: str = "ok"                      # ok | NO_SAFE_TOPIC_AVAILABLE
    selected: Optional[RankedTopic] = None
    ranked: list[RankedTopic] = Field(default_factory=list)
    rejected: list[RankedTopic] = Field(default_factory=list)
    providers: list[ProviderStatus] = Field(default_factory=list)
    cost: CostReport = Field(default_factory=CostReport)
    ranker_used: str = "deterministic"
    gemini_model: Optional[str] = None
    prompt_version: str = ""
    ranking_version: str = ""
    raw_signal_count: int = 0
    cluster_count: int = 0
    finalist_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None
    enqueued_job_id: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.selected is not None
