"""Tests for /jobs — listing, retrieval, approval gate, rejection, artifacts.

This surface had no test coverage. Several of the assertions below pin
behaviour that was wrong before this milestone (see the docstrings).
"""
from __future__ import annotations


def test_health_is_ok(client):
    assert client.get("/health").json() == {"ok": True}


# --- listing ---------------------------------------------------------------


def test_list_is_empty_initially(client):
    assert client.get("/jobs").json() == []


def test_list_returns_created_jobs(client, make_job):
    make_job("vid_a", topic="alpha")
    make_job("vid_b", topic="beta")
    body = client.get("/jobs").json()
    assert {j["id"] for j in body} == {"vid_a", "vid_b"}


def test_list_filters_by_status(client, make_job):
    make_job("vid_q", status="queued")
    make_job("vid_d", status="done")
    body = client.get("/jobs", params={"status": "done"}).json()
    assert [j["id"] for j in body] == ["vid_d"]


def test_list_never_exposes_internal_blobs(client, make_job):
    make_job("vid_blob", spec_json='{"secret": "internal"}')
    body = client.get("/jobs").json()
    assert "spec_json" not in body[0]
    assert "internal" not in str(body)


# --- retrieval -------------------------------------------------------------


def test_get_unknown_job_is_404(client):
    assert client.get("/jobs/nope").status_code == 404


def test_get_returns_the_same_shape_as_the_list(client, make_job):
    """Regression: `GET /jobs/{id}` returned the raw SQLModel row while
    `GET /jobs` returned a projection, so one job had two shapes."""
    make_job("vid_shape")
    listed = client.get("/jobs").json()[0]
    single = client.get("/jobs/vid_shape").json()
    for key in listed:
        assert key in single, f"{key} missing from the detail response"


def test_get_does_not_leak_internal_blobs(client, make_job):
    """Regression: the detail endpoint returned spec_json / scene_graph_json /
    metadata_json verbatim."""
    make_job(
        "vid_leak",
        spec_json='{"api_key": "must-not-appear"}',
        scene_graph_json='{"scenes": "large blob"}',
        metadata_json='{"title": "blob"}',
    )
    body = client.get("/jobs/vid_leak").json()
    assert "spec_json" not in body
    assert "scene_graph_json" not in body
    assert "metadata_json" not in body
    assert "must-not-appear" not in str(body)


def test_get_flags_presence_of_blobs_without_returning_them(client, make_job):
    make_job("vid_flags", scene_graph_json='{"scenes": []}', metadata_json=None)
    body = client.get("/jobs/vid_flags").json()
    assert body["has_scene_graph"] is True
    assert body["has_metadata"] is False


# --- approval --------------------------------------------------------------


def test_approve_unknown_job_is_404(client):
    assert client.post("/jobs/nope/approve").status_code == 404


def test_approve_requires_awaiting_approval(client, make_job):
    make_job("vid_queued", status="queued")
    res = client.post("/jobs/vid_queued/approve")
    assert res.status_code == 409
    assert "awaiting_approval" in res.json()["detail"]


def test_approve_transitions_to_approved(client, make_job):
    make_job("vid_ok", status="awaiting_approval")
    assert client.post("/jobs/vid_ok/approve").json()["status"] == "approved"
    assert client.get("/jobs/vid_ok").json()["status"] == "approved"


def test_approve_twice_is_rejected(client, make_job):
    make_job("vid_twice", status="awaiting_approval")
    client.post("/jobs/vid_twice/approve")
    assert client.post("/jobs/vid_twice/approve").status_code == 409


# --- rejection -------------------------------------------------------------


def test_reject_unknown_job_is_404(client):
    """Regression: reject() called set_status() unconditionally, and
    set_status() no-ops for a missing id — so this returned {"ok": true}."""
    res = client.post("/jobs/does-not-exist/reject")
    assert res.status_code == 404


def test_reject_marks_the_job_failed_with_a_reason(client, make_job):
    make_job("vid_rej", status="awaiting_approval")
    body = client.post("/jobs/vid_rej/reject", params={"reason": "off-brand"}).json()
    assert body["status"] == "failed"
    assert body["reason"] == "off-brand"
    assert client.get("/jobs/vid_rej").json()["error"] == "off-brand"


def test_reject_has_a_default_reason(client, make_job):
    make_job("vid_rej2", status="awaiting_approval")
    assert client.post("/jobs/vid_rej2/reject").json()["reason"] == "rejected by reviewer"


def test_reject_refuses_to_overwrite_a_completed_job(client, make_job):
    """Regression: a `done` job could be flipped to `failed`, destroying the
    real outcome."""
    make_job("vid_done", status="done")
    res = client.post("/jobs/vid_done/reject")
    assert res.status_code == 409
    assert client.get("/jobs/vid_done").json()["status"] == "done"


def test_reject_refuses_to_overwrite_an_existing_failure(client, make_job):
    """Regression: re-rejecting a failed job discarded its original error."""
    make_job("vid_failed", status="failed", error="render crashed at scene 3")
    assert client.post("/jobs/vid_failed/reject").status_code == 409
    assert client.get("/jobs/vid_failed").json()["error"] == "render crashed at scene 3"


# --- artifact --------------------------------------------------------------


def test_video_unknown_job_is_404(client):
    assert client.get("/jobs/nope/video").status_code == 404


def test_video_without_a_render_is_404(client, make_job):
    make_job("vid_norender", output_mp4=None)
    assert client.get("/jobs/vid_norender/video").status_code == 404


def test_video_with_a_missing_file_is_410_not_500(client, make_job, tmp_path):
    """Regression: FileResponse does not stat the path until it streams, so a
    recorded-but-deleted render raised an unhandled error mid-response."""
    make_job("vid_gone", output_mp4=str(tmp_path / "deleted.mp4"))
    res = client.get("/jobs/vid_gone/video")
    assert res.status_code == 410
    assert "missing from disk" in res.json()["detail"]


def test_video_streams_an_existing_render(client, make_job, tmp_path):
    mp4 = tmp_path / "out.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-payload")
    make_job("vid_real", output_mp4=str(mp4))
    res = client.get("/jobs/vid_real/video")
    assert res.status_code == 200
    assert res.headers["content-type"] == "video/mp4"
    assert res.content == mp4.read_bytes()
