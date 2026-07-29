"""Authentication and user-management HTTP endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..auth import repository
from ..auth.deps import get_current_user, require_admin
from ..auth.models import ApiKey, RefreshToken, User, VALID_ROLES
from ..auth.security import (
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
    role: str = "user"


class UserPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None


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
        raise HTTPException(422, "role must be 'admin' or 'user'")
    email = data.email.strip().lower()
    if not email or not data.password:
        raise HTTPException(422, "email and password are required")
    user = User(email=email, password_hash=hash_password(data.password), role=data.role)
    try:
        with repository.session() as s:
            s.add(user)
            s.commit()
            s.refresh(user)
    except IntegrityError as exc:
        raise HTTPException(409, "email already registered") from exc
    return user


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
    user = repository.get_user_by_email(data.email.strip().lower())
    if (
        user is None
        or not user.is_active
        or not verify_password(data.password, user.password_hash)
    ):
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
    old_hash = secret_hash(data.refresh_token)
    now = datetime.now(timezone.utc)
    with repository.session() as s:
        old = s.exec(
            select(RefreshToken).where(RefreshToken.token_hash == old_hash)
        ).first()
        if (
            old is None
            or old.revoked_at is not None
            or _aware(old.expires_at) <= now
        ):
            raise HTTPException(401, "invalid refresh token")
        user = s.get(User, old.user_id)
        if user is None or not user.is_active:
            raise HTTPException(401, "invalid refresh token")
        raw_refresh, replacement = _issue_refresh(
            user, request.headers.get("user-agent", "")
        )
        user_id, user_role = user.id, user.role
        old.revoked_at = now
        s.add(old)
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


@router.post("/register")
def register(data: UserCreate):
    if not settings().auth_registration_open:
        raise HTTPException(403, "registration is closed")
    # Public registration can never be used to self-assign administrator access.
    return _user_public(_create_user(data.model_copy(update={"role": "user"})))


@router.post("/users")
def create_user(data: UserCreate, _admin: User = Depends(require_admin)):
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
        raise HTTPException(422, "role must be 'admin' or 'user'")
    with repository.session() as s:
        user = s.get(User, user_id)
        if user is None:
            raise HTTPException(404, "user not found")
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
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
