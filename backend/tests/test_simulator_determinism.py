"""Integration test — simulator determinism.

Verifies that the SimulationEngine produces identical observation ID sequences
when started with the same seed. All randomness is sourced from the seedable
random.Random, so the same seed reproduces the same trajectory.

Kafka is NOT available in the test environment, so observations are not
published — but the observation_ids list is still tracked deterministically.
No mocking of the SUT.
"""

from __future__ import annotations

import asyncio

import pytest

from app.simulator.engine import SimulationEngine

ORG_ID = "org_test_sim"
INCIDENT_ID = "inc_test_sim"


async def _run_engine(seed: int, ticks: int) -> list[str]:
    """Start an engine with the given seed, run for N ticks, return obs IDs."""
    engine = SimulationEngine(seed=seed)
    engine.start(ORG_ID, INCIDENT_ID, device_count=2)
    await asyncio.sleep(ticks + 0.5)
    await engine.stop()
    return engine.observation_ids


async def test_same_seed_produces_same_observation_ids() -> None:
    """Two engines with seed=42 produce identical observation ID sequences."""
    ids_a = await _run_engine(seed=42, ticks=2)
    ids_b = await _run_engine(seed=42, ticks=2)

    assert len(ids_a) > 0, "engine produced no observation IDs"
    assert len(ids_a) == len(ids_b), (
        f"length mismatch: {len(ids_a)} vs {len(ids_b)}"
    )
    assert ids_a == ids_b, (
        f"observation IDs differ:\n  a={ids_a[:5]}\n  b={ids_b[:5]}"
    )


async def test_different_seeds_produce_different_observation_ids() -> None:
    """Engines with different seeds produce different observation ID sequences."""
    ids_a = await _run_engine(seed=42, ticks=2)
    ids_b = await _run_engine(seed=99, ticks=2)

    assert len(ids_a) > 0
    assert len(ids_b) > 0
    assert ids_a != ids_b, (
        "different seeds produced identical observation ID sequences"
    )


def test_status_reflects_seed() -> None:
    """Engine status reports the configured seed."""
    engine = SimulationEngine(seed=123)
    status = engine.status()
    assert status["seed"] == 123
    assert status["state"] == "stopped"
    assert status["device_count"] == 0


async def test_start_returns_device_ids() -> None:
    """start() returns a list of device IDs matching device_count."""
    engine = SimulationEngine(seed=42)
    device_ids = engine.start(ORG_ID, INCIDENT_ID, device_count=3)

    assert len(device_ids) == 3
    assert all(d.startswith("rescue-ball-") for d in device_ids)

    await engine.stop()


async def test_replay_restarts_with_new_seed() -> None:
    """replay() stops the engine and restarts with a new seed."""
    engine = SimulationEngine(seed=42)
    engine.start(ORG_ID, INCIDENT_ID, device_count=2)

    new_ids = await engine.replay(seed=99)
    assert len(new_ids) == 2
    assert engine.status()["seed"] == 99

    await engine.stop()
