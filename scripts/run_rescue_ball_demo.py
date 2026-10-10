#!/usr/bin/env python3
"""Rescue-ball simulation demo CLI.

Runs the ``SimulationEngine`` for a configurable duration and prints observation
IDs. Running twice with the same seed produces identical observation IDs (the
engine's RNG is seeded deterministically and ULIDs are generated from the RNG,
not wall-clock randomness).

Usage:
    python -m scripts.run_rescue_ball_demo --seed 42
    python scripts/run_rescue_ball_demo.py --seed 42 --duration 5

Environment:
    PYTHONPATH must include the backend directory, or run from repo root
    (the script auto-adds ``backend`` to ``sys.path``).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Allow running from repo root or backend dir.
_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
if os.path.isdir(_BACKEND):
    sys.path.insert(0, os.path.abspath(_BACKEND))

from app.simulator.engine import SimulationEngine  # noqa: E402

_ORG_ID = "demo-org"
_INCIDENT_ID = "demo-incident-rivertown-flood"
_DEVICE_COUNT = 2


async def _run(seed: int, duration: float) -> int:
    """Run the simulation for ``duration`` seconds. Returns 0 on success."""
    engine = SimulationEngine(seed=seed)
    device_ids = engine.start(_ORG_ID, _INCIDENT_ID, _DEVICE_COUNT)
    print(f"Started simulation (seed={seed}) with devices: {device_ids}")
    print(f"Running for {duration:.1f}s...")

    await asyncio.sleep(duration)

    obs_ids = engine.observation_ids
    sim_status = engine.status()
    print(f"\nSimulation state: {sim_status['state']}")
    print(f"Sim time: {sim_status['sim_time_ms']}ms")
    print(f"Observations published: {len(obs_ids)}")
    print("Observation IDs:")
    for oid in obs_ids:
        print(f"  {oid}")

    await engine.stop()
    print("\nSimulation stopped.")
    return 0


def main() -> int:
    """Parse args and run the simulation demo."""
    parser = argparse.ArgumentParser(
        description="Rescue-ball simulation demo CLI.",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed (default: 42)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=3.0,
        help="Simulation duration in seconds (default: 3.0)",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.seed, args.duration))


if __name__ == "__main__":
    sys.exit(main())
