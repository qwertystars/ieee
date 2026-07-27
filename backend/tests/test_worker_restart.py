"""Integration test — worker restart recovery.

Verifies that the ConsumerManager correctly classifies transient vs permanent
errors, that _build_observation maps payloads correctly, and that stop() is
safe to call when the consumer was never started (or failed to start). These
are the code paths exercised when a worker process restarts after a crash.

Kafka/Redpanda is NOT available in the test environment, so we test the
non-Kafka code paths directly. No mocking of the SUT — we call the real
methods on the real ConsumerManager class.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.exc import IntegrityError

from app.streaming.consumer import ConsumerManager

ORG_ID = "org_test_worker"
INCIDENT_ID = "inc_test_worker"


def test_should_retry_classifies_value_error_as_permanent() -> None:
    """ValueError (e.g. missing field) is permanent → not retried → DLQ."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._should_retry(ValueError("missing observation_id")) is False


def test_should_retry_classifies_key_error_as_permanent() -> None:
    """KeyError (missing dict key) is permanent → not retried."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._should_retry(KeyError("geometry")) is False


def test_should_retry_classifies_integrity_error_as_permanent() -> None:
    """IntegrityError (constraint violation) is permanent → not retried."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._should_retry(IntegrityError("stmt", {}, Exception())) is False


def test_should_retry_classifies_connection_error_as_transient() -> None:
    """ConnectionError (network issue) is transient → retried."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._should_retry(ConnectionError("refused")) is True


def test_should_retry_classifies_timeout_error_as_transient() -> None:
    """TimeoutError is transient → retried."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._should_retry(TimeoutError("timed out")) is True


def test_build_observation_maps_all_fields() -> None:
    """_build_observation correctly maps a payload dict to an Observation."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    payload = {
        "observation_id": "01J9TESTWORKER001",
        "event_type": "sensor_observation",
        "phenomenon": "water_level",
        "value": 2.3,
        "unit": "m",
        "geometry": {"type": "Point", "coordinates": [-73.9, 40.7]},
        "geometry_uncertainty": 3.0,
        "observed_at": 1721300000000,
        "valid_from": 1721300000000,
        "received_at": 1721300001000,
        "source_id": "src_worker_test",
        "source_type": "sensor",
        "collection_method": "gauge",
        "source_reliability": 0.85,
        "freshness": 0.95,
        "corroboration_state": "uncorroborated",
        "quality_flags": {"outlier": False},
        "access_policy": "internal",
        "provenance_chain": {"steps": ["ingest"]},
        "raw_data_hash": "sha256:abc",
        "org_id": ORG_ID,
        "incident_id": INCIDENT_ID,
    }

    obs = cm._build_observation(payload)

    assert obs.observation_id == payload["observation_id"]
    assert obs.event_type == "sensor_observation"
    assert obs.phenomenon == "water_level"
    assert obs.value == 2.3
    assert obs.unit == "m"
    assert obs.observed_at == 1721300000000
    assert obs.source_id == "src_worker_test"
    assert obs.org_id == ORG_ID
    assert obs.incident_id == INCIDENT_ID
    assert obs.raw_data_hash == "sha256:abc"


def test_stop_is_safe_when_not_started() -> None:
    """Calling stop() before start() must not raise (worker restart scenario)."""
    import asyncio

    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    # stop() is async — run it in a fresh event loop.
    asyncio.run(cm.stop())
    # Consumer and producer should both be None.
    assert cm._consumer is None
    assert cm._dlq_producer is None


def test_consume_without_start_raises_runtime_error() -> None:
    """consume() before start() raises RuntimeError (not a silent no-op)."""
    import asyncio

    cm = ConsumerManager(bootstrap_servers="localhost:9092")

    async def _try_consume() -> None:
        await cm.consume()

    with pytest.raises(RuntimeError, match="not started"):
        asyncio.run(_try_consume())


def test_send_to_dlq_safe_when_producer_none() -> None:
    """_send_to_dlq is a safe no-op when the DLQ producer was never started."""
    import asyncio

    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    # _dlq_producer is None — _send_to_dlq should return without error.
    asyncio.run(cm._send_to_dlq({"bad": "payload"}, "test error"))
