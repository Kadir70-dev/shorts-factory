"""
The deterministic ranker — the fallback and the floor.

It is a complete, self-sufficient ranker: pure code, no network, no model. When
Gemini is disabled, over budget, or down, this produces a real, defensible ranking
so the system keeps working. It also produces the angle/hook/why-now text via
simple templates, so a fallback run still hands the Director something usable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config_types import ChannelBrief
from ..models import (
    AssetClass,
    CostReport,
    EventType,
    FactualState,
    RankedTopic,
    TopicCandidate,
)
from ..scoring import explain, load_config, recompute_overall

_ANGLE_BY_STATE = {
    FactualState.confirmed: "Explain what just happened and the one number that matters",
    FactualState.forecast: "Set up what is coming and what each outcome would mean",
    FactualState.expectation: "Explain what the market is pricing in and why",
    FactualState.opinion: "Cut through the takes and explain the underlying mechanism",
    FactualState.historical: "Explain the mechanism using a concrete past example",
    FactualState.rumour: "Explain what is actually confirmed versus merely claimed",
    FactualState.unknown: "Explain the story and why it matters to US investors",
}
# Only used when the event is CONFIRMED — these hooks assert that something
# happened, and asserting that about a forecast would be exactly the misleading
# certainty the safety gate exists to prevent.
_HOOK_BY_CONFIRMED_EVENT = {
    EventType.fed_decision: "The Fed just moved. Here is what it actually changes.",
    EventType.cpi: "Inflation came in — and this is the number that matters.",
    EventType.pce: "The Fed's preferred inflation gauge just landed.",
    EventType.nonfarm_payrolls: "The jobs report just hit. Here is the part that moves markets.",
    EventType.earnings: "These earnings just reset expectations.",
    EventType.price_move: "This move is bigger than it looks. Here is why.",
    EventType.treasury: "Yields moved — and that changes everything downstream.",
}

# Safe for any factual state: curious, specific, and asserting nothing.
_HOOK_BY_STATE = {
    FactualState.forecast: "This lands soon — and here is what each outcome means.",
    FactualState.expectation: "Markets have already priced this in. Here is how.",
    FactualState.opinion: "Everyone has a take. Here is the mechanism underneath it.",
    FactualState.historical: "Most people get this wrong in about ten seconds.",
    FactualState.rumour: "Here is what is actually confirmed — and what is not.",
    FactualState.unknown: "Here is what actually changed, in 30 seconds.",
}


def _target_viewer(c: TopicCandidate, brief: ChannelBrief) -> str:
    if AssetClass.market_structure in c.asset_classes:
        return "Traders curious about how markets actually work under the hood"
    if AssetClass.crypto in c.asset_classes:
        return "US retail investors following digital assets"
    if c.event_type in {EventType.cpi, EventType.pce, EventType.fed_decision}:
        return "US investors who track the Fed and inflation data"
    return brief.target_audience


def _why_now(c: TopicCandidate) -> str:
    bits: list[str] = []
    if c.last_seen:
        last = c.last_seen if c.last_seen.tzinfo else c.last_seen.replace(tzinfo=timezone.utc)
        hours = max(0.0, (datetime.now(timezone.utc) - last).total_seconds() / 3600.0)
        bits.append(f"newest source is {hours:.1f}h old")
    if c.scheduled_event_at:
        bits.append(f"scheduled event at {c.scheduled_event_at.isoformat()}")
    bits.append(
        f"{c.independent_source_count} independent source(s) across "
        f"{c.provider_count} provider(s)"
    )
    if "views_per_hour" in c.metrics:
        bits.append(f"{c.metrics['views_per_hour']:.0f} competing views/hour on YouTube")
    return "; ".join(bits)


def _publish_window(c: TopicCandidate) -> datetime | None:
    """When this should go out. Hard news: now. Scheduled release: just after it."""
    now = datetime.now(timezone.utc)
    if c.scheduled_event_at:
        sched = c.scheduled_event_at
        if sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)
        return sched + timedelta(minutes=45) if sched > now else now
    if c.factual_state is FactualState.confirmed:
        return now
    if c.factual_state is FactualState.historical:
        return None            # evergreen — no window
    return now + timedelta(hours=1)


def _confidence(c: TopicCandidate) -> float:
    """How much do we trust this candidate's own inputs? Independent corroboration
    and provider diversity raise it; rumour status and thin evidence lower it."""
    conf = 0.30
    conf += min(0.30, 0.10 * c.independent_source_count)
    conf += min(0.20, 0.07 * c.provider_count)
    conf += 0.15 * (c.deterministic_scores.credibility / 100.0)
    if c.factual_state is FactualState.rumour:
        conf -= 0.25
    if not any(e.url for e in c.evidence):
        conf -= 0.15
    return round(max(0.0, min(1.0, conf)), 3)


def _hook_for(c: TopicCandidate) -> str:
    """A hook that never asserts more than the evidence does."""
    if c.factual_state is FactualState.confirmed:
        hook = _HOOK_BY_CONFIRMED_EVENT.get(c.event_type)
        if hook:
            return hook
    if c.event_type is EventType.education:
        return _HOOK_BY_STATE[FactualState.historical]
    return _HOOK_BY_STATE.get(c.factual_state, _HOOK_BY_STATE[FactualState.unknown])


def to_ranked(c: TopicCandidate, brief: ChannelBrief) -> RankedTopic:
    cfg = load_config()
    scores = c.deterministic_scores.model_copy(deep=True)
    scores.overall_score = recompute_overall(scores, cfg)
    return RankedTopic(
        topic_id=c.topic_id,
        canonical_topic=c.canonical_topic,
        proposed_angle=_ANGLE_BY_STATE.get(c.factual_state, _ANGLE_BY_STATE[FactualState.unknown]),
        target_viewer=_target_viewer(c, brief),
        hook_concept=_hook_for(c),
        why_now=_why_now(c),
        scores=scores,
        supporting_evidence=list(c.evidence[:12]),
        source_names=list(c.source_names),
        source_count=c.source_count,
        confidence=_confidence(c),
        expires_at=c.expires_at,
        recommended_publish_window=_publish_window(c),
        risk_flags=list(c.risk_flags),
        rejection_reasons=list(c.rejection_reasons),
        ranker="deterministic",
        eligible_for_production=c.eligible_for_production,
        score_explanation=explain(scores, cfg),
    )


class DeterministicRanker:
    name = "deterministic"

    async def rank(
        self, candidates: list[TopicCandidate], *, brief: ChannelBrief
    ) -> tuple[list[RankedTopic], CostReport, list[str]]:
        ranked = [to_ranked(c, brief) for c in candidates]
        ranked.sort(key=lambda r: -r.scores.overall_score)
        return ranked, CostReport(), []
