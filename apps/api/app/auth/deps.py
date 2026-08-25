"""FastAPI dependencies for access-token and API-key authentication."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import settings
from . import repository
from .models import User
from .security import AccessTokenError, decode_access_token, secret_hash

bearer = HTTPBearer(auto_error=False)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "authentication required")
    token = credentials.credentials
    if token.startswith("sf_"):
        key = repository.get_api_key_by_hash(secret_hash(token))
        now = datetime.now(timezone.utc)
        if (
            key is None
            or key.revoked_at is not None
            or (key.expires_at is not None and _aware(key.expires_at) <= now)
        ):
            raise HTTPException(401, "invalid credentials")
        user = repository.get_user(key.user_id)
        if user is None or not user.is_active:
            raise HTTPException(401, "invalid credentials")
        with repository.session() as s:
            stored = s.get(type(key), key.id)
            if stored:
                stored.last_used_at = now
                s.add(stored)
                s.commit()
        return user
    try:
        claims = decode_access_token(token)
    except AccessTokenError as exc:
        raise HTTPException(401, "invalid credentials") from exc
    user = repository.get_user(str(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(401, "invalid credentials")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require authentication under the single-trust-boundary model.

    Every authenticated principal is an operator; this named alias preserves
    the security intent at user-management call sites.
    """
    return user


def optional_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User | None:
    if not settings().auth_required:
        return None
    return get_current_user(credentials)
