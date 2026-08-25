"""Tests for /generate — validation, enqueue, idempotency, queue failure.

No real Redis is contacted: `create_pool` is patched per test. That is the
point of several of these — the previous implementation had no failure path
at all, so a Redis outage surfaced as an unhandled 500.
"""
from __future__ import annotations

import pytest

from app.routers import generate as gen


class FakePool:
    """Stands in for arq's ArqRedis. Records enqueues and whether it closed."""

    def __init__(self):
        self.enqueued: list[tuple] = []
        self.closed = False

    async def enqueue_job(self, fn, *args, **kwargs):
        self.enqueued.append((fn, args, kwargs))
        return object()

    async def aclose(self):
        self.closed = True


@pytest.fixture
def pool(monkeypatch):
    """Patch create_pool to hand out one shared FakePool."""
    fake = FakePool()

    async def _create_pool(*_a, **_kw):
        return fake

    monkeypatch.setattr(gen, "create_pool", _create_pool)
    return fake


@pytest.fixture
def broken_pool(monkeypatch):
    """Patch create_pool to fail the way an unreachable Redis does."""
    async def _create_pool(*_a, **_kw):
        raise ConnectionError("Connection refused")

    monkeypatch.setattr(gen, "create_pool", _create_pool)


def _spec_payload(**overrides) -> dict:
    payload = {
        "channel_id": "test_channel",
        "niche": "usa_finance",
        "topic": "what is inflation",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def any_channel(monkeypatch):
    """Channel validation is config-file-backed; accept any id here."""
    monkeypatch.setattr(gen, "load_channel", lambda _cid: object())


# --- validation ------------------------------------------------------------


def test_unknown_channel_is_404_not_500(client, pool):
    """Regression: load_channel raises FileNotFoundError for an unknown id,
    which escaped both endpoints unhandled as a 500 with a traceback."""
    res = client.post("/generate", json=_spec_payload(channel_id="no_such_channel"))
    assert res.status_code == 404
    assert pool.enqueued == []


def test_unknown_channel_does_not_leak_server_paths(client, pool):
    """The FileNotFoundError text embedded the absolute config path, so the
    error response disclosed the deployment's filesystem layout."""
    res = client.post("/generate", json=_spec_payload(channel_id="no_such_channel"))
    body = str(res.json())
    assert "/home/" not in body
    assert "config/channels" not in body


def test_unknown_channel_is_404_for_batch(client, pool):
    res = client.post("/generate/batch", json={
        "channel_id": "no_such_channel", "niche": "usa_finance", "count": 2,
    })
    assert res.status_code == 404
    assert pool.enqueued == []


def test_invalid_niche_is_422(client, any_channel, pool):
    res = client.post("/generate", json=_spec_payload(niche="not_a_niche"))
    assert res.status_code == 422


def test_batch_count_is_bounded(client, any_channel, pool):
    res = client.post("/generate/batch", json={
        "channel_id": "test_channel", "niche": "usa_finance", "count": 9999,
    })
    assert res.status_code == 422


# --- single enqueue --------------------------------------------------------


def test_generate_one_enqueues_and_persists(client, any_channel, pool, job_db):
    res = client.post("/generate", json=_spec_payload())
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    assert res.json()["status"] == "queued"

    assert len(pool.enqueued) == 1
    fn, args, kwargs = pool.enqueued[0]
    assert fn == "run_pipeline"
    assert args == (job_id,)
    assert kwargs["_job_id"] == job_id

    stored = job_db.get_job(job_id)
    assert stored is not None and stored.status == "queued"


def test_enqueue_closes_the_pool_it_created(client, any_channel, pool):
    """Regression: create_pool was never closed, leaking one connection pool
    per enqueue (50 for a max-size batch)."""
    client.post("/generate", json=_spec_payload())
    assert pool.closed is True


# --- idempotency -----------------------------------------------------------


async def test_reenqueue_of_a_queued_job_is_allowed(job_db, pool, any_channel):
    """A queued row may re-submit the same arq job id so a prior Redis outage
    can recover."""
    from app.schemas.video_spec import VideoSpec

    spec = VideoSpec(channel_id="c", niche="usa_finance", topic="t", id="vid_fixed")
    await gen.enqueue_spec(spec)
    await gen.enqueue_spec(spec)
    assert len(pool.enqueued) == 2
    assert all(call[2]["_job_id"] == "vid_fixed" for call in pool.enqueued)


async def test_non_queued_job_is_not_reenqueued(job_db, pool):
    """Once work has started, re-submitting must be a no-op."""
    from app.schemas.video_spec import VideoSpec

    spec = VideoSpec(channel_id="c", niche="usa_finance", topic="t", id="vid_running")
    job_db.upsert_job(job_db.Job(
        id="vid_running", channel_id="c", niche="usa_finance",
        topic="t", status="rendering",
    ))
    await gen.enqueue_spec(spec)
    assert pool.enqueued == []


# --- queue failure / recovery ---------------------------------------------


def test_queue_outage_returns_503_not_500(client, any_channel, broken_pool):
    """Regression: an unreachable Redis raised out of the router unhandled."""
    res = client.post("/generate", json=_spec_payload())
    assert res.status_code == 503


def test_job_row_survives_a_queue_outage(client, any_channel, broken_pool, job_db):
    """Recovery property: the row is committed before the enqueue attempt, so
    the request is not lost and can be re-enqueued."""
    client.post("/generate", json=_spec_payload(topic="survives outage"))
    rows = job_db.list_jobs()
    assert len(rows) == 1
    assert rows[0].status == "queued"


def test_batch_queue_outage_returns_503(client, any_channel, broken_pool):
    res = client.post("/generate/batch", json={
        "channel_id": "test_channel", "niche": "usa_finance", "count": 3,
    })
    assert res.status_code == 503


async def test_enqueue_error_is_a_runtime_error(job_db, monkeypatch):
    """The topic-intelligence bridge catches broad exceptions; EnqueueError
    must stay compatible with what previously propagated from here."""
    assert issubclass(gen.EnqueueError, RuntimeError)


# --- batch -----------------------------------------------------------------


def test_batch_enqueues_the_requested_count(client, any_channel, pool):
    res = client.post("/generate/batch", json={
        "channel_id": "test_channel", "niche": "usa_election", "count": 3,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 3
    assert len(set(body["job_ids"])) == 3
    assert len(pool.enqueued) == 3


def test_batch_reuses_one_pool_for_every_spec(client, any_channel, monkeypatch):
    """Performance: previously one pool was created per spec in the loop."""
    created = []

    async def _create_pool(*_a, **_kw):
        fake = FakePool()
        created.append(fake)
        return fake

    monkeypatch.setattr(gen, "create_pool", _create_pool)
    client.post("/generate/batch", json={
        "channel_id": "test_channel", "niche": "usa_facts", "count": 5,
    })
    assert len(created) == 1, "batch should build one pool, not one per spec"
    assert len(created[0].enqueued) == 5
    assert created[0].closed is True


def test_batch_without_a_topic_uses_trending_placeholders(client, any_channel, pool, job_db):
    client.post("/generate/batch", json={
        "channel_id": "test_channel", "niche": "usa_history", "count": 2,
    })
    topics = {j.topic for j in job_db.list_jobs()}
    assert all(t.startswith("__trending__:usa_history:") for t in topics)
