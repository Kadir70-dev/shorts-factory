from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_no_hashes(value) -> None:
    if isinstance(value, dict):
        assert not {"password_hash", "token_hash", "key_hash"} & value.keys()
        for child in value.values():
            _assert_no_hashes(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_hashes(child)


def test_password_hashing_round_trip():
    from app.auth.security import hash_password, verify_password

    raw = "not stored as plaintext"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed)
    assert not verify_password("wrong", hashed)


def test_login_success_and_me(auth_client, make_user, login):
    user = make_user()
    response = login()
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]

    me = auth_client.get("/auth/me", headers=_bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["id"] == user.id
    assert me.json()["email"] == user.email
    _assert_no_hashes(me.json())


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("user@example.com", "wrong"),
        ("missing@example.com", "correct horse battery staple"),
    ],
)
def test_login_failure_is_generic(make_user, login, email, password):
    make_user()
    response = login(email, password)
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"


def test_inactive_user_cannot_login(make_user, login):
    make_user(is_active=False)
    assert login().status_code == 401


def test_missing_and_inactive_logins_use_dummy_hash(monkeypatch):
    from starlette.requests import Request

    from app.auth import security
    from app.routers import auth

    request = Request({"type": "http", "client": ("timing-test", 1), "headers": []})
    seen_hashes = []
    monkeypatch.setattr(auth.repository, "get_user_by_email", lambda _email: None)
    monkeypatch.setattr(
        auth,
        "verify_password",
        lambda _password, password_hash: seen_hashes.append(password_hash) or False,
    )
    with pytest.raises(Exception) as missing:
        auth.login(auth.LoginRequest(email="missing@example.com", password="x"), request)
    assert missing.value.status_code == 401
    assert seen_hashes == [security._DUMMY_HASH]


def test_expired_and_tampered_access_tokens_are_rejected(
    auth_client, make_user, monkeypatch
):
    from app.auth.security import create_access_token
    from app.config import settings

    user = make_user()
    monkeypatch.setattr(settings(), "auth_access_token_minutes", -1)
    expired = create_access_token(user.id, user.role)
    assert auth_client.get("/auth/me", headers=_bearer(expired)).status_code == 401

    monkeypatch.setattr(settings(), "auth_access_token_minutes", 30)
    valid = create_access_token(user.id, user.role)
    tampered = valid[:-1] + ("a" if valid[-1] != "a" else "b")
    assert auth_client.get("/auth/me", headers=_bearer(tampered)).status_code == 401
    assert auth_client.get("/auth/me", headers=_bearer("garbage")).status_code == 401


def test_refresh_rotates_and_old_token_stops_working(make_user, login, auth_client):
    make_user()
    old = login().json()["refresh_token"]
    rotated = auth_client.post("/auth/refresh", json={"refresh_token": old})
    assert rotated.status_code == 200
    new = rotated.json()["refresh_token"]
    assert new != old
    newest = auth_client.post(
        "/auth/refresh", json={"refresh_token": new}
    )
    assert newest.status_code == 200
    assert auth_client.post(
        "/auth/refresh", json={"refresh_token": old}
    ).status_code == 401
    assert auth_client.post(
        "/auth/refresh", json={"refresh_token": newest.json()["refresh_token"]}
    ).status_code == 401


def test_login_and_refresh_return_usable_access_tokens(
    make_user, login, auth_client
):
    user = make_user()

    logged_in = login()
    assert logged_in.status_code == 200
    login_access = logged_in.json()["access_token"]
    login_me = auth_client.get("/auth/me", headers=_bearer(login_access))
    assert login_me.status_code == 200
    assert login_me.json()["id"] == user.id

    refreshed = auth_client.post(
        "/auth/refresh",
        json={"refresh_token": logged_in.json()["refresh_token"]},
    )
    assert refreshed.status_code == 200
    refresh_access = refreshed.json()["access_token"]
    refresh_me = auth_client.get("/auth/me", headers=_bearer(refresh_access))
    assert refresh_me.status_code == 200
    assert refresh_me.json()["id"] == user.id


def test_logout_is_idempotent_and_revokes(make_user, login, auth_client):
    make_user()
    token = login().json()["refresh_token"]
    for _ in range(2):
        assert auth_client.post(
            "/auth/logout", json={"refresh_token": token}
        ).status_code == 200
    assert auth_client.post(
        "/auth/refresh", json={"refresh_token": token}
    ).status_code == 401


def test_user_management_requires_authentication(auth_client):
    assert auth_client.post(
        "/auth/users",
        json={"email": "new@example.com", "password": "long enough password"},
    ).status_code == 401
    assert auth_client.patch(
        "/auth/users/unknown", json={"is_active": False}
    ).status_code == 401


def test_admin_user_management_never_leaks_hashes(make_user, login, auth_client):
    make_user(email="admin@example.com")
    token = login("admin@example.com").json()["access_token"]
    created = auth_client.post(
        "/auth/users",
        headers=_bearer(token),
        json={
            "email": "new@example.com",
            "password": "a secure password",
            "role": "admin",
        },
    )
    assert created.status_code == 200
    listed = auth_client.get("/auth/users", headers=_bearer(token))
    patched = auth_client.patch(
        f"/auth/users/{created.json()['id']}",
        headers=_bearer(token),
        json={"role": "admin"},
    )
    for response in (created, listed, patched):
        assert response.status_code == 200
        _assert_no_hashes(response.json())


def test_api_key_auth_revocation_expiry_and_one_time_raw_value(
    auth_db, make_user, login, auth_client
):
    from app.auth.models import ApiKey
    from app.auth.security import secret_hash

    make_user()
    access = login().json()["access_token"]
    created = auth_client.post(
        "/auth/api-keys",
        headers=_bearer(access),
        json={"name": "automation"},
    )
    assert created.status_code == 200
    raw = created.json()["key"]
    assert raw.startswith("sf_")
    _assert_no_hashes(created.json())

    listed = auth_client.get("/auth/api-keys", headers=_bearer(access))
    assert listed.status_code == 200
    assert "key" not in listed.json()[0]
    _assert_no_hashes(listed.json())
    assert auth_client.get("/auth/me", headers=_bearer(raw)).status_code == 200

    key_id = created.json()["id"]
    assert auth_client.delete(
        f"/auth/api-keys/{key_id}", headers=_bearer(access)
    ).status_code == 200
    assert auth_client.get("/auth/me", headers=_bearer(raw)).status_code == 401

    expired = auth_client.post(
        "/auth/api-keys",
        headers=_bearer(access),
        json={
            "name": "expired",
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    ).json()["key"]
    assert auth_client.get("/auth/me", headers=_bearer(expired)).status_code == 401

    with Session(auth_db) as s:
        rows = list(s.exec(select(ApiKey)))
    known = next(row for row in rows if row.id == key_id)
    assert known.key_hash == secret_hash(raw)


def test_existing_routes_are_protected_and_health_is_public(
    auth_client, monkeypatch
):
    from app.config import settings

    assert auth_client.get("/jobs").status_code == 401
    assert auth_client.post("/generate", json={}).status_code == 401
    assert auth_client.get("/health").status_code == 200

    monkeypatch.setattr(settings(), "auth_required", False)
    assert auth_client.get("/jobs").status_code == 200
    assert auth_client.post("/generate", json={}).status_code == 422
    assert auth_client.get("/health").status_code == 200
    assert auth_client.get("/auth/users").status_code == 401
    assert auth_client.patch(
        "/auth/users/unknown", json={"is_active": False}
    ).status_code == 401
    assert auth_client.get("/auth/me").status_code == 401


def test_register_route_does_not_exist(auth_client):
    response = auth_client.post(
        "/auth/register",
        json={"email": "stranger@example.com", "password": "long enough password"},
    )
    assert response.status_code == 404


def test_user_role_is_rejected_on_create_and_patch(
    auth_client, make_user, login
):
    operator = make_user()
    token = login().json()["access_token"]
    response = auth_client.post(
        "/auth/users",
        headers=_bearer(token),
        json={
            "email": "invalid-role@example.com",
            "password": "long enough password",
            "role": "user",
        },
    )
    assert response.status_code == 422
    response = auth_client.patch(
        f"/auth/users/{operator.id}",
        headers=_bearer(token),
        json={"role": "user"},
    )
    assert response.status_code == 422


def test_short_password_is_rejected(auth_client, make_user, login):
    make_user()
    token = login().json()["access_token"]
    response = auth_client.post(
        "/auth/users",
        headers=_bearer(token),
        json={"email": "short@example.com", "password": "too-short"},
    )
    assert response.status_code == 422


def test_login_rate_limit_returns_retry_after(
    auth_client, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings(), "auth_rate_limit_attempts", 2)
    for _ in range(2):
        assert auth_client.post(
            "/auth/login",
            json={"email": "missing@example.com", "password": "anything"},
        ).status_code == 401
    limited = auth_client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "anything"},
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1


def test_refresh_reuse_revokes_entire_session_chain(
    auth_client, make_user, login
):
    make_user()
    original = login().json()["refresh_token"]
    rotated = auth_client.post(
        "/auth/refresh", json={"refresh_token": original}
    ).json()["refresh_token"]
    assert auth_client.post(
        "/auth/refresh", json={"refresh_token": original}
    ).status_code == 401
    assert auth_client.post(
        "/auth/refresh", json={"refresh_token": rotated}
    ).status_code == 401


def test_password_change_works_and_revokes_sessions(
    auth_client, make_user, login
):
    make_user()
    logged_in = login()
    access = logged_in.json()["access_token"]
    refresh_token = logged_in.json()["refresh_token"]
    changed = auth_client.post(
        "/auth/me/password",
        headers=_bearer(access),
        json={
            "current_password": "correct horse battery staple",
            "new_password": "new correct horse battery staple",
        },
    )
    assert changed.status_code == 200
    assert auth_client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    ).status_code == 401
    assert login(password="correct horse battery staple").status_code == 401
    assert login(password="new correct horse battery staple").status_code == 200


def test_operator_can_patch_password(auth_client, make_user, login):
    operator = make_user()
    token = login().json()["access_token"]
    patched = auth_client.patch(
        f"/auth/users/{operator.id}",
        headers=_bearer(token),
        json={"password": "operator reset password"},
    )
    assert patched.status_code == 200
    assert login(password="operator reset password").status_code == 200


def test_revoke_all_sessions(auth_client, make_user, login):
    make_user()
    first = login().json()
    second = login().json()
    response = auth_client.post(
        "/auth/me/sessions/revoke-all",
        headers=_bearer(first["access_token"]),
    )
    assert response.status_code == 200
    for token in (first["refresh_token"], second["refresh_token"]):
        assert auth_client.post(
            "/auth/refresh", json={"refresh_token": token}
        ).status_code == 401


def test_last_operator_cannot_be_deactivated(auth_client, make_user, login):
    operator = make_user()
    token = login().json()["access_token"]
    response = auth_client.patch(
        f"/auth/users/{operator.id}",
        headers=_bearer(token),
        json={"is_active": False},
    )
    assert response.status_code == 409
    assert "last active operator" in response.json()["detail"]


def test_authenticated_m1_regression_paths(
    auth_client, auth_db, make_user, login, tmp_path
):
    from app.db import Job

    make_user()
    headers = _bearer(login().json()["access_token"])
    assert auth_client.post(
        "/jobs/unknown/reject", headers=headers
    ).status_code == 404

    with Session(auth_db) as s:
        s.add(
            Job(
                id="terminal",
                channel_id="test",
                niche="usa_finance",
                topic="terminal",
                status="done",
            )
        )
        s.add(
            Job(
                id="missing-video",
                channel_id="test",
                niche="usa_finance",
                topic="missing",
                status="done",
                output_mp4=str(tmp_path / "gone.mp4"),
            )
        )
        s.commit()

    assert auth_client.post(
        "/jobs/terminal/reject", headers=headers
    ).status_code == 409
    assert auth_client.get(
        "/jobs/missing-video/video", headers=headers
    ).status_code == 410
    unknown_channel = auth_client.post(
        "/generate",
        headers=headers,
        json={
            "channel_id": "definitely_missing_channel",
            "niche": "usa_finance",
            "topic": "test topic",
        },
    )
    assert unknown_channel.status_code == 404
    assert "/home/" not in str(unknown_channel.json())
    assert "config/channels" not in str(unknown_channel.json())


def test_bootstrap_creates_admin_and_refuses_second(auth_db):
    from app.auth.bootstrap import bootstrap_admin
    from app.auth.models import ROLE_ADMIN

    user = bootstrap_admin("first@example.com", "secret")
    assert user.role == ROLE_ADMIN
    with pytest.raises(RuntimeError, match="admin already exists"):
        bootstrap_admin("second@example.com", "different")


def test_signing_secret_write_is_atomic_and_empty_file_is_actionable(
    tmp_path, monkeypatch
):
    from app.auth import security
    from app.config import settings

    monkeypatch.setattr(security, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings(), "auth_secret_key", "")
    monkeypatch.setattr(settings(), "auth_required", True)
    monkeypatch.setattr(security, "_secret_key", None)
    value = security.initialize_signing_secret()
    path = tmp_path / "auth_secret.key"
    assert path.read_text(encoding="utf-8") == value
    assert not (tmp_path / "auth_secret.key.tmp").exists()

    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(security, "_secret_key", None)
    with pytest.raises(RuntimeError) as failure:
        security.initialize_signing_secret()
    message = str(failure.value)
    assert str(path) in message
    assert "delete it" in message
    assert "invalidates existing access tokens" in message


def test_bootstrap_password_argv_warns(monkeypatch, capsys):
    from app.auth import bootstrap

    monkeypatch.delenv("SHORTS_FACTORY_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(
        bootstrap,
        "bootstrap_admin",
        lambda email, password, force: type(
            "Result", (), {"email": email, "password": password}
        )(),
    )
    assert bootstrap.main(
        ["--email", "ci@example.com", "--password", "ci-only-secret"]
    ) == 0
    assert "--password exposes the password" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_disabled_auth_startup_warning_uses_logging(
    auth_db, monkeypatch, caplog
):
    from app import main
    from app.config import settings

    monkeypatch.setattr(settings(), "auth_required", False)
    with caplog.at_level(logging.WARNING):
        async with main.app.router.lifespan_context(main.app):
            pass
    assert "AUTHENTICATION IS DISABLED" in caplog.text
