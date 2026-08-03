"""Password hashing, signed access tokens, and opaque secret generation."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from ..config import DATA_DIR, settings

_password_hasher = PasswordHasher()
_secret_key: str | None = None


class AccessTokenError(ValueError):
    """JWT validation failed."""


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def initialize_signing_secret() -> str:
    """Load or atomically create the persistent JWT secret.

    The ``0600`` permission is POSIX-only and has no effect on Windows.
    """
    global _secret_key
    configured = settings().auth_secret_key.strip()
    if configured:
        _secret_key = configured
        return configured

    path = Path(DATA_DIR) / "auth_secret.key"
    temporary_path = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if not value:
                raise RuntimeError(
                    f"signing secret file is empty at {path}; delete it to "
                    "regenerate the secret; this invalidates existing access tokens"
                )
        else:
            value = secrets.token_urlsafe(48)
            fd = os.open(
                temporary_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        if os.name == "posix":
            os.chmod(path, 0o600)
        _secret_key = value
        return value
    except RuntimeError:
        raise
    except OSError as exc:
        if settings().auth_required:
            raise RuntimeError(
                f"authentication is required but the signing secret could not "
                f"be persisted at {path}: {exc}"
            ) from exc
        _secret_key = secrets.token_urlsafe(48)
        return _secret_key


def _signing_secret() -> str:
    return _secret_key or initialize_signing_secret()


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": now + timedelta(minutes=settings().auth_access_token_minutes),
        "iat": now,
        "jti": uuid4().hex,
        "typ": "access",
    }
    return jwt.encode(payload, _signing_secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(token, _signing_secret(), algorithms=["HS256"])
        if claims.get("typ") != "access" or not claims.get("sub"):
            raise AccessTokenError("invalid access token")
        return claims
    except jwt.PyJWTError as exc:
        raise AccessTokenError("invalid or expired access token") from exc


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, secret_hash(raw)


def new_api_key() -> tuple[str, str]:
    raw = f"sf_{secrets.token_urlsafe(32)}"
    return raw, secret_hash(raw)
