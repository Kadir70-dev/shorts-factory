"""Regression tests for runtime project-root resolution.

Guards the bug where `.env` (shared by local runs and `docker-compose env_file`)
pinned DATA_DIR=/repo/data, so a local WSL run tried to write /repo/data/jobs/...
and died with `PermissionError: [Errno 13] Permission denied: '/repo'`.

Contract under test (app/config.py::_resolve_root):
  1. PROJECT_ROOT wins everywhere.
  2. A source checkout (<root>/apps/api/app/config.py with a sibling apps/) →
     that checkout root. This is local WSL / bare metal.
  3. No checkout layout (the container, where app/ is COPYed to /app/app) →
     /repo, matching the Compose bind mounts.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import app.config as config


@pytest.fixture
def fresh_config(monkeypatch):
    """Reimport app.config with a clean env and no cached settings()."""
    def _load(**env):
        for key in ("PROJECT_ROOT", "DATA_DIR", "DATABASE_URL",
                    "YOUTUBE_CLIENT_SECRET_PATH"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        module = importlib.reload(config)
        module.settings.cache_clear()
        return module

    yield _load
    importlib.reload(config).settings.cache_clear()


# ------------------------- 2. local WSL / checkout ------------------------- #
def test_local_checkout_resolves_to_repo_root(fresh_config):
    """Local WSL: root is the checkout, never /repo."""
    cfg = fresh_config()
    expected = Path(config.__file__).resolve().parents[3]

    assert cfg.ROOT == expected
    assert (cfg.ROOT / "apps").is_dir()
    assert cfg.ROOT != Path("/repo")
    assert cfg.DATA_DIR == expected / "data"
    assert not str(cfg.DATA_DIR).startswith("/repo")


def test_local_settings_write_inside_the_checkout(fresh_config):
    """The values the pipeline actually uses stay inside the project dir."""
    cfg = fresh_config()
    s = cfg.Settings()
    root = str(Path(config.__file__).resolve().parents[3])

    assert str(s.data_dir).startswith(root)
    assert str(s.data_dir / "jobs").startswith(root)   # the failing write path
    assert root in s.database_url
    assert "/repo" not in s.database_url
    assert not str(s.youtube_client_secret_path).startswith("/repo")


def test_local_data_dir_is_writable(fresh_config):
    """The regression itself: the resolved data dir must be usable, not /repo."""
    cfg = fresh_config()
    probe = cfg.DATA_DIR / "jobs"
    probe.mkdir(parents=True, exist_ok=True)   # raised PermissionError before
    assert probe.is_dir()


# ----------------------------- 3. Docker ----------------------------------- #
def test_container_layout_resolves_to_repo(fresh_config, monkeypatch):
    """Inside the image config.py is /app/app/config.py — no checkout → /repo."""
    cfg = fresh_config()
    monkeypatch.setattr(cfg, "_CONFIG_FILE", Path("/app/app/config.py"))
    assert cfg._resolve_root() == Path("/repo")


def test_container_layout_ignores_a_short_path(fresh_config, monkeypatch):
    """Fewer than 4 parents must fall back to /repo, not IndexError."""
    cfg = fresh_config()
    monkeypatch.setattr(cfg, "_CONFIG_FILE", Path("/config.py"))
    assert cfg._resolve_root() == Path("/repo")


def test_apps_sibling_missing_falls_back_to_repo(fresh_config, monkeypatch, tmp_path):
    """Deep path but no sibling apps/ → not a checkout → /repo."""
    cfg = fresh_config()
    monkeypatch.setattr(
        cfg, "_CONFIG_FILE", tmp_path / "a" / "b" / "c" / "config.py")
    assert cfg._resolve_root() == Path("/repo")


def test_compose_env_pins_repo(fresh_config):
    """docker-compose sets PROJECT_ROOT/DATA_DIR=/repo; they must be honoured."""
    cfg = fresh_config(PROJECT_ROOT="/repo", DATA_DIR="/repo/data",
                       DATABASE_URL="sqlite:////repo/data/factory.db")
    assert cfg.ROOT == Path("/repo")
    assert cfg.DATA_DIR == Path("/repo/data")

    s = cfg.Settings()
    assert s.data_dir == Path("/repo/data")
    assert s.database_url == "sqlite:////repo/data/factory.db"


# --------------------------- 1. explicit override --------------------------- #
def test_project_root_override_wins(fresh_config, tmp_path):
    cfg = fresh_config(PROJECT_ROOT=str(tmp_path))
    assert cfg.ROOT == tmp_path.resolve()
    assert cfg.DATA_DIR == tmp_path.resolve() / "data"
    assert cfg.CONFIG_DIR == tmp_path.resolve() / "config"


def test_no_repo_path_leaks_into_local_settings(fresh_config):
    """Belt and braces: no setting may carry /repo on a local checkout."""
    cfg = fresh_config()
    s = cfg.Settings()
    leaked = [
        name for name, value in s.model_dump().items()
        if isinstance(value, (str, Path)) and str(value).startswith("/repo")
    ]
    assert leaked == [], f"settings still pinned to /repo: {leaked}"
