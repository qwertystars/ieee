"""Integration test — dead-letter queue (DLQ) routing.

Verifies that the ConsumerManager correctly classifies errors as permanent
(sending to DLQ) vs transient (retrying). The DLQ topic name is
`observations.dlq`. When the DLQ producer is unavailable (Kafka down),
_send_to_dlq is a safe no-op.

No mocking of the SUT — we call the real ConsumerManager methods. Kafka is
not available in the test environment, which is the real "DLQ producer down"
scenario.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

import app.streaming.consumer as consumer_module
from app.streaming.consumer import DLQ_TOPIC, ConsumerManager


def test_dlq_topic_name() -> None:
    """The DLQ topic is named 'observations.dlq'."""
    assert DLQ_TOPIC == "observations.dlq"


def test_permanent_errors_not_retried() -> None:
    """Permanent errors (ValueError, KeyError, IntegrityError) → _should_retry False.

    These are the error types that route to the DLQ instead of retrying.
    """
    cm = ConsumerManager(bootstrap_servers="localhost:9092")

    permanent_errors = [
        ValueError("missing field"),
        KeyError("observation_id"),
        TypeError("wrong type"),
        AttributeError("no attribute"),
        IntegrityError("stmt", {}, Exception()),
    ]

    for err in permanent_errors:
        assert cm._should_retry(err) is False, (
            f"{type(err).__name__} should be permanent (not retried)"
        )


def test_transient_errors_retried() -> None:
    """Transient errors (ConnectionError, TimeoutError, OSError) → _should_retry True."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")

    transient_errors = [
        ConnectionError("refused"),
        TimeoutError("timed out"),
        OSError("network unreachable"),
        RuntimeError("unexpected state"),
    ]

    for err in transient_errors:
        assert cm._should_retry(err) is True, (
            f"{type(err).__name__} should be transient (retried)"
        )


def test_send_to_dlq_no_producer_is_noop() -> None:
    """When the DLQ producer is None (Kafka down), _send_to_dlq is a no-op."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    assert cm._dlq_producer is None

    # Should not raise.
    assert asyncio.run(cm._send_to_dlq({"observation_id": "bad"}, "test error")) is False


def test_dlq_producer_serializes_string_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeConsumer:
        def __init__(self, *topics: str, **kwargs: object) -> None:
            del topics, kwargs

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    class FakeProducer:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

    monkeypatch.setattr(consumer_module, "AIOKafkaConsumer", FakeConsumer)
    monkeypatch.setattr(consumer_module, "AIOKafkaProducer", FakeProducer)
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    asyncio.run(cm.start(["observations.normalized"]))
    assert callable(captured["key_serializer"])
    assert captured["key_serializer"]("external-id") == b"external-id"
    asyncio.run(cm.stop())


def test_retry_with_backoff_raises_on_permanent() -> None:
    """_retry_with_backoff raises immediately for permanent errors (no retry)."""
    cm = ConsumerManager(bootstrap_servers="localhost:9092")

    with pytest.raises(ValueError, match="missing"):
        asyncio.run(cm._retry_with_backoff({"observation_id": ""}))


def test_process_missing_observation_id_raises_value_error() -> None:
    """_process raises ValueError for a payload missing observation_id.

    This is the poison-message scenario: a malformed payload that cannot be
    processed. The consumer loop catches this and sends it to the DLQ.
    """
    cm = ConsumerManager(bootstrap_servers="localhost:9092")

    with pytest.raises(ValueError, match="missing observation_id"):
        asyncio.run(cm._process({"phenomenon": "water_level"}))


def test_process_valid_payload_does_not_raise_value_error() -> None:
    """_process with a valid payload does not raise ValueError.

    It may raise other errors (e.g. DB constraint), but not the 'missing
    observation_id' ValueError that triggers DLQ routing.
    """
    cm = ConsumerManager(bootstrap_servers="localhost:9092")

    payload = {
        "observation_id": "01J9TESTDLQ0001",
        "event_type": "sensor_observation",
        "phenomenon": "water_level",
        "geometry": {"type": "Point", "coordinates": [-73.9, 40.7]},
        "observed_at": 1721300000000,
        "source_id": "src_dlq_test",
        "source_type": "sensor",
        "org_id": "org_test_dlq",
        "incident_id": "inc_test_dlq",
    }

    # This may succeed or fail with a DB error, but must NOT raise ValueError.
    try:
        asyncio.run(cm._process(payload))
    except ValueError as exc:
        pytest.fail(f"valid payload raised ValueError: {exc}")
    except Exception:
        pass  # DB errors are acceptable — we're testing DLQ classification
