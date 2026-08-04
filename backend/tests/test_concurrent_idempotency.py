"""Integration test — concurrent idempotency key handling.

Verifies that when two threads call check_and_record() concurrently with
the same (source, external_id) pair, exactly one succeeds (returns True)
and exactly one row is inserted. The unique constraint on
(source, external_id) enforces this at the DB level.

Uses the real PostgreSQL database via SessionLocal. No mocking.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete, text

from app.db import SessionLocal
from app.lib.idempotency import IdempotencyKey, check_and_record

SOURCE = "test_concurrent_source"
EXTERNAL_ID = "ext_concurrent_001"


@pytest.fixture
def db():
    """Yield a session and clean up test rows before and after."""
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


def test_concurrent_same_key_only_one_succeeds(db) -> None:
    """Two threads, same (source, external_id) → exactly one True, one False."""
    results: list[bool] = []
    lock = threading.Lock()

    def _worker() -> None:
        session = SessionLocal()
        try:
            ok = check_and_record(session, SOURCE, EXTERNAL_ID)
        finally:
            session.close()
        with lock:
            results.append(ok)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_worker) for _ in range(2)]
        for f in futures:
            f.result(timeout=10)

    assert len(results) == 2
    assert results.count(True) == 1, (
        f"expected exactly 1 True, got {results}"
    )
    assert results.count(False) == 1, (
        f"expected exactly 1 False, got {results}"
    )

    # Verify only one row in the DB.
    count = db.execute(
        text(
            "SELECT count(*) FROM idempotency_keys "
            "WHERE source = :s AND external_id = :e"
        ),
        {"s": SOURCE, "e": EXTERNAL_ID},
    ).scalar()
    assert count == 1, f"expected 1 row, got {count}"


def test_sequential_same_key_second_fails(db) -> None:
    """Sequential calls: first True, second False (baseline for concurrent test)."""
    first = check_and_record(db, SOURCE, EXTERNAL_ID)
    second = check_and_record(db, SOURCE, EXTERNAL_ID)
    assert first is True
    assert second is False


def test_concurrent_different_keys_all_succeed(db) -> None:
    """Two threads, different external_ids → both True, two rows."""
    results: list[bool] = []
    lock = threading.Lock()
    ext_ids = ["ext_concurrent_a", "ext_concurrent_b"]

    def _worker(ext_id: str) -> None:
        session = SessionLocal()
        try:
            ok = check_and_record(session, SOURCE, ext_id)
        finally:
            session.close()
        with lock:
            results.append(ok)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_worker, eid) for eid in ext_ids]
        for f in futures:
            f.result(timeout=10)

    assert all(results), f"expected all True, got {results}"

    # Cleanup the extra rows.
    db.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.source == SOURCE,
            IdempotencyKey.external_id.in_(ext_ids),
        )
    )
    db.commit()


def test_concurrent_four_workers_one_winner(db) -> None:
    """Four concurrent workers, same key → exactly one True."""
    results: list[bool] = []
    lock = threading.Lock()

    def _worker() -> None:
        session = SessionLocal()
        try:
            ok = check_and_record(session, SOURCE, EXTERNAL_ID)
        finally:
            session.close()
        with lock:
            results.append(ok)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_worker) for _ in range(4)]
        for f in futures:
            f.result(timeout=10)

    assert results.count(True) == 1, (
        f"expected exactly 1 True among 4, got {results}"
    )
    assert len(results) == 4


def test_same_external_id_is_independent_per_tenant(db) -> None:
    first = check_and_record(
        db, SOURCE, EXTERNAL_ID, org_id="org_concurrent_a", payload={"value": 1}
    )
    second = check_and_record(
        db, SOURCE, EXTERNAL_ID, org_id="org_concurrent_b", payload={"value": 1}
    )
    assert first is True
    assert second is True
    db.execute(
        delete(IdempotencyKey).where(
            IdempotencyKey.org_id.in_(["org_concurrent_a", "org_concurrent_b"]),
            IdempotencyKey.source == SOURCE,
            IdempotencyKey.external_id == EXTERNAL_ID,
        )
    )
    db.commit()
