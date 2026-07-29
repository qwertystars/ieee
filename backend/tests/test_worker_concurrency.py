"""Tests for configurable worker concurrency (WORKER_CONCURRENCY).

Verifies:
- WORKER_CONCURRENCY defaults to 1 (backward compatible)
- WORKER_CONCURRENCY=N creates N ConsumerManager instances
- Each consumer gets a different partition assignment (Kafka consumer group)
"""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings, settings


def test_worker_concurrency_defaults_to_1() -> None:
    """Default WORKER_CONCURRENCY is 1 — backward compatible."""
    s = Settings()
    assert s.WORKER_CONCURRENCY == 1


def test_worker_concurrency_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """WORKER_CONCURRENCY=3 sets the value to 3."""
    monkeypatch.setenv("WORKER_CONCURRENCY", "3")
    s = Settings()
    assert s.WORKER_CONCURRENCY == 3


def _run_worker_with_mocks() -> int:
    """Run run_worker with mocked consumers; return ConsumerManager call count."""
    from app.worker.main import run_worker

    with patch("app.worker.main.ConsumerManager") as MockCM:
        instance = MockCM.return_value
        instance.start = AsyncMock()
        instance.consume = AsyncMock()
        instance.stop = AsyncMock()
        asyncio.run(run_worker())
        return MockCM.call_count


def test_run_worker_creates_1_consumer_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WORKER_CONCURRENCY=1 (default) creates exactly 1 ConsumerManager."""
    monkeypatch.setattr(settings, "WORKER_CONCURRENCY", 1)
    assert _run_worker_with_mocks() == 1


def test_run_worker_creates_3_consumers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WORKER_CONCURRENCY=3 creates exactly 3 ConsumerManager instances."""
    monkeypatch.setattr(settings, "WORKER_CONCURRENCY", 3)
    assert _run_worker_with_mocks() == 3


_KAFKA_EXTERNAL = "localhost:19092"


def _kafka_reachable(timeout: float = 2.0) -> bool:
    """Check if Kafka/Redpanda external listener is reachable.

    The external listener (port 19092) advertises ``localhost:19092``
    which resolves from the host. The internal listener (port 9092)
    advertises ``redpanda:9092`` which only resolves inside Docker.
    """
    host, _, port_str = _KAFKA_EXTERNAL.partition(":")
    try:
        with socket.create_connection((host, int(port_str)), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.mark.skipif(
    not _kafka_reachable(),
    reason="Kafka/Redpanda external listener not reachable",
)
def test_multiple_consumers_get_different_partitions() -> None:
    """3 consumers in the same group get disjoint partition assignments.

    Kafka's consumer group protocol guarantees that partitions are
    distributed among consumers in the same group. With 6 partitions
    and 3 consumers, each should get ~2 partitions with no overlap.
    """
    from app.streaming.consumer import ConsumerManager

    consumers = [
        ConsumerManager(bootstrap_servers=_KAFKA_EXTERNAL, group_id="test-worker-concurrency") for _ in range(3)
    ]

    async def _run() -> None:
        try:
            for cm in consumers:
                await cm.start(["observations.normalized"])

            loop = asyncio.get_running_loop()
            deadline = loop.time() + 15.0
            while loop.time() < deadline:
                assigned = [
                    cm._consumer.assignment() if cm._consumer else set()
                    for cm in consumers
                ]
                if all(len(a) > 0 for a in assigned):
                    break
                await asyncio.sleep(0.5)

            assignments = [
                cm._consumer.assignment() if cm._consumer else set()
                for cm in consumers
            ]

            for i, assigned in enumerate(assignments):
                assert len(assigned) > 0, (
                    f"Consumer {i} got no partition assignment"
                )

            all_partitions: set = set()
            for assigned in assignments:
                for tp in assigned:
                    assert tp not in all_partitions, (
                        f"Partition {tp} assigned to multiple consumers"
                    )
                    all_partitions.add(tp)
        finally:
            for cm in consumers:
                await cm.stop()

    asyncio.run(_run())
