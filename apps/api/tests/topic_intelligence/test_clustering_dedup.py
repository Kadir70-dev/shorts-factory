"""
Normalization, clustering and dedup tests (requirements 3, 4, 5, 6).

  3. Reddit popularity is not treated as factual verification.
  4. Duplicate topics are merged.
  5. Forecast and confirmed events remain separate.
  6. Previously published topics are rejected.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.topic_intelligence import dedup, safety
from app.topic_intelligence.clustering import cluster_signals, text_similarity
from app.topic_intelligence.models import FactualState, SourceTier
from app.topic_intelligence.normalizer import canonical_key, normalize_all
from app.topic_intelligence.tables import TopicLedger

from .fixtures import (
    ALL_SIGNALS,
    BITCOIN_SIGNALS,
    CPI_CONFIRMED_SIGNALS,
    CPI_FORECAST_SIGNALS,
    FOMC_SIGNALS,
    NOW,
    REDDIT_RUMOUR_SIGNALS,
    SYNDICATED_SIGNALS,
)


def _cluster(signals):
    return cluster_signals(normalize_all(signals, now=NOW), now=NOW)


# --------------------------------------------------------------------------- #
# 3. Reddit popularity != verification
# --------------------------------------------------------------------------- #
def test_reddit_popularity_is_not_factual_verification():
    """24,000 upvotes must not buy credibility or eligibility."""
    normalized = normalize_all(REDDIT_RUMOUR_SIGNALS, now=NOW)
    for n in normalized:
        assert n.source_tier is SourceTier.social
        assert n.credibility <= 0.25, "social tier credibility must stay capped"
        # Engagement is preserved as a metric, never promoted to evidence quality.
        assert n.normalized_metrics["upvote_velocity"] > 0

    candidates = _cluster(REDDIT_RUMOUR_SIGNALS)
    safety.apply(candidates)
    rumour = candidates[0]

    assert rumour.factual_state is FactualState.rumour
    assert rumour.eligible_for_production is False
    assert "social_only_rumour" in rumour.risk_flags
    assert any("popularity is not verification" in r for r in rumour.rejection_reasons)


def test_high_engagement_does_not_raise_credibility_score():
    from app.topic_intelligence.scoring import credibility, load_config

    cfg = load_config()
    low = _cluster(REDDIT_RUMOUR_SIGNALS)[0]
    boosted = _cluster([
        s.model_copy(update={"engagement": {"score": 999999.0, "comments": 50000.0}})
        for s in REDDIT_RUMOUR_SIGNALS
    ])[0]
    assert credibility(low, cfg) == credibility(boosted, cfg)


def test_social_only_factual_claim_is_penalized():
    """A confirmed-sounding claim with only Reddit behind it is not confirmed."""
    claim = REDDIT_RUMOUR_SIGNALS[0].model_copy(update={
        "title": "Bank of America officially announced a merger, confirmed today",
        "summary": "Reported by a user.",
    })
    c = _cluster([claim])[0]
    assert c.factual_state is FactualState.confirmed
    v = safety.evaluate(c)
    assert "unconfirmed_factual_claim" in v.risk_flags
    assert v.risk_penalty >= 30.0


# --------------------------------------------------------------------------- #
# 4. Duplicate topics are merged
# --------------------------------------------------------------------------- #
def test_paraphrases_of_one_event_merge_into_one_cluster():
    candidates = _cluster(FOMC_SIGNALS)
    assert len(candidates) == 1, [c.canonical_topic for c in candidates]
    c = candidates[0]
    assert c.source_count == len(FOMC_SIGNALS)
    # Cross-provider aggregation: news + youtube both contributed.
    assert set(c.source_names) == {"finance_news", "youtube"}
    assert c.provider_count == 2
    # The primary source is retained in the evidence bundle.
    from app.topic_intelligence.entities import host_of

    assert "federalreserve.gov" in {host_of(e.url) for e in c.evidence}
    # ...and it is what represents the cluster (highest credibility wins).
    assert c.canonical_topic.lower().startswith("federal reserve")


def test_syndicated_copies_count_as_one_independent_source():
    """Six outlets running one wire story is ONE confirmation, not six."""
    c = _cluster(SYNDICATED_SIGNALS)[0]
    assert c.source_count == 6
    assert c.independent_source_count == 1, (
        "identical syndicated copies must collapse to a single independent source"
    )
    assert c.metrics["independent_sources"] == 1.0


def test_unrelated_stories_do_not_merge():
    candidates = _cluster(FOMC_SIGNALS + BITCOIN_SIGNALS)
    topics = [c.canonical_topic.lower() for c in candidates]
    assert len(candidates) == 2, topics
    assert any("fed" in t or "rate" in t for t in topics)
    assert any("bitcoin" in t for t in topics)


def test_similarity_is_symmetric_and_bounded():
    a = "Fed cuts rates"
    b = "FOMC rate reduction"
    assert text_similarity(a, b) == text_similarity(b, a)
    assert 0.0 <= text_similarity(a, b) <= 1.0
    assert text_similarity(a, a) > text_similarity(a, "Bitcoin hits a record high")


# --------------------------------------------------------------------------- #
# 5. Forecast vs confirmed must never merge
# --------------------------------------------------------------------------- #
def test_forecast_and_confirmed_events_stay_separate():
    candidates = _cluster(CPI_FORECAST_SIGNALS + CPI_CONFIRMED_SIGNALS)
    states = {c.factual_state for c in candidates}
    assert len(candidates) == 2, [
        (c.canonical_topic, c.factual_state.value) for c in candidates
    ]
    assert FactualState.forecast in states
    assert FactualState.confirmed in states


def test_expectation_is_not_confirmation():
    from app.topic_intelligence.normalizer import normalize_signal

    expectation = CPI_CONFIRMED_SIGNALS[0].model_copy(update={
        "title": "Markets expect the Fed to cut rates next month",
    })
    confirmed = CPI_CONFIRMED_SIGNALS[0].model_copy(update={
        "title": "Fed officially cuts rates",
    })
    assert normalize_signal(expectation, now=NOW).factual_state is FactualState.expectation
    assert normalize_signal(confirmed, now=NOW).factual_state is FactualState.confirmed

    merged = _cluster([expectation, confirmed])
    assert len(merged) == 2, "an expectation and a confirmation are different facts"


def test_canonical_key_encodes_factual_state():
    assert canonical_key("Fed cuts rates", FactualState.forecast) != \
        canonical_key("Fed cuts rates", FactualState.confirmed)


def test_all_fixture_scenarios_cluster_into_distinct_topics():
    candidates = _cluster(ALL_SIGNALS)
    assert len(candidates) >= 6, [c.canonical_topic for c in candidates]
    joined = " ".join(c.canonical_topic.lower() for c in candidates)
    for expected in ("fed", "cpi", "nvidia", "bitcoin", "high frequency", "treasury"):
        assert expected in joined, f"{expected!r} missing from {joined}"


# --------------------------------------------------------------------------- #
# 6. Previously published topics are rejected
# --------------------------------------------------------------------------- #
def _ledger_row(candidate, *, status="published", days_ago=3, angle=""):
    return TopicLedger(
        channel_id="usa_trading", topic_id=candidate.topic_id,
        canonical_key=canonical_key(candidate.canonical_topic, candidate.factual_state),
        canonical_topic=candidate.canonical_topic, proposed_angle=angle,
        factual_state=candidate.factual_state.value, status=status,
        selected_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def test_previously_published_topic_is_rejected():
    c = _cluster(FOMC_SIGNALS)[0]
    verdict = dedup.check_candidate(c, [_ledger_row(c)])
    assert verdict.blocked is True
    assert verdict.status == "duplicate"
    assert "exact duplicate" in verdict.reasons[0]


def test_queued_and_rendering_topics_also_block():
    c = _cluster(BITCOIN_SIGNALS)[0]
    for status in ("queued", "rendering", "selected"):
        assert dedup.check_candidate(c, [_ledger_row(c, status=status)]).blocked is True


def test_abandoned_ledger_entry_does_not_block():
    c = _cluster(BITCOIN_SIGNALS)[0]
    assert dedup.check_candidate(c, [_ledger_row(c, status="abandoned")]).blocked is False


def test_topic_outside_the_dedup_window_is_reusable():
    c = _cluster(BITCOIN_SIGNALS)[0]
    old = _ledger_row(c, days_ago=400)      # beyond TOPIC_EXACT_DEDUP_DAYS=365
    assert dedup.check_candidate(c, [old]).blocked is False


def test_confirmed_event_supersedes_an_earlier_forecast():
    """A materially new event unlocks a topic the forecast already used."""
    forecast = _cluster(CPI_FORECAST_SIGNALS)[0]
    confirmed = _cluster(CPI_CONFIRMED_SIGNALS)[0]
    row = _ledger_row(forecast)
    # Force the semantic path: same story, different state.
    row.canonical_topic = confirmed.canonical_topic
    row.canonical_key = canonical_key(confirmed.canonical_topic, FactualState.forecast)

    verdict = dedup.check_candidate(confirmed, [row])
    assert verdict.blocked is False
    assert verdict.status == "superseded"
    assert any("materially new" in r for r in verdict.reasons)


def test_admin_override_unblocks_a_duplicate():
    c = _cluster(FOMC_SIGNALS)[0]
    verdict = dedup.check_candidate(c, [_ledger_row(c)], override=True)
    assert verdict.blocked is False
    assert any("ADMIN OVERRIDE" in r for r in verdict.reasons)


def test_apply_dedup_drops_blocked_candidates(ti_repo):
    candidates = _cluster(FOMC_SIGNALS + BITCOIN_SIGNALS)
    fomc = next(c for c in candidates if "fed" in c.canonical_topic.lower()
                or "rate" in c.canonical_topic.lower())

    from app.topic_intelligence.models import RankedTopic

    ti_repo.record_selection(
        channel_id="usa_trading",
        topic=RankedTopic(topic_id=fomc.topic_id,
                          canonical_topic=fomc.canonical_topic),
        candidate=fomc, run_id="run_prev", status="published",
    )
    survivors = dedup.apply_dedup(
        list(candidates), channel_id="usa_trading", repo=ti_repo
    )
    assert fomc.topic_id not in {c.topic_id for c in survivors}
    assert len(survivors) == len(candidates) - 1
