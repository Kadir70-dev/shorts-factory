"""Phase 2B human review, approval gate, and audit tests."""
import json

import pytest

from app.topic_intelligence.review import ReviewError, TopicReviewService
from app.topic_intelligence.tables import (
    TopicCandidateRow, TopicEvidence, TopicLedger, TopicRankingResult,
    TopicRankingRun,
)


def seed(repo):
    with repo._session_factory() as s:
        s.add(TopicRankingRun(
            run_id="run-2b", channel_id="usa_trading", selected_topic_id="t1",
            status="ok", finalist_count=2, cluster_count=3,
        ))
        for topic, rank, eligible in (("t1", 0, True), ("t2", 1, True),
                                      ("dup", 2, False)):
            s.add(TopicCandidateRow(
                run_id="run-2b", topic_id=topic, channel_id="usa_trading",
                canonical_topic={"t1": "Fed cuts rates", "t2": "CPI cools",
                                 "dup": "Old Fed story"}[topic],
                deterministic_scores_json=json.dumps({"overall_score": 80-rank}),
                eligible_for_production=eligible,
                dedup_status="new" if eligible else "ledger_exact",
                rejection_reasons="" if eligible else "DUPLICATE_TOPIC",
            ))
            s.add(TopicRankingResult(
                run_id="run-2b", topic_id=topic, rank=rank,
                canonical_topic={"t1": "Fed cuts rates", "t2": "CPI cools",
                                 "dup": "Old Fed story"}[topic],
                proposed_angle="What traders need to know",
                scores_json=json.dumps({"overall_score": 80-rank}),
                overall_score=80-rank, confidence=.8, selected=topic == "t1",
                eligible_for_production=eligible,
                rejection_reasons="" if eligible else "DUPLICATE_TOPIC",
                score_explanation="Grounded score",
            ))
        s.add(TopicEvidence(
            run_id="run-2b", topic_id="t1", provider="finance_news",
            title="Fed release", url="https://example.test/fed",
        ))
        s.add(TopicLedger(
            channel_id="usa_trading", topic_id="t1", canonical_key="fed-cuts",
            canonical_topic="Fed cuts rates", status="selected", run_id="run-2b",
        ))
        s.commit()


@pytest.mark.asyncio
async def test_approve_enqueues_once_and_attaches_human_audit(ti_repo):
    seed(ti_repo)
    calls = []

    async def enqueue(topic, channel, *, evidence_bundle):
        calls.append((topic, channel, evidence_bundle))
        return "job-2b"

    service = TopicReviewService(repo=ti_repo, enqueue=enqueue)
    result = await service.approve("run-2b", actor="alice", reason="timely")

    assert result["review"]["status"] == "approved"
    assert result["review"]["job_id"] == "job-2b"
    assert calls[0][2]["approval"]["actor"] == "alice"
    assert calls[0][2]["evidence"][0]["url"] == "https://example.test/fed"
    with pytest.raises(ReviewError) as exc:
        await service.approve("run-2b", actor="alice")
    assert exc.value.code == "ALREADY_ENQUEUED"
    assert len(calls) == 1


def test_reject_requires_reason_and_is_audited(ti_repo):
    seed(ti_repo)
    service = TopicReviewService(repo=ti_repo)
    with pytest.raises(ReviewError) as exc:
        service.reject("run-2b", reason="")
    assert exc.value.code == "REASON_REQUIRED"

    result = service.reject("run-2b", actor="editor", reason="weak hook")
    assert result["review"]["status"] == "rejected"
    assert result["audit_trail"][-1]["action"] == "reject"
    assert result["selected"]["eligible_for_production"] is False


def test_alternate_and_duplicate_override_preserve_audit(ti_repo):
    seed(ti_repo)
    service = TopicReviewService(repo=ti_repo)

    changed = service.select_alternate("run-2b", "t2", actor="editor")
    assert changed["run"]["selected_topic_id"] == "t2"
    assert changed["selected"]["selected"] is True
    assert ti_repo.ledger_row(run_id="run-2b", topic_id="t1").status == "abandoned"

    with pytest.raises(ReviewError) as exc:
        service.select_alternate("run-2b", "dup")
    assert exc.value.code == "TOPIC_NOT_ELIGIBLE"

    overridden = service.override_duplicate(
        "run-2b", "dup", actor="admin", reason="material new development",
    )
    dup = next(x for x in overridden["ranked"] if x["topic_id"] == "dup")
    assert dup["eligible_for_production"] is True
    assert dup["dedup_status"] == "override"
    assert overridden["audit_trail"][-1]["action"] == "override_duplicate"


def test_review_api_and_dashboard_are_mounted():
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert {
        "/topic-intelligence/reviews",
        "/topic-intelligence/reviews/{run_id}",
        "/topic-intelligence/reviews/{run_id}/approve",
        "/topic-intelligence/reviews/{run_id}/reject",
        "/topic-intelligence/reviews/{run_id}/select-alternate",
        "/topic-intelligence/reviews/{run_id}/candidates/{topic_id}/override-duplicate",
    } <= paths
    from app.topic_intelligence.router import router
    review = next(r for r in router.routes if r.path == "/topic-intelligence/review")
    assert "GET" in review.methods
