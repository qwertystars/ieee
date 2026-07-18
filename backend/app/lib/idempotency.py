"""Idempotency — dedup by (source, external_id) unique constraint.

Provides `check_and_record(db, source, external_id)` for HTTP/queue/webhook
handlers. The first call with a given (source, external_id) pair inserts a row
and returns True; subsequent calls return False without inserting.

The `idempotency_keys` table is created on demand via `ensure_table(engine)`
since it is not part of the Alembic migration.
"""

from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.lib.time import now_ms


class IdempotencyKey(Base):
    """A processed (source, external_id) pair. Uniqueness enforces dedup."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "source", "external_id", name="uq_idempotency_source_external"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    created_at = Column(BigInteger, nullable=False, default=now_ms)


def ensure_table(engine=None) -> None:
    """Create the idempotency_keys table if it does not exist.

    Pass an engine to target a specific database; defaults to the app engine.
    """
    if engine is None:
        from app.db import engine as _engine

        engine = _engine
    IdempotencyKey.__table__.create(bind=engine, checkfirst=True)


def check_and_record(db: Session, source: str, external_id: str) -> bool:
    """Try to record (source, external_id).

    Returns True if this is the first time the pair is seen (row inserted).
    Returns False if the pair was already recorded (unique constraint hit).
    """
    row = IdempotencyKey(source=source, external_id=external_id, created_at=now_ms())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


__all__ = ["IdempotencyKey", "ensure_table", "check_and_record"]
