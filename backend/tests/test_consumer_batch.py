"""Tests for the consumer's batch commit logic (T25).

Verifies:
  1. Consumer buffers 10 observations before committing (batch_size default).
  2. No data loss — all observations eventually reach the DB after flush.
  3. Timer-based flush commits a non-full buffer.
  4. Graceful shutdown flushes the remaining buffer.
  5. Duplicate observation_ids are skipped during flush.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.lib.ulid import generate_ulid
from app.models.observation import Observation
from app.streaming.consumer import ConsumerManager

ORG_ID = "org_test_batch"
INCIDENT_ID = "inc_test_batch"


def _payload(idx: int) -> dict:
    """Build a valid normalized observation payload for testing."""
    return {
        "observation_id": generate_ulid(),
        "event_type": "sensor_observation",
        "phenomenon": "water_level",
        "value": float(idx) * 0.1,
        "unit": "m",
        "geometry": {"type": "Point", "coordinates": [-73.9, 40.7]},
        "geometry_uncertainty": 0.0,
        "observed_at": 1756000000000 + idx,
        "valid_from": 1756000000000 + idx,
        "received_at": 1756000000000 + idx,
        "source_id": f"sensor_batch_{idx}",
        "source_type": "sensor",
        "collection_method": "gauge",
        "source_reliability": 0.85,
        "freshness": 1.0,
        "corroboration_state": "uncorroborated",
        "quality_flags": {},
        "access_policy": "internal",
        "provenance_chain": {},
        "raw_data_hash": f"sha256:batch_{idx}",
        "org_id": ORG_ID,
        "incident_id": INCIDENT_ID,
    }


@pytest.fixture
def _clear_batch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure default batch size (10) and flush interval for tests."""
    monkeypatch.delenv("CONSUMER_BATCH_SIZE", raising=False)
    monkeypatch.delenv("CONSUMER_FLUSH_INTERVAL_S", raising=False)


def test_consumer_buffers_until_batch_size(_clear_batch_env: None) -> None:
    """Given 9 payloads, _process buffers without committing; 10th triggers flush."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._batch_size == 10

    async def _run() -> None:
        for i in range(9):
            await cm._process(_payload(i))
        assert len(cm._buffer) == 9

        await cm._process(_payload(9))
        assert len(cm._buffer) == 0

    asyncio.run(_run())


def test_no_data_loss_all_observations_in_db(_clear_batch_env: None) -> None:
    """After flush, all 10 buffered observations are in the DB."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    payloads = [_payload(i) for i in range(10)]
    expected_ids = {p["observation_id"] for p in payloads}

    async def _run() -> None:
        for p in payloads:
            await cm._process(p)
    asyncio.run(_run())

    assert len(cm._buffer) == 0

    db = SessionLocal()
    try:
        rows = db.execute(
            select(Observation.observation_id).where(
                Observation.incident_id == INCIDENT_ID,
                Observation.observation_id.in_(expected_ids),
            )
        ).scalars().all()
        assert set(rows) == expected_ids
    finally:
        db.close()


def test_flush_batch_commits_partial_buffer(_clear_batch_env: None) -> None:
    """flush_batch commits a non-full buffer (e.g. 3 observations)."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    payloads = [_payload(i) for i in range(3)]
    expected_ids = {p["observation_id"] for p in payloads}

    async def _run() -> None:
        for p in payloads:
            await cm._process(p)
        assert len(cm._buffer) == 3
        await cm._flush_batch()
        assert len(cm._buffer) == 0

    asyncio.run(_run())

    db = SessionLocal()
    try:
        rows = db.execute(
            select(Observation.observation_id).where(
                Observation.incident_id == INCIDENT_ID,
                Observation.observation_id.in_(expected_ids),
            )
        ).scalars().all()
        assert set(rows) == expected_ids
    finally:
        db.close()


def test_graceful_shutdown_flushes_remaining_buffer(_clear_batch_env: None) -> None:
    """stop() flushes the remaining buffer before shutting down."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    payloads = [_payload(i) for i in range(5)]
    expected_ids = {p["observation_id"] for p in payloads}

    async def _run() -> None:
        for p in payloads:
            await cm._process(p)
        assert len(cm._buffer) == 5
        await cm.stop()
        assert len(cm._buffer) == 0

    asyncio.run(_run())

    db = SessionLocal()
    try:
        rows = db.execute(
            select(Observation.observation_id).where(
                Observation.incident_id == INCIDENT_ID,
                Observation.observation_id.in_(expected_ids),
            )
        ).scalars().all()
        assert set(rows) == expected_ids
    finally:
        db.close()


def test_duplicate_observation_ids_skipped(_clear_batch_env: None) -> None:
    """Duplicate observation_ids in the same batch are skipped by idempotency."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    dup_id = generate_ulid()
    p1 = _payload(0)
    p1["observation_id"] = dup_id
    p2 = _payload(1)
    p2["observation_id"] = dup_id
    p3 = _payload(2)

    async def _run() -> None:
        await cm._process(p1)
        await cm._process(p2)
        await cm._process(p3)
        await cm._flush_batch()

    asyncio.run(_run())

    db = SessionLocal()
    try:
        rows = db.execute(
            select(Observation.observation_id).where(
                Observation.observation_id == dup_id
            )
        ).scalars().all()
        assert len(rows) == 1
    finally:
        db.close()


def test_batch_size_configurable_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CONSUMER_BATCH_SIZE env var overrides the default batch size."""
    monkeypatch.setenv("CONSUMER_BATCH_SIZE", "3")
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._batch_size == 3


def test_flush_interval_configurable_via_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CONSUMER_FLUSH_INTERVAL_S env var overrides the default interval."""
    monkeypatch.setenv("CONSUMER_FLUSH_INTERVAL_S", "2.5")
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._flush_interval_s == 2.5
