"""
Persistence. SQLite via SQLModel for v1 (local-first). Swap to Postgres by
changing DATABASE_URL only — no model changes. The SceneGraph and metadata are
stored as JSON blobs; we don't normalize scenes into tables (no query need).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, Session, create_engine, select

from .config import settings

_engine = create_engine(settings().database_url, echo=False)


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)               # == VideoSpec.id
    channel_id: str
    niche: str
    topic: str
    status: str = "queued"
    error: Optional[str] = None
    spec_json: str = "{}"                            # serialized VideoSpec
    scene_graph_json: Optional[str] = None          # serialized SceneGraph
    metadata_json: Optional[str] = None             # title/desc/tags/thumbnail
    output_mp4: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    SQLModel.metadata.create_all(_engine)


def get_session() -> Session:
    return Session(_engine)


def upsert_job(job: Job) -> None:
    job.updated_at = datetime.now(timezone.utc)
    with get_session() as s:
        s.merge(job)
        s.commit()


def get_job(job_id: str) -> Optional[Job]:
    with get_session() as s:
        return s.get(Job, job_id)


def list_jobs(status: str | None = None, limit: int = 100) -> list[Job]:
    with get_session() as s:
        stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Job.status == status)
        return list(s.exec(stmt))


def set_status(job_id: str, status: str, error: str | None = None) -> None:
    with get_session() as s:
        job = s.get(Job, job_id)
        if job:
            job.status = status
            job.error = error
            job.updated_at = datetime.now(timezone.utc)
            s.add(job)
            s.commit()
