"""Tests for idempotency dedup via (source, external_id) unique constraint.

Uses the real PostgreSQL database via SessionLocal. The idempotency_keys table
is created on demand via ensure_table() since it is not in the Alembic
migration. All test rows are cleaned up after each test.
"""

import pytest
from sqlalchemy import delete, text

from app.db import SessionLocal, engine
from app.lib.idempotency import IdempotencyKey, check_and_record, ensure_table

SOURCE = "test_source"
EXTERNAL_ID = "ext_test_001"


@pytest.fixture(scope="module", autouse=True)
def _table():
    """Create the idempotency_keys table once for the test module."""
    ensure_table(engine)
    yield


@pytest.fixture
def db():
    """Yield a session and clean up test rows after each test."""
    session = SessionLocal()
    session.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.source == SOURCE,
            IdempotencyKey.external_id == EXTERNAL_ID,
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.source == SOURCE,
                IdempotencyKey.external_id == EXTERNAL_ID,
            )
        )
        session.commit()
        session.close()


def test_first_insert_returns_true(db):
    """The first call with a fresh (source, external_id) returns True."""
    result = check_and_record(db, SOURCE, EXTERNAL_ID)
    assert result is True

    # Row exists in the table.
    count = db.execute(
        text(
            "SELECT count(*) FROM idempotency_keys "
            "WHERE source = :s AND external_id = :e"
        ),
        {"s": SOURCE, "e": EXTERNAL_ID},
    ).scalar()
    assert count == 1


def test_duplicate_insert_returns_false(db):
    """Inserting the same (source, external_id) twice → second is a no-op."""
    first = check_and_record(db, SOURCE, EXTERNAL_ID)
    second = check_and_record(db, SOURCE, EXTERNAL_ID)

    assert first is True
    assert second is False

    # Still only one row.
    count = db.execute(
        text(
            "SELECT count(*) FROM idempotency_keys "
            "WHERE source = :s AND external_id = :e"
        ),
        {"s": SOURCE, "e": EXTERNAL_ID},
    ).scalar()
    assert count == 1


def test_different_external_ids_both_succeed(db):
    """Different external_id values are independent and both return True."""
    a = check_and_record(db, SOURCE, EXTERNAL_ID)
    b = check_and_record(db, SOURCE, "ext_test_002")
    assert a is True
    assert b is True

    # Clean up the second row.
    db.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.source == SOURCE,
            IdempotencyKey.external_id == "ext_test_002",
        )
    )
    db.commit()


def test_different_sources_same_external_id_both_succeed(db):
    """Same external_id under different sources are independent."""
    a = check_and_record(db, SOURCE, EXTERNAL_ID)
    b = check_and_record(db, "other_source", EXTERNAL_ID)
    assert a is True
    assert b is True

    # Clean up the second row.
    db.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.source == "other_source",
            IdempotencyKey.external_id == EXTERNAL_ID,
        )
    )
    db.commit()
