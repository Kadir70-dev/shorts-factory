"""Create the first administrator without exposing credentials in shell output."""
from __future__ import annotations

import argparse
import getpass
import os
import sys

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
    parser.add_argument("--password")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read one password line from standard input",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
        if not password:
            parser.error("no password was provided on standard input")
    elif os.environ.get("SHORTS_FACTORY_ADMIN_PASSWORD") is not None:
        password = os.environ["SHORTS_FACTORY_ADMIN_PASSWORD"]
    elif args.password is not None:
        print(
            "WARNING: --password exposes the password in process arguments; "
            "use it only for non-interactive CI",
            file=sys.stderr,
        )
        password = args.password
    else:
        password = getpass.getpass("Admin password: ")
        confirmation = getpass.getpass("Confirm admin password: ")
        if password != confirmation:
            parser.error("passwords do not match")
    if not password:
        parser.error("password must not be empty")
    try:
        user = bootstrap_admin(args.email, password, args.force)
    except RuntimeError as exc:
        parser.error(str(exc))
    print(f"admin ready: {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
