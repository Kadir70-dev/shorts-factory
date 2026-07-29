"""Additive SQLModel tables for authentication."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

ROLE_ADMIN = "admin"
ROLE_USER = "user"
VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_USER})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid4().hex


class User(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = ROLE_USER
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_login_at: Optional[datetime] = None


class RefreshToken(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(index=True)
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    user_agent: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ApiKey(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    key_hash: str = Field(index=True)
    name: str
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


AUTH_TABLES = (User, RefreshToken, ApiKey)
