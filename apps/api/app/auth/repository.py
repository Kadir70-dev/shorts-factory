"""Persistence helpers for auth tables, kept additive to the existing database."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlmodel import SQLModel, Session, select

from .. import db
from .models import AUTH_TABLES, ApiKey, RefreshToken, User


def init_auth_db() -> None:
    """Create only auth tables; never inspect or alter existing tables."""
    SQLModel.metadata.create_all(
        db._engine, tables=[table.__table__ for table in AUTH_TABLES]
    )
    # M2.1 removes privilege separation. Normalize any accounts created by the
    # former two-role model without changing the table shape.
    with session() as s:
        s.execute(update(User).where(User.role != "admin").values(role="admin"))
        s.commit()


def session() -> Session:
    # Keep loaded values available for detached-instance reads after commit.
    return Session(db._engine, expire_on_commit=False)


def get_user(user_id: str) -> User | None:
    with session() as s:
        return s.get(User, user_id)


def get_user_by_email(email: str) -> User | None:
    with session() as s:
        return s.exec(select(User).where(User.email == email.lower())).first()


def get_refresh_by_hash(token_hash: str) -> RefreshToken | None:
    with session() as s:
        return s.exec(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).first()


def get_api_key_by_hash(key_hash: str) -> ApiKey | None:
    with session() as s:
        return s.exec(select(ApiKey).where(ApiKey.key_hash == key_hash)).first()


def revoke_refresh(token_hash: str, when: datetime) -> bool:
    with session() as s:
        result = s.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=when)
        )
        s.commit()
        return result.rowcount == 1
