from __future__ import annotations

import pytest


@pytest.fixture
def auth_db(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, create_engine

    from app import db
    from app.auth.models import AUTH_TABLES
    from app.config import settings

    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}", echo=False)
    SQLModel.metadata.create_all(
        engine, tables=[db.Job.__table__, *[model.__table__ for model in AUTH_TABLES]]
    )
    monkeypatch.setattr(db, "_engine", engine, raising=True)
    monkeypatch.setattr(settings(), "auth_required", True)
    monkeypatch.setattr(
        settings(), "auth_secret_key", "isolated-test-secret-with-sufficient-length"
    )
    return engine


@pytest.fixture
def auth_client(auth_db):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def make_user(auth_db):
    from sqlmodel import Session

    from app.auth.models import User
    from app.auth.security import hash_password

    def _make(
        email: str = "user@example.com",
        password: str = "correct horse battery staple",
        role: str = "user",
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
        )
        with Session(auth_db) as s:
            s.add(user)
            s.commit()
            s.refresh(user)
        return user

    return _make


@pytest.fixture
def login(auth_client):
    def _login(
        email: str = "user@example.com",
        password: str = "correct horse battery staple",
    ):
        return auth_client.post(
            "/auth/login", json={"email": email, "password": password}
        )

    return _login
