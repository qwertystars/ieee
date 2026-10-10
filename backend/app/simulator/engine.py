"""Simulation engine — orchestrates rescue-ball devices and publishes observations.

The engine runs a deterministic simulation loop in a background asyncio task.
All randomness is sourced from a seedable ``random.Random``, so the same seed
reproduces the same trajectory and observation IDs. Observations are published
to the ``observations.raw`` Kafka topic via ``ProducerManager``, matching the
payload format expected by the streaming consumer (``consumer.py``). If Kafka
is unavailable, the engine logs a warning and continues (best-effort).

DIGITAL SIMULATION — physical rescue ball, mobility, communications, thermal
accuracy, and landing mechanism have NOT been validated.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable

from app.config import settings
from app.lib.ulid import generate_ulid
from app.simulator.engine_types import deterministic_ulid as _deterministic_ulid
from app.simulator.local_transport import build_simulation_payload, persist_simulation
from app.simulator.rescue_ball import RescueBallDevice
from app.simulator.scenarios import (
    RIVERTOWN_FLOOD_PATH,
    inject_battery_drain,
    inject_blocked_route,
    inject_connectivity_loss,
    inject_environmental_temp,
    inject_human_heat_signature,
    inject_motion,
    inject_sensor_degradation,
    inject_thermal_hotspot,
    inject_vibration,
    inject_water_depth,
)
from app.streaming.producer import ProducerManager

logger = logging.getLogger("app.simulator.engine")

# Maps fault type names to scenario injection functions.
_FAULT_INJECTIONS: dict[str, Callable[..., None]] = {
    "battery_drain": inject_battery_drain,
    "sensor_degradation": inject_sensor_degradation,
    "connectivity_loss": inject_connectivity_loss,
    "blocked_route": inject_blocked_route,
    "thermal_hotspot": inject_thermal_hotspot,
    "human_heat_signature": inject_human_heat_signature,
    "water_depth": inject_water_depth,
    "motion": inject_motion,
    "vibration": inject_vibration,
    "environmental_temp": inject_environmental_temp,
}

# Phenomena published per device per tick: (phenomenon, attr, unit).
_PHENOMENA: list[tuple[str, str, str]] = [
    ("battery_level", "battery_pct", "%"),
    ("device_temperature", "device_temperature", "celsius"),
    ("signal_quality", "signal_quality", "%"),
    ("altitude", "altitude", "m"),
]

_TICK_MS = 1000  # 1 second per tick


class SimulationEngine:
    """Seeded digital twin with explicit Kafka or local database transport."""

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._rng = random.Random(seed)
        self._devices: list[RescueBallDevice] = []
        self._task: asyncio.Task[None] | None = None
        self._state = "stopped"  # stopped | running | paused
        self._speed = 1.0
        self._org_id = ""
        self._incident_id = ""
        self._sim_time_ms = 0
        self._producer: ProducerManager | None = None
        self._observation_ids: list[str] = []
        self._run_id = ""

    @property
    def observation_ids(self) -> list[str]:
        """List of observation IDs published so far (deterministic per seed)."""
        return list(self._observation_ids)

    def start(self, org_id: str, incident_id: str, device_count: int = 2) -> list[str]:
        """Create devices and start the simulation loop. Returns device IDs."""
        if self._state != "stopped":
            raise RuntimeError("Simulation already running — call stop() first")
        self._org_id = org_id
        self._incident_id = incident_id
        self._rng = random.Random(self._seed)
        self._sim_time_ms = 0
        self._observation_ids.clear()
        self._run_id = generate_ulid()
        self._devices = [self._make_device(i) for i in range(device_count)]
        self._state = "running"
        self._task = asyncio.create_task(self._run_loop())
        return [d.device_id for d in self._devices]

    def _make_device(self, index: int) -> RescueBallDevice:
        """Create a RescueBallDevice at a Rivertown flood-path waypoint."""
        wp = RIVERTOWN_FLOOD_PATH[index % len(RIVERTOWN_FLOOD_PATH)]
        return RescueBallDevice(
            device_id=f"rescue-ball-{index + 1:03d}",
            org_id=self._org_id,
            incident_id=self._incident_id,
            lon=wp[0],
            lat=wp[1],
            altitude=wp[2],
            deployment_state="deployed",
            velocity=0.5 + self._rng.random() * 1.0,
            heading=self._rng.uniform(0.0, 360.0),
            battery_pct=80.0 + self._rng.random() * 20.0,
            estimated_remaining_runtime=3600,
            link_type="lte",
            signal_quality=70.0 + self._rng.random() * 30.0,
            packet_loss=0.0,
            device_temperature=25.0,
            enclosure_status="ok",
            camera_status="active",
            thermal_sensor_status="active",
            imu_reading={},
            acoustic_reading={},
            last_seen_ts=self._sim_time_ms,
            health_flags={},
        )

    def pause(self) -> None:
        """Pause the simulation loop."""
        if self._state == "running":
            self._state = "paused"

    def resume(self) -> None:
        """Resume a paused simulation."""
        if self._state == "paused":
            self._state = "running"

    def set_speed(self, speed: float) -> None:
        """Set the simulation speed multiplier (1.0 = real-time)."""
        if speed <= 0.0:
            raise ValueError("speed must be positive")
        self._speed = speed

    async def stop(self) -> None:
        """Stop the simulation and cancel the background task."""
        if self._state == "stopped":
            return
        self._state = "stopped"
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Producer stop failed (non-fatal): %s", exc)
            self._producer = None

    async def replay(self, seed: int) -> list[str]:
        """Stop the simulation and replay from the given seed."""
        org_id = self._org_id
        incident_id = self._incident_id
        device_count = len(self._devices)
        await self.stop()
        self._seed = seed
        return self.start(org_id, incident_id, device_count)

    def inject_fault(self, device_id: str, fault_type: str, **kwargs) -> None:
        """Inject a fault into a device via a scenario function."""
        device = next((d for d in self._devices if d.device_id == device_id), None)
        if device is None:
            raise ValueError(f"unknown device: {device_id}")
        fault_fn = _FAULT_INJECTIONS.get(fault_type)
        if fault_fn is None:
            raise ValueError(f"unknown fault type: {fault_type}")
        fault_fn(device, **kwargs)

    def status(self) -> dict:
        """Return the current simulation state."""
        return {
            "state": self._state,
            "device_count": len(self._devices),
            "speed": self._speed,
            "seed": self._seed,
            "sim_time_ms": self._sim_time_ms,
            "device_ids": [d.device_id for d in self._devices],
        }

    async def _run_loop(self) -> None:
        """Background simulation loop — steps devices and publishes observations."""
        await self._ensure_producer()
        while self._state != "stopped":
            if self._state == "paused":
                await asyncio.sleep(0.1)
                continue
            for device in self._devices:
                device.step(_TICK_MS, self._rng)
                for phenomenon, attr, unit in _PHENOMENA:
                    value = getattr(device, attr)
                    await self._publish_observation(device, phenomenon, value, unit)
            self._sim_time_ms += _TICK_MS
            await asyncio.sleep(_TICK_MS / 1000.0 / self._speed)

    async def _ensure_producer(self) -> None:
        """Start the Kafka producer (best-effort — non-fatal if unavailable)."""
        if settings.SIMULATOR_TRANSPORT == "database":
            return
        if self._producer is None:
            self._producer = ProducerManager()
        if not self._producer.is_started:
            try:
                await asyncio.wait_for(self._producer.start(), timeout=1.0)
            except Exception as exc:
                logger.warning("Kafka producer unavailable (non-fatal): %s", exc)
                self._producer = None

    async def _publish_observation(
        self, device: RescueBallDevice, phenomenon: str, value: float, unit: str
    ) -> None:
        """Publish an observation to Kafka, matching the consumer payload format.

        The payload fields match ``ConsumerManager._build_observation`` in
        ``consumer.py``. The ``provenance_chain`` carries ``{"simulated": True}``
        so downstream consumers can distinguish simulated from real data.
        """
        obs_id = _deterministic_ulid(self._rng, self._sim_time_ms)
        payload = build_simulation_payload(self, device, phenomenon, value, unit, obs_id)
        self._observation_ids.append(obs_id)
        if settings.SIMULATOR_TRANSPORT == "database":
            await asyncio.to_thread(persist_simulation, payload, self._run_id)
        elif self._producer is not None and self._producer.is_started:
            try:
                await self._producer.send("observations.raw", payload)
            except Exception as exc:
                logger.warning("Failed to publish observation %s: %s", obs_id, exc)
        else:
            logger.debug("Producer unavailable — observation %s not published", obs_id)


__all__ = ["SimulationEngine"]
