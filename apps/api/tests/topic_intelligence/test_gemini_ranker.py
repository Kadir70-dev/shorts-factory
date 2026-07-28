"""
Gemini ranking + validation tests (requirements 7, 8, 9, 10, 11, 15).

  7. Gemini structured output passes validation.
  8. Gemini inventing an unknown candidate ID is rejected.
  9. Gemini inventing a source is rejected.
 10. The overall score is recalculated in code.
 11. Gemini failure activates the deterministic fallback.
 15. The daily Gemini budget is respected.
"""
from __future__ import annotations

import json

import pytest

from app.topic_intelligence.clustering import cluster_signals
from app.topic_intelligence.gemini_client import (
    GeminiBudgetExceeded,
    GeminiUnavailable,
    parse_json_response,
)
from app.topic_intelligence.models import GeminiRankingResponse, TopicScores
from app.topic_intelligence.normalizer import normalize_all
from app.topic_intelligence.rankers.gemini import GeminiRanker, find_invented_metrics
from app.topic_intelligence.safety import apply as apply_safety
from app.topic_intelligence.scoring import (
    blend_gemini_scores,
    load_config,
    recompute_overall,
    score_all,
)
from app.topic_intelligence.settings import TopicIntelligenceSettings

from .conftest import StubGeminiClient
from .fixtures import BITCOIN_SIGNALS, FOMC_SIGNALS, NOW, NVDA_SIGNALS


def _candidates(signals=None):
    sigs = signals if signals is not None else FOMC_SIGNALS + NVDA_SIGNALS
    cands = cluster_signals(normalize_all(sigs, now=NOW), now=NOW)
    apply_safety(cands)
    return score_all(cands, now=NOW)


def _verdict(topic_id: str, **over) -> dict:
    base = {
        "topic_id": topic_id,
        "proposed_angle": "Explain the decision and the one number that matters",
        "target_viewer": "US retail investors who track the Fed",
        "hook_concept": "The Fed just moved. Here is what changes.",
        "why_now": "The decision landed hours ago and rates drive everything downstream.",
        "score_explanation": "Timely, well sourced, easy to explain in 40 seconds.",
        "confidence": 0.82,
        "risk_flags": [],
        "rejection_reasons": [],
        "cited_source_names": ["finance_news"],
        "audience_relevance": 90,
        "ctr_potential": 78,
        "retention_potential": 74,
        "subscriber_potential": 70,
        "monetization_potential": 80,
        "production_feasibility": 88,
    }
    base.update(over)
    return base


def _payload(*verdicts) -> str:
    return json.dumps({"ranked": list(verdicts), "notes": ""})


def _settings(**over) -> TopicIntelligenceSettings:
    defaults = dict(gemini_api_key="test-key", gemini_ranker_enabled=True,
                    gemini_grounding_enabled=False)
    defaults.update(over)
    return TopicIntelligenceSettings(**defaults)


# --------------------------------------------------------------------------- #
# 7. structured output passes validation
# --------------------------------------------------------------------------- #
async def test_valid_gemini_output_passes_validation(brief):
    cands = _candidates()
    s = _settings()
    client = StubGeminiClient(
        responses=[_payload(*[_verdict(c.topic_id) for c in cands])], settings=s
    )
    ranked, cost, warnings = await GeminiRanker(s, client=client).rank(cands, brief=brief)

    assert len(ranked) == len(cands)
    assert all(r.ranker == "gemini" for r in ranked)
    assert ranked[0].proposed_angle.startswith("Explain the decision")
    assert ranked[0].confidence == pytest.approx(0.82)
    assert cost.gemini_calls == 1
    assert not [w for w in warnings if "REJECTED" in w]


def test_pydantic_validation_coerces_and_clamps_scores():
    parsed = GeminiRankingResponse.model_validate({
        "ranked": [{"topic_id": "tc_x", "confidence": 87, "ctr_potential": "78%",
                    "retention_potential": 140, "audience_relevance": -5}]
    })
    v = parsed.ranked[0]
    assert v.confidence == pytest.approx(0.87)      # 0-100 -> 0-1
    assert v.ctr_potential == 78.0                  # "78%" -> 78.0
    assert v.retention_potential == 100.0           # clamped
    assert v.audience_relevance == 0.0              # clamped


def test_topic_scores_reject_non_numeric_values():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TopicScores(trend_momentum="not a number")


def test_fenced_json_is_parsed():
    out = parse_json_response('```json\n{"ranked": []}\n```')
    assert out == {"ranked": []}


async def test_malformed_gemini_json_falls_back_cleanly(brief):
    s = _settings()
    client = StubGeminiClient(responses=["this is not json at all"], settings=s)
    ranked, _cost, warnings = await GeminiRanker(s, client=client).rank(
        _candidates(), brief=brief
    )
    assert ranked == []
    assert any("unparseable" in w for w in warnings)


# --------------------------------------------------------------------------- #
# 8. unknown candidate ID is rejected
# --------------------------------------------------------------------------- #
async def test_invented_topic_id_is_rejected(brief):
    cands = _candidates()
    s = _settings()
    client = StubGeminiClient(
        responses=[_payload(
            _verdict("tc_totally_made_up"),
            _verdict(cands[0].topic_id),
        )],
        settings=s,
    )
    ranked, _cost, warnings = await GeminiRanker(s, client=client).rank(cands, brief=brief)

    ids = {r.topic_id for r in ranked}
    assert "tc_totally_made_up" not in ids
    assert cands[0].topic_id in ids
    assert any("REJECTED unknown topic_id" in w for w in warnings)
    # Candidates the model omitted still get a deterministic ranking.
    assert ids == {c.topic_id for c in cands}


async def test_duplicate_verdicts_are_ignored(brief):
    cands = _candidates(FOMC_SIGNALS)
    s = _settings()
    client = StubGeminiClient(
        responses=[_payload(_verdict(cands[0].topic_id), _verdict(cands[0].topic_id))],
        settings=s,
    )
    ranked, _c, warnings = await GeminiRanker(s, client=client).rank(cands, brief=brief)
    assert len(ranked) == 1
    assert any("duplicate verdict" in w for w in warnings)


# --------------------------------------------------------------------------- #
# 9. invented source is rejected
# --------------------------------------------------------------------------- #
async def test_invented_source_citation_is_rejected(brief):
    cands = _candidates(FOMC_SIGNALS)
    s = _settings()
    client = StubGeminiClient(
        responses=[_payload(_verdict(
            cands[0].topic_id,
            cited_source_names=["Bloomberg Terminal Exclusive", "my-own-analysis.io"],
            proposed_angle="An angle citing a source we never collected",
        ))],
        settings=s,
    )
    ranked, _cost, warnings = await GeminiRanker(s, client=client).rank(cands, brief=brief)

    assert any("cited unknown source" in w for w in warnings)
    topic = ranked[0]
    assert "gemini_invented_source" in topic.risk_flags
    # The model's narrative is discarded; the deterministic angle stands.
    assert topic.proposed_angle != "An angle citing a source we never collected"
    assert any("not present in the evidence bundle" in r
               for r in topic.rejection_reasons)


async def test_legitimate_citation_is_accepted(brief):
    cands = _candidates(FOMC_SIGNALS)
    s = _settings()
    client = StubGeminiClient(
        responses=[_payload(_verdict(
            cands[0].topic_id, cited_source_names=["federalreserve.gov", "reuters"]
        ))],
        settings=s,
    )
    ranked, _cost, warnings = await GeminiRanker(s, client=client).rank(cands, brief=brief)
    assert not any("unknown source" in w for w in warnings)
    assert "gemini_invented_source" not in ranked[0].risk_flags


# --------------------------------------------------------------------------- #
# invented metrics
# --------------------------------------------------------------------------- #
async def test_invented_metrics_in_the_narrative_are_rejected(brief):
    cands = _candidates(FOMC_SIGNALS)
    s = _settings()
    client = StubGeminiClient(
        responses=[_payload(_verdict(
            cands[0].topic_id,
            why_now="This topic has 4,200,000 searches per month and a 12% CTR.",
        ))],
        settings=s,
    )
    ranked, _cost, warnings = await GeminiRanker(s, client=client).rank(cands, brief=brief)

    assert any("invented metric" in w for w in warnings)
    assert "gemini_invented_metric" in ranked[0].risk_flags
    assert "4,200,000" not in ranked[0].why_now


def test_find_invented_metrics_accepts_numbers_we_actually_measured():
    c = _candidates(FOMC_SIGNALS)[0]
    measured = int(c.metrics["views_per_hour"])
    assert find_invented_metrics(f"About {measured} views per hour on YouTube", c) == []
    assert find_invented_metrics("It has 99999999 views", c) != []


# --------------------------------------------------------------------------- #
# 10. overall score is recalculated in code
# --------------------------------------------------------------------------- #
async def test_overall_score_is_recomputed_not_taken_from_gemini(brief):
    cands = _candidates(FOMC_SIGNALS)
    s = _settings()
    # The model tries to hand us a perfect score for everything.
    client = StubGeminiClient(
        responses=[_payload(_verdict(
            cands[0].topic_id, overall_score=100, trend_momentum=100,
            credibility=100, freshness=100, competition_opportunity=100,
            risk_penalty=0,
        ))],
        settings=s,
    )
    ranked, _cost, _w = await GeminiRanker(s, client=client).rank(cands, brief=brief)
    topic = ranked[0]

    cfg = load_config()
    assert topic.scores.overall_score == recompute_overall(topic.scores, cfg)
    assert topic.scores.overall_score < 100.0
    # Deterministic-only dimensions are untouched by the model.
    det = cands[0].deterministic_scores
    assert topic.scores.trend_momentum == det.trend_momentum
    assert topic.scores.credibility == det.credibility
    assert topic.scores.freshness == det.freshness
    assert topic.scores.competition_opportunity == det.competition_opportunity
    assert topic.scores.risk_penalty == det.risk_penalty


def test_blend_only_moves_allowed_fields_and_respects_influence():
    det = TopicScores(
        trend_momentum=40, audience_relevance=50, competition_opportunity=60,
        freshness=70, credibility=80, ctr_potential=50, retention_potential=50,
        subscriber_potential=50, monetization_potential=50,
        production_feasibility=50, risk_penalty=10,
    )
    blended = blend_gemini_scores(
        det,
        {"ctr_potential": 100.0, "trend_momentum": 100.0, "credibility": 0.0},
        influence=0.5,
    )
    assert blended.ctr_potential == 75.0          # 50*(0.5) + 100*(0.5)
    assert blended.trend_momentum == 40.0         # not adjustable -> unchanged
    assert blended.credibility == 80.0            # not adjustable -> unchanged
    assert blended.overall_score == recompute_overall(blended)


def test_zero_influence_makes_gemini_purely_advisory():
    det = TopicScores(ctr_potential=50.0)
    blended = blend_gemini_scores(det, {"ctr_potential": 100.0}, influence=0.0)
    assert blended.ctr_potential == 50.0


def test_risk_penalty_is_subtractive():
    clean = TopicScores(trend_momentum=80, audience_relevance=80, freshness=80,
                        credibility=80, competition_opportunity=80, ctr_potential=80,
                        retention_potential=80, subscriber_potential=80,
                        monetization_potential=80, production_feasibility=80)
    risky = clean.model_copy(update={"risk_penalty": 50.0})
    assert recompute_overall(risky) < recompute_overall(clean)


# --------------------------------------------------------------------------- #
# 11. Gemini failure -> deterministic fallback
# --------------------------------------------------------------------------- #
async def test_gemini_api_failure_returns_no_ranking_and_a_warning(brief):
    s = _settings()
    client = StubGeminiClient(exc=GeminiUnavailable("503 backend unavailable"),
                              settings=s)
    ranked, _cost, warnings = await GeminiRanker(s, client=client).rank(
        _candidates(), brief=brief
    )
    assert ranked == []
    assert any("503 backend unavailable" in w for w in warnings)


async def test_service_falls_back_to_deterministic_on_gemini_failure(ti_repo, brief):
    from app.config import load_channel
    from app.topic_intelligence.service import TopicIntelligenceService

    s = _settings()
    svc = TopicIntelligenceService(
        settings=s, repo=ti_repo,
        gemini_client=StubGeminiClient(exc=GeminiUnavailable("down"), settings=s),
    )
    ranked, ranker_used, _cost, warnings, model = await svc.rank(
        _candidates(FOMC_SIGNALS), channel=load_channel("usa_trading"),
        run_id="run_fb",
    )
    assert ranker_used == "deterministic"
    assert model is None
    assert ranked and ranked[0].ranker == "deterministic"
    assert any("deterministic fallback engaged" in w for w in warnings)


async def test_disabled_ranker_uses_deterministic_without_calling_gemini(ti_repo):
    from app.config import load_channel
    from app.topic_intelligence.service import TopicIntelligenceService

    s = _settings(gemini_ranker_enabled=False)
    client = StubGeminiClient(settings=s)
    svc = TopicIntelligenceService(settings=s, repo=ti_repo, gemini_client=client)
    _ranked, ranker_used, _cost, warnings, _m = await svc.rank(
        _candidates(FOMC_SIGNALS), channel=load_channel("usa_trading"), run_id="r"
    )
    assert ranker_used == "deterministic"
    assert client.calls == 0
    assert any("GEMINI_RANKER_ENABLED=false" in w for w in warnings)


# --------------------------------------------------------------------------- #
# 15. daily budget
# --------------------------------------------------------------------------- #
async def test_daily_budget_blocks_the_call(brief):
    s = _settings(gemini_daily_budget_usd=0.01)
    # Already spent the day's budget in earlier runs.
    client = StubGeminiClient(settings=s, spend_today=0.05)
    ranked, cost, warnings = await GeminiRanker(s, client=client).rank(
        _candidates(FOMC_SIGNALS), brief=brief
    )
    assert ranked == []
    assert client.calls == 1          # attempted, refused before any generation
    assert cost.budget_exhausted is True
    assert any("budget exhausted" in w for w in warnings)


async def test_spend_accumulates_and_then_trips_the_budget(brief):
    s = _settings(gemini_daily_budget_usd=0.0009)
    cands = _candidates(FOMC_SIGNALS)
    client = StubGeminiClient(
        responses=[_payload(_verdict(cands[0].topic_id))] * 2,
        settings=s, input_tokens=1_000_000, output_tokens=0,
    )
    # First call fits the budget ($0.30/Mtok * 1M = $0.0003 at test pricing? no —
    # 1M input tokens at 0.30/Mtok = $0.30) so it trips immediately after.
    first, _c, _w = await GeminiRanker(s, client=client).rank(cands, brief=brief)
    assert first, "first call should have been allowed"
    assert client.spent_usd > 0

    with pytest.raises(GeminiBudgetExceeded):
        await client.generate("second call")


def test_budget_of_zero_means_unlimited():
    s = _settings(gemini_daily_budget_usd=0.0)
    client = StubGeminiClient(settings=s, spend_today=999.0)
    client._check_budget()      # must not raise


def test_cost_estimate_uses_configured_pricing():
    s = _settings(gemini_input_cost_per_mtok=1.0, gemini_output_cost_per_mtok=2.0)
    client = StubGeminiClient(settings=s)
    assert client._estimate_cost(1_000_000, 500_000) == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# 12 (ranker half). Unsafe model output is caught after the fact.
# --------------------------------------------------------------------------- #
async def test_unsafe_gemini_narrative_marks_the_topic_ineligible(brief):
    cands = _candidates(BITCOIN_SIGNALS)
    s = _settings()
    client = StubGeminiClient(
        responses=[_payload(_verdict(
            cands[0].topic_id,
            hook_concept="Buy now — this is a guaranteed risk-free double.",
        ))],
        settings=s,
    )
    ranked, _cost, warnings = await GeminiRanker(s, client=client).rank(cands, brief=brief)

    assert ranked[0].eligible_for_production is False
    assert any("unsafe phrasing" in w for w in warnings)
    assert any(f.startswith("gemini_") for f in ranked[0].risk_flags)
    assert "Buy now" not in ranked[0].hook_concept
