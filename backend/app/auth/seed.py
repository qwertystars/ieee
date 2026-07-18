"""Seed demo users for development.

Creates 6 demo users with password 'demo1234':
  admin, emergency_manager, responder_coordinator,
  field_responder, shelter_manager, viewer
"""

import time

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.db import Base, engine
from app.lib.ulid import generate_ulid
from app.models.user import User

DEMO_ORG_ID = "org_demo"
DEMO_PASSWORD = "demo1234"

DEMO_USERS: list[dict] = [
    {
        "email": "admin@demo.disaster",
        "role": "admin",
    },
    {
        "email": "emergency_manager@demo.disaster",
        "role": "emergency_manager",
    },
    {
        "email": "responder_coordinator@demo.disaster",
        "role": "responder_coordinator",
    },
    {
        "email": "field_responder@demo.disaster",
        "role": "field_responder",
    },
    {
        "email": "shelter_manager@demo.disaster",
        "role": "shelter_manager",
    },
    {
        "email": "viewer@demo.disaster",
        "role": "viewer",
    },
]


def _ensure_users_table() -> None:
    """Create the users table if it doesn't exist (idempotent).

    The Alembic migration does not include the users table, so we create it
    here via Base.metadata.create_all scoped to just the users table.
    """
    inspector = inspect(engine)
    if not inspector.has_table("users"):
        Base.metadata.create_all(bind=engine, tables=[User.__table__])


def seed_demo_users(db: Session) -> int:
    """Seed demo users if they don't exist. Returns count of users created."""
    _ensure_users_table()
    now_ms = int(time.time() * 1000)
    created = 0
    for entry in DEMO_USERS:
        existing = db.query(User).filter(User.email == entry["email"]).first()
        if existing is not None:
            continue
        user = User(
            id=generate_ulid(),
            email=entry["email"],
            hashed_password=hash_password(DEMO_PASSWORD),
            role=entry["role"],
            org_id=DEMO_ORG_ID,
            created_at=now_ms,
        )
        db.add(user)
        created += 1
    db.commit()
    return created


__all__ = ["DEMO_ORG_ID", "DEMO_PASSWORD", "DEMO_USERS", "seed_demo_users"]
