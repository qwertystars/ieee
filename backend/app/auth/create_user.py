"""Create or reset a user account from the command line.

Production deployments never seed demo users, so the first admin must be
provisioned out-of-band:

    docker compose -f docker-compose.prod.yml run --rm backend \
        python -m app.auth.create_user --email ops@example.org --role admin --org-id org_main

The password is read from the RESQNET_USER_PASSWORD environment variable when
set, otherwise prompted for interactively (never passed as an argument, so it
does not land in shell history or the process table).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.auth.abac import ACTION_MIN_ROLES
from app.auth.passwords import hash_password
from app.lib.ulid import generate_ulid
from app.models.user import User

VALID_ROLES = tuple(sorted(ACTION_MIN_ROLES["read"]))
MIN_PASSWORD_LENGTH = 12
PASSWORD_ENV = "RESQNET_USER_PASSWORD"


def upsert_user(db: Session, *, email: str, role: str, org_id: str, password: str) -> bool:
    """Create the user, or reset role/org/password if it exists. Returns True if created."""
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {', '.join(VALID_ROLES)}")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    user = db.query(User).filter(User.email == email).first()
    created = user is None
    if user is None:
        user = User(id=generate_ulid(), email=email, created_at=int(time.time() * 1000))
        db.add(user)
    user.role = role
    user.org_id = org_id
    user.hashed_password = hash_password(password)
    db.commit()
    return created


def _read_password() -> str:
    from_env = os.environ.get(PASSWORD_ENV)
    if from_env:
        return from_env
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise ValueError("passwords do not match")
    return first


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=VALID_ROLES)
    parser.add_argument("--org-id", required=True, help="tenant id, e.g. org_main")
    args = parser.parse_args(argv)

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        created = upsert_user(
            db,
            email=args.email.strip(),
            role=args.role,
            org_id=args.org_id,
            password=_read_password(),
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()
    print(f"{'created' if created else 'updated'} {args.role} {args.email} in {args.org_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
