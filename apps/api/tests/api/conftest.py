"""Fixtures for the API-surface tests.

Each test gets its own SQLite file and its own FastAPI TestClient, so job
state never leaks between tests and nothing touches data/factory.db.

Mirrors the `ti_repo` fixture pattern in the parent conftest: build an engine
against a tmp_path database and monkeypatch the module-level `_engine` that
`app.db` created at import time.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    """Point `app.db` at a fresh SQLite file and create the Job table."""
    from sqlmodel import SQLModel, create_engine

    from app import db as db_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}", echo=False)
    SQLModel.metadata.create_all(engine, tables=[db_mod.Job.__table__])
    monkeypatch.setattr(db_mod, "_engine", engine, raising=True)
    return db_mod


@pytest.fixture
def client(job_db):
    """TestClient over the real app, with the job store isolated.

    The app's lifespan runs `init_db()` against the real engine, so it is not
    triggered here — these tests exercise routers, not startup wiring.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def make_job(job_db):
    """Insert a Job row directly and return it."""
    def _make(job_id: str = "vid_test01", **overrides):
        fields = {
            "id": job_id,
            "channel_id": "test_channel",
            "niche": "usa_finance",
            "topic": "a test topic",
            "status": "queued",
        }
        fields.update(overrides)
        job = job_db.Job(**fields)
        job_db.upsert_job(job)
        return job

    return _make
