"""
Safety gate, provenance and end-to-end run tests (requirements 12, 13, 16, 17).

 12. Unsafe financial-advice topics are rejected.
 13. Evidence provenance is persisted.
 16. A complete mock run selects exactly one eligible topic.
 17. No eligible candidate returns NO_SAFE_TOPIC_AVAILABLE.
"""
from __future__ import annotations

import json

import pytest

from app.topic_intelligence import safety
from app.topic_intelligence.clustering import cluster_signals
from app.topic_intelligence.models import NO_SAFE_TOPIC_AVAILABLE
from app.topic_intelligence.normalizer import normalize_all
from app.topic_intelligence.service import TopicIntelligenceService
from app.topic_intelligence.settings import TopicIntelligenceSettings

from .conftest import StubGeminiClient, StubProvider
from .fixtures import (
    ALL_SIGNALS,
    BITCOIN_SIGNALS,
    FOMC_SIGNALS,
    HFT_SIGNALS,
    NOW,
    NVDA_SIGNALS,
    REDDIT_RUMOUR_SIGNALS,
    UNSAFE_SIGNALS,
)


def _cluster(signals):
    return cluster_signals(normalize_all(signals, now=NOW), now=NOW)


def _settings(**over) -> TopicIntelligenceSettings:
    defaults = dict(
        gemini_api_key="", gemini_ranker_enabled=False,
        gemini_grounding_enabled=False, ti_auto_enqueue=False,
    )
    defaults.update(over)
    return TopicIntelligenceSettings(**defaults)


def _service(repo, signals, **over) -> TopicIntelligenceService:
    s = _settings(**over)
    return TopicIntelligenceService(
        settings=s, repo=repo,
        providers=[StubProvider("finance_news", signals, settings=s)],
    )


# --------------------------------------------------------------------------- #
# 12. unsafe financial-advice topics
# --------------------------------------------------------------------------- #
def test_financial_advice_topic_is_blocked():
    c = _cluster(UNSAFE_SIGNALS)[0]
    v = safety.evaluate(c)
    assert v.eligible is False
    assert v.risk_penalty == 100.0
    assert {"guaranteed_profit", "financial_advice", "pump_and_dump"} & set(v.risk_flags)
    assert any(r.startswith("BLOCKED:") for r in v.reasons)


@pytest.mark.parametrize("headline,flag", [
    ("This guaranteed risk-free trade never loses", "guaranteed_profit"),
    ("You should buy now before it explodes", "financial_advice"),
    ("This coin is going to the moon, next 100x", "pump_and_dump"),
    ("The market is rigged and banks are manipulating gold", "manipulation_allegation"),
    ("Trade on inside information from non-public information", "insider_trading"),
    ("Bitcoin will crash to zero next week", "prediction_as_fact"),
])
def test_each_blocking_rule_fires(headline, flag):
    sig = BITCOIN_SIGNALS[0].model_copy(update={"title": headline, "summary": None})
    c = _cluster([sig])[0]
    v = safety.evaluate(c)
    assert v.eligible is False
    assert flag in v.risk_flags


def test_personal_finance_advice_columns_are_heavily_demoted():
    """Retelling "I'm 71 and inherited $20,000 — what should I do?" is one step
    from giving the advice ourselves."""
    sig = NVDA_SIGNALS[0].model_copy(update={
        "title": "I'm 71 and inherited $20,000. What should I do with the money?",
        "summary": "My financial adviser is against a withdrawal plan.",
    })
    c = _cluster([sig])[0]
    v = safety.evaluate(c)
    assert "advice_column" in v.risk_flags
    assert v.risk_penalty >= 30.0


def test_deterministic_hook_never_asserts_an_unconfirmed_event():
    """The fallback ranker can actually ship — its hook must not claim a forecast
    already happened."""
    from app.topic_intelligence.config_types import ChannelBrief
    from app.topic_intelligence.models import FactualState
    from app.topic_intelligence.rankers.deterministic import to_ranked
    from app.topic_intelligence.scoring import score_all

    from .fixtures import CPI_FORECAST_SIGNALS

    brief = ChannelBrief(channel_id="usa_trading")
    forecast = score_all(_cluster(CPI_FORECAST_SIGNALS), now=NOW)[0]
    assert forecast.factual_state is FactualState.forecast
    hook = to_ranked(forecast, brief).hook_concept
    for asserted in ("just landed", "just hit", "just moved", "came in"):
        assert asserted not in hook.lower(), hook

    confirmed = score_all(_cluster(FOMC_SIGNALS), now=NOW)[0]
    assert confirmed.factual_state is FactualState.confirmed
    assert "just moved" in to_ranked(confirmed, brief).hook_concept.lower()


def test_penalty_rules_reduce_but_do_not_block():
    sig = NVDA_SIGNALS[0].model_copy(update={
        "title": "Shocking: the truth about Nvidia nobody is talking about",
    })
    c = _cluster([sig])[0]
    v = safety.evaluate(c)
    assert v.eligible is True
    assert v.risk_penalty > 0
    assert "sensational" in v.risk_flags


def test_apply_stamps_every_candidate():
    cands = _cluster(FOMC_SIGNALS + UNSAFE_SIGNALS)
    safety.apply(cands)
    for c in cands:
        assert isinstance(c.risk_flags, list)
        assert 0.0 <= c.deterministic_scores.risk_penalty <= 100.0
        assert isinstance(c.eligible_for_production, bool)
    assert any(c.eligible_for_production is False for c in cands)


def test_screen_text_catches_model_authored_advice():
    assert safety.screen_text("Buy now, this is a guaranteed win") != []
    assert safety.screen_text("The Fed cut rates by 25 basis points") == []


def test_ctr_and_retention_are_relative_scores_not_forecasts():
    """The engine must never emit a real-world percentage claim."""
    from app.topic_intelligence.rankers.deterministic import to_ranked
    from app.topic_intelligence.config_types import ChannelBrief
    from app.topic_intelligence.scoring import score_all

    cands = score_all(_cluster(FOMC_SIGNALS), now=NOW)
    topic = to_ranked(cands[0], ChannelBrief(channel_id="usa_trading"))
    assert 0.0 <= topic.scores.ctr_potential <= 100.0
    assert 0.0 <= topic.scores.retention_potential <= 100.0
    assert 0.0 <= topic.confidence <= 1.0
    blob = json.dumps(topic.model_dump(), default=str)
    assert "% CTR" not in blob and "achieve 12" not in blob


# --------------------------------------------------------------------------- #
# 13. provenance is persisted
# --------------------------------------------------------------------------- #
async def test_evidence_provenance_is_persisted(ti_repo):
    svc = _service(ti_repo, FOMC_SIGNALS + NVDA_SIGNALS)
    result = await svc.run(channel_id="usa_trading", enqueue=False)

    assert result.ok, result.warnings
    topic_id = result.selected.topic_id

    evidence = ti_repo.evidence_for(topic_id, run_id=result.run_id)
    assert evidence, "no evidence rows persisted"
    for e in evidence:
        assert e.provider
        assert e.title
        assert e.collected_at is not None
        assert e.source_tier
        assert json.loads(e.metrics_json) is not None
    assert any(e.url and e.url.startswith("http") for e in evidence)

    candidate = ti_repo.candidate(topic_id)
    assert candidate is not None
    assert candidate.run_id == result.run_id
    assert json.loads(candidate.metrics_json)
    assert json.loads(candidate.deterministic_scores_json)["overall_score"] > 0

    run = ti_repo.get_run(result.run_id)
    assert run is not None
    assert run.selected_topic_id == topic_id
    assert run.ranking_version and run.prompt_version
    assert run.ranker_used == "deterministic"

    results = ti_repo.run_results(result.run_id)
    assert any(r.selected for r in results)
    assert all(r.scores_json for r in results)

    provider_rows = ti_repo.provider_runs(result.run_id)
    assert {p.provider for p in provider_rows} == {"finance_news"}


async def test_evidence_bundle_contains_the_full_decision(ti_repo):
    from app.topic_intelligence.provenance import evidence_bundle

    svc = _service(ti_repo, FOMC_SIGNALS + BITCOIN_SIGNALS)
    result = await svc.run(channel_id="usa_trading", enqueue=False)
    assert result.ok

    _finalists, all_candidates = svc.build_candidates(
        FOMC_SIGNALS + BITCOIN_SIGNALS, channel_id="usa_trading", now=NOW
    )
    candidate = next(
        (c for c in all_candidates if c.topic_id == result.selected.topic_id), None
    )
    bundle = evidence_bundle(result, result.selected, candidate)

    for key in ("run_id", "channel_id", "ranking_version", "prompt_version",
                "ranker_used", "topic", "scores", "evidence", "providers",
                "funnel", "cost"):
        assert key in bundle, key
    assert bundle["evidence"], "bundle must carry citations"
    assert bundle["funnel"]["raw_signals"] > 0
    json.dumps(bundle, default=str)      # must be serializable


async def test_ledger_records_the_selection(ti_repo):
    svc = _service(ti_repo, FOMC_SIGNALS)
    result = await svc.run(channel_id="usa_trading", enqueue=False)
    entries = ti_repo.ledger_entries("usa_trading", days=30)
    assert len(entries) == 1
    assert entries[0].topic_id == result.selected.topic_id
    assert entries[0].status == "selected"


# --------------------------------------------------------------------------- #
# 16. a complete mock run selects exactly ONE eligible topic
# --------------------------------------------------------------------------- #
async def test_full_mock_run_selects_exactly_one_topic(ti_repo):
    s = _settings()
    providers = [
        StubProvider("finance_news",
                     FOMC_SIGNALS + NVDA_SIGNALS + BITCOIN_SIGNALS, settings=s),
        StubProvider("youtube", HFT_SIGNALS, settings=s),
        StubProvider("reddit", REDDIT_RUMOUR_SIGNALS, settings=s),
        StubProvider("x", enabled=False, settings=s),
        StubProvider("economic_calendar", configured=False, settings=s),
    ]
    svc = TopicIntelligenceService(settings=s, repo=ti_repo, providers=providers)
    result = await svc.run(channel_id="usa_trading", enqueue=False)

    assert result.status == "ok"
    assert result.selected is not None
    assert result.selected.eligible_for_production is True
    # Exactly one winner, and it is the highest scoring eligible candidate.
    eligible = [r for r in result.ranked if r.eligible_for_production]
    assert result.selected.scores.overall_score == max(
        r.scores.overall_score for r in eligible
    )
    assert len([r for r in result.ranked
                if r.topic_id == result.selected.topic_id]) == 1

    # The unsafe rumour must not win.
    assert "rumor" not in result.selected.canonical_topic.lower()
    assert "rumour" not in result.selected.canonical_topic.lower()

    # Funnel accounting and partial-provider success.
    assert result.raw_signal_count > 0
    assert result.cluster_count > 0
    assert result.finalist_count > 0
    statuses = {p.name: p for p in result.providers}
    assert statuses["x"].ok is False
    assert statuses["economic_calendar"].ok is False
    assert statuses["finance_news"].ok is True


async def test_full_run_with_gemini_selects_one_topic(ti_repo):
    s = _settings(gemini_api_key="test-key", gemini_ranker_enabled=True)
    providers = [StubProvider("finance_news", FOMC_SIGNALS + NVDA_SIGNALS, settings=s)]

    svc0 = TopicIntelligenceService(settings=s, repo=ti_repo, providers=providers)
    finalists, _all = svc0.build_candidates(
        FOMC_SIGNALS + NVDA_SIGNALS, channel_id="usa_trading", now=NOW
    )
    payload = json.dumps({"ranked": [
        {"topic_id": c.topic_id, "proposed_angle": "Explain the mechanism",
         "target_viewer": "US investors", "hook_concept": "Here is what changed.",
         "why_now": "It happened hours ago.", "score_explanation": "Timely.",
         "confidence": 0.8, "cited_source_names": ["finance_news"],
         "audience_relevance": 85, "ctr_potential": 75, "retention_potential": 72,
         "subscriber_potential": 65, "monetization_potential": 80,
         "production_feasibility": 85}
        for c in finalists
    ]})

    svc = TopicIntelligenceService(
        settings=s, repo=ti_repo, providers=providers,
        gemini_client=StubGeminiClient(responses=[payload], settings=s),
    )
    result = await svc.run(channel_id="usa_trading", enqueue=False)

    assert result.ok
    assert result.ranker_used == "gemini"
    assert result.gemini_model == s.gemini_model
    assert result.cost.gemini_calls == 1
    assert result.cost.estimated_usd > 0
    assert result.selected.proposed_angle == "Explain the mechanism"


async def test_run_does_not_enqueue_by_default(ti_repo, monkeypatch):
    called = False

    async def _boom(*_a, **_k):
        nonlocal called
        called = True
        return "job_x"

    monkeypatch.setattr(
        "app.topic_intelligence.bridge.enqueue_topic", _boom, raising=False
    )
    svc = _service(ti_repo, FOMC_SIGNALS)
    result = await svc.run(channel_id="usa_trading")
    assert called is False
    assert result.enqueued_job_id is None


# --------------------------------------------------------------------------- #
# 17. nothing eligible -> NO_SAFE_TOPIC_AVAILABLE
# --------------------------------------------------------------------------- #
async def test_no_eligible_candidate_returns_no_safe_topic(ti_repo):
    svc = _service(ti_repo, UNSAFE_SIGNALS + REDDIT_RUMOUR_SIGNALS)
    result = await svc.run(channel_id="usa_trading", enqueue=False)

    assert result.status == NO_SAFE_TOPIC_AVAILABLE
    assert result.selected is None
    assert result.ok is False
    assert any("refusing to produce filler content" in w for w in result.warnings)
    # The refusal is still fully persisted for audit.
    run = ti_repo.get_run(result.run_id)
    assert run is not None and run.status == NO_SAFE_TOPIC_AVAILABLE
    assert run.selected_topic_id is None


async def test_zero_signals_returns_no_safe_topic(ti_repo):
    svc = _service(ti_repo, [])
    result = await svc.run(channel_id="usa_trading", enqueue=False)
    assert result.status == NO_SAFE_TOPIC_AVAILABLE
    assert result.raw_signal_count == 0


async def test_all_providers_down_returns_no_safe_topic(ti_repo):
    s = _settings()
    svc = TopicIntelligenceService(
        settings=s, repo=ti_repo,
        providers=[
            StubProvider("finance_news", exc=RuntimeError("dns fail"), settings=s),
            StubProvider("youtube", exc=TimeoutError("gateway"), settings=s),
        ],
    )
    result = await svc.run(channel_id="usa_trading", enqueue=False)
    assert result.status == NO_SAFE_TOPIC_AVAILABLE
    assert all(p.ok is False for p in result.providers)
    assert len(result.warnings) >= 2


async def test_minimum_eligible_candidates_is_enforced(ti_repo):
    svc = _service(ti_repo, FOMC_SIGNALS, ti_min_eligible_candidates=5)
    result = await svc.run(channel_id="usa_trading", enqueue=False)
    assert result.status == NO_SAFE_TOPIC_AVAILABLE


async def test_previously_published_topic_is_excluded_from_a_later_run(ti_repo):
    """The ledger written by run #1 blocks the same topic in run #2."""
    first = await _service(ti_repo, FOMC_SIGNALS).run(
        channel_id="usa_trading", enqueue=False
    )
    assert first.ok
    ti_repo.mark_ledger_status(first.selected.topic_id, "published")

    second = await _service(ti_repo, FOMC_SIGNALS).run(
        channel_id="usa_trading", enqueue=False
    )
    assert second.status == NO_SAFE_TOPIC_AVAILABLE, (
        "a published topic must not be selectable again"
    )


async def test_a_different_topic_still_wins_after_a_publication(ti_repo):
    first = await _service(ti_repo, FOMC_SIGNALS).run(
        channel_id="usa_trading", enqueue=False
    )
    assert first.ok
    second = await _service(ti_repo, FOMC_SIGNALS + BITCOIN_SIGNALS).run(
        channel_id="usa_trading", enqueue=False
    )
    assert second.ok
    assert second.selected.topic_id != first.selected.topic_id


async def test_off_niche_stories_are_rejected(ti_repo):
    """Safe but off-beat: a courtroom story from a general news feed must not win."""
    off_niche = FOMC_SIGNALS[0].model_copy(update={
        "external_id": "court-1",
        "title": "Judge weighs motion to dismiss in high-profile perjury case",
        "summary": "Lawyers argued over the wording of a subpoena.",
        "url": "https://www.cnbc.com/2026/07/28/court-case.html",
    })
    svc = _service(ti_repo, [off_niche])
    result = await svc.run(channel_id="usa_trading", enqueue=False)
    assert result.status == NO_SAFE_TOPIC_AVAILABLE

    _finalists, all_candidates = svc.build_candidates(
        [off_niche], channel_id="usa_trading", now=NOW
    )
    assert all_candidates[0].eligible_for_production is False
    assert any("off-niche" in r for r in all_candidates[0].rejection_reasons)


def test_relevance_gate_keeps_real_finance_topics():
    from app.topic_intelligence.scoring import is_on_niche

    for signals in (FOMC_SIGNALS, NVDA_SIGNALS, BITCOIN_SIGNALS, HFT_SIGNALS):
        c = _cluster(signals)[0]
        assert is_on_niche(c), c.canonical_topic


def test_word_boundary_matching_prevents_false_asset_classes():
    """'dwindling stockpiles' is not an equities story."""
    from app.topic_intelligence.entities import detect_asset_classes
    from app.topic_intelligence.models import AssetClass

    assert detect_asset_classes(
        "US and Iran pause fighting amid dwindling stockpiles"
    ) == [AssetClass.unknown]
    assert AssetClass.equities in detect_asset_classes(
        "US stock market closes higher"
    )


async def test_run_over_the_full_fixture_set_is_sane(ti_repo):
    svc = _service(ti_repo, ALL_SIGNALS)
    result = await svc.run(channel_id="usa_trading", enqueue=False)
    assert result.ok
    assert result.cluster_count >= 6
    assert result.finalist_count >= 1
    assert result.selected.source_count >= 1
    assert result.selected.supporting_evidence
