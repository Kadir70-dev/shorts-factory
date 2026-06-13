"""Job status, listing, approval gate, and artifact retrieval for the dashboard."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..db import get_job, list_jobs, set_status

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def all_jobs(status: str | None = None):
    return [
        {"id": j.id, "channel": j.channel_id, "topic": j.topic,
         "status": j.status, "error": j.error, "mp4": j.output_mp4}
        for j in list_jobs(status=status)
    ]


@router.get("/{job_id}")
def one_job(job_id: str):
    j = get_job(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@router.post("/{job_id}/approve")
async def approve(job_id: str):
    j = get_job(job_id)
    if not j or j.status != "awaiting_approval":
        raise HTTPException(409, "job not awaiting approval")
    set_status(job_id, "approved")
    # Phase 5: enqueue upload here
    return {"ok": True, "status": "approved"}


@router.post("/{job_id}/reject")
def reject(job_id: str):
    set_status(job_id, "failed", error="rejected by reviewer")
    return {"ok": True}


@router.get("/{job_id}/video")
def video(job_id: str):
    j = get_job(job_id)
    if not j or not j.output_mp4:
        raise HTTPException(404, "no render yet")
    return FileResponse(j.output_mp4, media_type="video/mp4")
