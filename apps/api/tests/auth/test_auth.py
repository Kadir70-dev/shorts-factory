from __future__ import annotations

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
    assert auth_client.post(
        "/auth/refresh", json={"refresh_token": old}
    ).status_code == 401
    assert auth_client.post(
        "/auth/refresh", json={"refresh_token": new}
    ).status_code == 200


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


def test_admin_routes_reject_normal_user(make_user, login, auth_client):
    make_user()
    token = login().json()["access_token"]
    response = auth_client.get("/auth/users", headers=_bearer(token))
    assert response.status_code == 403


def test_admin_user_management_never_leaks_hashes(make_user, login, auth_client):
    make_user(email="admin@example.com", role="admin")
    token = login("admin@example.com").json()["access_token"]
    created = auth_client.post(
        "/auth/users",
        headers=_bearer(token),
        json={"email": "new@example.com", "password": "secret", "role": "user"},
    )
    assert created.status_code == 200
    listed = auth_client.get("/auth/users", headers=_bearer(token))
    patched = auth_client.patch(
        f"/auth/users/{created.json()['id']}",
        headers=_bearer(token),
        json={"role": "admin", "is_active": False},
    )
    for response in (created, listed, patched):
        assert response.status_code == 200
        _assert_no_hashes(response.json())


def test_api_key_auth_revocation_expiry_and_one_time_raw_value(
    auth_db, make_user, login, auth_client
):
    from app.auth.models import ApiKey

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
    assert all(row.key_hash != raw and row.key_hash != expired for row in rows)


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


def test_register_respects_open_setting(auth_client, monkeypatch):
    from app.config import settings

    closed = auth_client.post(
        "/auth/register",
        json={"email": "closed@example.com", "password": "secret", "role": "user"},
    )
    assert closed.status_code == 403

    monkeypatch.setattr(settings(), "auth_registration_open", True)
    response = auth_client.post(
        "/auth/register",
        json={"email": "open@example.com", "password": "secret", "role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "user"
    _assert_no_hashes(response.json())


def test_bootstrap_creates_admin_and_refuses_second(auth_db):
    from app.auth.bootstrap import bootstrap_admin
    from app.auth.models import ROLE_ADMIN

    user = bootstrap_admin("first@example.com", "secret")
    assert user.role == ROLE_ADMIN
    with pytest.raises(RuntimeError, match="admin already exists"):
        bootstrap_admin("second@example.com", "different")
