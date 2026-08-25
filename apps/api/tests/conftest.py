"""
Global test setup.

Every test runs with NO real API keys and NO network. The environment is pinned
here BEFORE `app.config` / `app.topic_intelligence.settings` are imported, so the
cached Settings objects never see a developer's real .env.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

APPS_API = Path(__file__).resolve().parents[1]
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

# Isolated SQLite file for the whole session — never the repo's data/factory.db.
_TMP_DB = Path(tempfile.mkdtemp(prefix="ti-tests-")) / "test.db"

os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP_DB}",
    # Hard-off: no provider may accidentally reach the network in a test.
    "GEMINI_API_KEY": "",
    "GEMINI_RANKER_ENABLED": "true",
    "GEMINI_GROUNDING_ENABLED": "false",
    "GEMINI_MODEL": "gemini-2.5-flash",
    "GEMINI_DAILY_BUDGET_USD": "1.0",
    "GOOGLE_TRENDS_ENABLED": "false",
    "GOOGLE_TRENDS_BASE_URL": "",
    "YOUTUBE_TRENDS_ENABLED": "true",
    "YOUTUBE_DATA_API_KEY": "",
    "REDDIT_ENABLED": "false",
    "REDDIT_CLIENT_ID": "",
    "REDDIT_CLIENT_SECRET": "",
    "X_TRENDS_ENABLED": "false",
    "X_BEARER_TOKEN": "",
    "ECONOMIC_CALENDAR_ENABLED": "false",
    "ECONOMIC_CALENDAR_PROVIDER": "",
    "FINANCE_NEWS_ENABLED": "true",
    "NEWS_API_KEY": "",
    "TI_AUTO_ENQUEUE": "false",
    "DIRECTOR_MODE": "mock",
    # Existing router tests predate authentication and exercise their own logic.
    # Auth-specific tests explicitly enable this against isolated auth tables.
    "AUTH_REQUIRED": "false",
    "AUTH_SECRET_KEY": "test-only-auth-secret-that-is-long-and-stable",
})


@pytest.fixture(autouse=True)
def _reset_module_state():
    """Circuit breakers and the HTTP cache are process-global by design."""
    from app.topic_intelligence.http import reset_cache, reset_circuits

    reset_circuits()
    reset_cache()
    yield
    reset_circuits()
    reset_cache()


@pytest.fixture
def ti_repo(tmp_path, monkeypatch):
    """A repository backed by a fresh SQLite file per test."""
    from sqlmodel import Session, SQLModel, create_engine

    from app.topic_intelligence import repository as repo_mod
    from app.topic_intelligence.tables import TI_TABLES

    engine = create_engine(f"sqlite:///{tmp_path / 'ti.db'}", echo=False)
    SQLModel.metadata.create_all(engine, tables=[t.__table__ for t in TI_TABLES])
    monkeypatch.setattr(repo_mod, "_engine", engine, raising=False)

    def _session():
        return Session(engine)

    return repo_mod.TopicIntelligenceRepository(session_factory=_session)
