"""Authentication and user-management HTTP endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..auth import repository
from ..auth.deps import get_current_user, require_admin
from ..auth.rate_limit import auth_limiter
from ..auth.models import ApiKey, RefreshToken, User, VALID_ROLES
from ..auth.security import (
    _DUMMY_HASH,
    create_access_token,
    hash_password,
    new_api_key,
    new_refresh_token,
    secret_hash,
    verify_password,
)
from ..config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
LOGIN_ERROR = "invalid email or password"


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserCreate(BaseModel):
    email: str
    password: str
    role: str = "admin"


class UserPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class ApiKeyCreate(BaseModel):
    name: str
    expires_at: datetime | None = None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _user_public(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
    }


def _key_public(key: ApiKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "last_used_at": key.last_used_at,
        "expires_at": key.expires_at,
        "revoked_at": key.revoked_at,
        "created_at": key.created_at,
    }


def _create_user(data: UserCreate) -> User:
    if data.role not in VALID_ROLES:
        raise HTTPException(422, "role must be 'admin'")
    email = data.email.strip().lower()
    if not email or not data.password:
        raise HTTPException(422, "email and password are required")
    _validate_password(data.password)
    user = User(email=email, password_hash=hash_password(data.password), role=data.role)
    try:
        with repository.session() as s:
            s.add(user)
            s.commit()
            s.refresh(user)
    except IntegrityError as exc:
        raise HTTPException(409, "email already registered") from exc
    return user


def _validate_password(password: str) -> None:
    minimum = settings().auth_min_password_length
    if len(password) < minimum:
        raise HTTPException(
            422, f"password must be at least {minimum} characters long"
        )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _revoke_all_sessions(s, user_id: str, now: datetime) -> None:
    s.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


def _issue_refresh(user: User, user_agent: str = "") -> tuple[str, RefreshToken]:
    raw, token_hash = new_refresh_token()
    row = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings().auth_refresh_token_days),
        user_agent=user_agent,
    )
    return raw, row


@router.post("/login")
def login(data: LoginRequest, request: Request):
    email = data.email.strip().lower()
    client_ip = _client_ip(request)
    auth_limiter.check(f"login:ip:{client_ip}", f"login:email:{email}")
    user = repository.get_user_by_email(email)
    if user is None or not user.is_active:
        verify_password(data.password, _DUMMY_HASH)
        raise HTTPException(401, LOGIN_ERROR)
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(401, LOGIN_ERROR)
    now = datetime.now(timezone.utc)
    raw_refresh, refresh = _issue_refresh(
        user, request.headers.get("user-agent", "")
    )
    with repository.session() as s:
        stored = s.get(User, user.id)
        assert stored is not None
        stored.last_login_at = now
        stored.updated_at = now
        user_id, user_role = stored.id, stored.role
        s.add(stored)
        s.add(refresh)
        s.commit()
    return {
        "access_token": create_access_token(user_id, user_role),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
    }


@router.post("/refresh")
def refresh(data: RefreshRequest, request: Request):
    auth_limiter.check(f"refresh:ip:{_client_ip(request)}")
    old_hash = secret_hash(data.refresh_token)
    now = datetime.now(timezone.utc)
    with repository.session() as s:
        old = s.exec(
            select(RefreshToken).where(RefreshToken.token_hash == old_hash)
        ).first()
        if old is None:
            raise HTTPException(401, "invalid refresh token")
        if old.revoked_at is not None:
            _revoke_all_sessions(s, old.user_id, now)
            s.commit()
            logging.warning(
                "revoked all refresh sessions after token reuse for user_id=%s",
                old.user_id,
            )
            raise HTTPException(401, "invalid refresh token")
        if _aware(old.expires_at) <= now:
            raise HTTPException(401, "invalid refresh token")
        user = s.get(User, old.user_id)
        if user is None or not user.is_active:
            raise HTTPException(401, "invalid refresh token")
        raw_refresh, replacement = _issue_refresh(
            user, request.headers.get("user-agent", "")
        )
        user_id, user_role = user.id, user.role
        revoked = s.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == old_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        if revoked.rowcount != 1:
            s.rollback()
            with repository.session() as cleanup:
                _revoke_all_sessions(cleanup, old.user_id, now)
                cleanup.commit()
            logging.warning(
                "revoked all refresh sessions after concurrent token reuse "
                "for user_id=%s",
                old.user_id,
            )
            raise HTTPException(401, "invalid refresh token")
        s.add(replacement)
        s.commit()
    return {
        "access_token": create_access_token(user_id, user_role),
        "refresh_token": raw_refresh,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout(data: RefreshRequest):
    repository.revoke_refresh(secret_hash(data.refresh_token), datetime.now(timezone.utc))
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_public(user)


@router.post("/me/sessions/revoke-all")
def revoke_all_sessions(user: User = Depends(get_current_user)):
    with repository.session() as s:
        _revoke_all_sessions(s, user.id, datetime.now(timezone.utc))
        s.commit()
    return {"ok": True}


@router.post("/me/password")
def change_password(data: PasswordChange, user: User = Depends(get_current_user)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(401, "current password is incorrect")
    _validate_password(data.new_password)
    now = datetime.now(timezone.utc)
    with repository.session() as s:
        stored = s.get(User, user.id)
        if stored is None or not stored.is_active:
            raise HTTPException(401, "invalid credentials")
        stored.password_hash = hash_password(data.new_password)
        stored.updated_at = now
        s.add(stored)
        _revoke_all_sessions(s, user.id, now)
        s.commit()
    return {"ok": True}


@router.post("/users")
def create_user(
    data: UserCreate, request: Request, _admin: User = Depends(require_admin)
):
    auth_limiter.check(f"users:ip:{_client_ip(request)}")
    return _user_public(_create_user(data))


@router.get("/users")
def list_users(_admin: User = Depends(require_admin)):
    with repository.session() as s:
        users = list(s.exec(select(User).order_by(User.created_at)))
    return [_user_public(user) for user in users]


@router.patch("/users/{user_id}")
def patch_user(
    user_id: str, data: UserPatch, _admin: User = Depends(require_admin)
):
    if data.role is not None and data.role not in VALID_ROLES:
        raise HTTPException(422, "role must be 'admin'")
    if data.password is not None:
        _validate_password(data.password)
    with repository.session() as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(404, "user not found")
        if data.is_active is False and user.is_active:
            other_active = s.exec(
                select(func.count())
                .select_from(User)
                .where(User.is_active.is_(True), User.id != user.id)
            ).one()
            if other_active == 0:
                raise HTTPException(
                    409, "cannot deactivate the last active operator"
                )
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.password is not None:
            user.password_hash = hash_password(data.password)
            _revoke_all_sessions(s, user.id, datetime.now(timezone.utc))
        user.updated_at = datetime.now(timezone.utc)
        s.add(user)
        s.commit()
        s.refresh(user)
        result = _user_public(user)
    return result


@router.post("/api-keys")
def create_api_key(data: ApiKeyCreate, user: User = Depends(get_current_user)):
    raw, key_hash = new_api_key()
    row = ApiKey(
        user_id=user.id,
        key_hash=key_hash,
        name=data.name,
        expires_at=data.expires_at,
    )
    with repository.session() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
    return _key_public(row) | {"key": raw}


@router.get("/api-keys")
def list_api_keys(user: User = Depends(get_current_user)):
    with repository.session() as s:
        rows = list(
            s.exec(
                select(ApiKey)
                .where(ApiKey.user_id == user.id)
                .order_by(ApiKey.created_at)
            )
        )
    return [_key_public(row) for row in rows]


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: str, user: User = Depends(get_current_user)):
    with repository.session() as s:
        row = s.get(ApiKey, key_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(404, "API key not found")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            s.add(row)
            s.commit()
    return {"ok": True}
