"""Focused Phase 2B -> existing generation pipeline integration tests."""
from pathlib import Path

import pytest

from app.db import Job
from app.schemas.video_spec import Niche, VideoSpec
from app.topic_intelligence.bridge import build_video_spec
from app.topic_intelligence.models import RankedTopic
from app.topic_intelligence.review import (
    ReviewError, TopicReviewService, generation_job_view,
)


def test_approved_topic_maps_to_stable_existing_video_spec(brief):
    from app.config import load_channel

    topic = RankedTopic(
        topic_id="topic-stable",
        canonical_topic="Fed decision moves markets",
        proposed_angle="What the decision changes for traders",
        hook_concept="The Fed just changed the setup.",
        why_now="The decision was released today.",
    )
    bundle = {
        "run_id": "run-stable",
        "topic": {"topic_id": topic.topic_id},
        "score_explanation": "Strong timely evidence",
        "evidence": [{"url": "https://example.test/fed"}],
        "risk_flags": [],
        "recommended_publish_window": "2026-07-29T15:00:00Z",
    }
    one = build_video_spec(topic, load_channel("usa_trading"),
                           evidence_bundle=bundle)
    two = build_video_spec(topic, load_channel("usa_trading"),
                           evidence_bundle=bundle)

    assert one.id == two.id
    assert one.id.startswith("vid_ti_")
    assert "Angle:" in one.topic and "Hook:" in one.topic


@pytest.mark.asyncio
async def test_existing_job_prevents_duplicate_queue(monkeypatch):
    from app.routers import generate

    spec = VideoSpec(id="vid_ti_duplicate", channel_id="usa_trading",
                     niche=Niche.finance, topic="Fed")
    existing = Job(id=spec.id, channel_id=spec.channel_id, niche=spec.niche.value,
                   topic=spec.topic, status="rendering", spec_json=spec.model_dump_json())
    monkeypatch.setattr(generate, "get_job", lambda _: existing)

    async def should_not_connect(*args, **kwargs):
        raise AssertionError("duplicate enqueue contacted Redis")

    monkeypatch.setattr(generate, "create_pool", should_not_connect)
    await generate.enqueue_spec(spec)


@pytest.mark.asyncio
async def test_new_job_uses_arq_job_id_for_concurrent_dedup(monkeypatch):
    from app.routers import generate

    spec = VideoSpec(id="vid_ti_new", channel_id="usa_trading",
                     niche=Niche.finance, topic="CPI")
    saved, calls = [], []

    class Pool:
        async def enqueue_job(self, *args, **kwargs):
            calls.append((args, kwargs))

    async def pool(*args, **kwargs):
        return Pool()

    monkeypatch.setattr(generate, "get_job", lambda _: None)
    monkeypatch.setattr(generate, "upsert_job", saved.append)
    monkeypatch.setattr(generate, "create_pool", pool)
    await generate.enqueue_spec(spec)

    assert saved[0].id == spec.id
    assert calls == [(("run_pipeline", spec.id), {"_job_id": spec.id})]


@pytest.mark.asyncio
async def test_rejected_topic_cannot_start_generation(ti_repo):
    from tests.topic_intelligence.test_review import seed

    seed(ti_repo)
    service = TopicReviewService(repo=ti_repo)
    service.reject("run-2b", actor="editor", reason="not suitable")
    with pytest.raises(ReviewError) as exc:
        await service.approve("run-2b")
    assert exc.value.code == "ALREADY_REJECTED"


def test_review_job_visibility_completed_and_failed(tmp_path, monkeypatch):
    from app.topic_intelligence import review

    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"test")
    jobs = {
        "vid_visible_complete": Job(
            id="vid_visible_complete", channel_id="usa_trading",
            niche="usa_finance", topic="Completed topic",
            status="awaiting_approval", output_mp4=str(mp4),
        ),
        "vid_visible_failed": Job(
            id="vid_visible_failed", channel_id="usa_trading",
            niche="usa_finance", topic="Failed topic", status="failed",
            error="RenderError: ffmpeg failed",
        ),
    }
    monkeypatch.setattr(review, "get_job", jobs.get)

    visible = generation_job_view("vid_visible_complete")
    assert visible["status"] == "awaiting_approval"
    assert visible["progress"] == 100
    assert visible["output_mp4"] == str(mp4)
    assert visible["video_url"] == "/jobs/vid_visible_complete/video"

    failed = generation_job_view("vid_visible_failed")
    assert failed["status"] == "failed"
    assert failed["error"] == "RenderError: ffmpeg failed"
    assert failed["output_mp4"] is None

@pytest.mark.asyncio
async def test_approval_response_links_existing_generation_job(ti_repo):
    from tests.topic_intelligence.test_review import seed

    seed(ti_repo)

    async def existing_pipeline(topic, channel, *, evidence_bundle):
        assert evidence_bundle["topic"]["topic_id"] == "t1"
        assert evidence_bundle["evidence"][0]["url"] == "https://example.test/fed"
        return "vid_ti_linked"

    result = await TopicReviewService(
        repo=ti_repo, enqueue=existing_pipeline,
    ).approve("run-2b", actor="editor")

    assert result["run"]["enqueued_job_id"] == "vid_ti_linked"
    assert result["review"]["generation"]["job_id"] == "vid_ti_linked"
    assert result["review"]["generation"]["status"] == "queued"
