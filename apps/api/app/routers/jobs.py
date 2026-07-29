"""Job status, listing, approval gate, and artifact retrieval for the dashboard."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..db import Job, get_job, list_jobs, set_status

router = APIRouter(prefix="/jobs", tags=["jobs"])

#: A job in one of these states has finished. Rejecting one would overwrite a
#: real outcome (and, for `failed`, discard the original error), so it is
#: refused rather than silently applied.
TERMINAL_STATUSES = {"done", "failed"}


def _public(job: Job) -> dict:
    """The projection every job endpoint returns.

    Deliberately excludes `spec_json`, `scene_graph_json` and `metadata_json`:
    they are large internal blobs. `GET /jobs/{id}` previously returned the raw
    SQLModel row, so the same job had a different shape (and leaked those
    blobs) depending on whether you fetched it from the list or by id.
    """
    return {
        "id": job.id,
        "channel": job.channel_id,
        "niche": job.niche,
        "topic": job.topic,
        "status": job.status,
        "error": job.error,
        "mp4": job.output_mp4,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("")
def all_jobs(status: str | None = None):
    return [_public(j) for j in list_jobs(status=status)]


@router.get("/{job_id}")
def one_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    # Flags rather than the blobs themselves: callers need to know whether a
    # scene graph / metadata exists without being handed several hundred KB.
    return _public(job) | {
        "has_scene_graph": job.scene_graph_json is not None,
        "has_metadata": job.metadata_json is not None,
    }


@router.post("/{job_id}/approve")
async def approve(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.status != "awaiting_approval":
        raise HTTPException(409, f"job is {job.status}, not awaiting_approval")
    set_status(job_id, "approved")
    # Phase 5: enqueue upload here
    return {"ok": True, "id": job_id, "status": "approved"}


@router.post("/{job_id}/reject")
def reject(job_id: str, reason: str = "rejected by reviewer"):
    """Reject a job under review.

    Previously this called `set_status` unconditionally. `set_status` no-ops
    when the id does not exist, so rejecting an unknown job returned
    `{"ok": true}` — and rejecting an already-finished job silently flipped it
    to `failed`, discarding its real outcome.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.status in TERMINAL_STATUSES:
        raise HTTPException(409, f"job is already {job.status}; refusing to overwrite a terminal state")
    set_status(job_id, "failed", error=reason)
    return {"ok": True, "id": job_id, "status": "failed", "reason": reason}


@router.get("/{job_id}/video")
def video(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if not job.output_mp4:
        raise HTTPException(404, "no render yet")
    path = Path(job.output_mp4)
    # FileResponse does not check the path until it streams, so a recorded-but-
    # missing render surfaced as an unhandled 500 mid-response instead of a
    # usable status code.
    if not path.is_file():
        raise HTTPException(410, "render is recorded for this job but the file is missing from disk")
    return FileResponse(path, media_type="video/mp4", filename=f"{job.id}.mp4")
