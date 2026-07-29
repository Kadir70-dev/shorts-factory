"""Create the first administrator without exposing credentials in shell output."""
from __future__ import annotations

import argparse

from sqlmodel import select

from .models import ROLE_ADMIN, User
from .repository import init_auth_db, session
from .security import hash_password


def bootstrap_admin(email: str, password: str, force: bool = False) -> User:
    init_auth_db()
    with session() as s:
        existing_admin = s.exec(
            select(User).where(User.role == ROLE_ADMIN)
        ).first()
        if existing_admin is not None and not force:
            raise RuntimeError("an admin already exists; use --force to override")

        normalized = email.strip().lower()
        existing_user = s.exec(select(User).where(User.email == normalized)).first()
        if existing_user is not None:
            if not force:
                raise RuntimeError("that email already exists")
            existing_user.password_hash = hash_password(password)
            existing_user.role = ROLE_ADMIN
            existing_user.is_active = True
            s.add(existing_user)
            s.commit()
            s.refresh(existing_user)
            return existing_user

        user = User(
            email=normalized,
            password_hash=hash_password(password),
            role=ROLE_ADMIN,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the first Shorts Factory admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        user = bootstrap_admin(args.email, args.password, args.force)
    except RuntimeError as exc:
        parser.error(str(exc))
    print(f"admin ready: {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
