"""Sensor and input-specific failure injectors for the eval testbed."""

from __future__ import annotations

import dataclasses

import numpy as np

from app.eval.testbed_types import ObservationSource, TestbedObservation


class RobustnessFailureMixin:
    """Add deterministic missing-modality and conflict injections."""

    _rng: np.random.Generator

    def inject_sensor_outage(
        self, observations: list[TestbedObservation], loss_pct: float = 10.0
    ) -> list[TestbedObservation]:
        """Remove a percentage of sensor observations without touching reports."""
        sensor_indices = [
            index for index, observation in enumerate(observations)
            if observation.source_type == ObservationSource.sensor
        ]
        count = int(len(sensor_indices) * loss_pct / 100.0)
        if count == 0:
            return list(observations)
        removed = set(self._rng.choice(sensor_indices, count, replace=False).tolist())
        return [observation for index, observation in enumerate(observations) if index not in removed]

    def inject_sensor_delay(
        self, observations: list[TestbedObservation], delay_minutes: int = 30
    ) -> list[TestbedObservation]:
        """Delay sensor timestamps while preserving their source provenance."""
        delay_ms = delay_minutes * 60_000
        return [
            dataclasses.replace(observation, timestamp_ms=observation.timestamp_ms + delay_ms)
            if observation.source_type == ObservationSource.sensor else observation
            for observation in observations
        ]

    def inject_sensor_duplicates(
        self, observations: list[TestbedObservation], count: int = 1
    ) -> list[TestbedObservation]:
        """Append exact sensor duplicates for deduplication evaluation."""
        sensors = [
            observation for observation in observations
            if observation.source_type == ObservationSource.sensor
        ]
        if not sensors or count <= 0:
            return list(observations)
        selected = [sensors[index] for index in self._rng.integers(0, len(sensors), count)]
        return [*observations, *selected]

    def inject_conflicting_sensors(
        self, observations: list[TestbedObservation], count: int = 1
    ) -> list[TestbedObservation]:
        """Append contradictory sensor readings that must never become truth."""
        sensors = [
            observation for observation in observations
            if observation.source_type == ObservationSource.sensor
        ]
        if not sensors or count <= 0:
            return list(observations)
        selected = [sensors[index] for index in self._rng.integers(0, len(sensors), count)]
        conflicts = [
            dataclasses.replace(
                observation,
                value=1.0 - observation.value,
                event_type="sensor_conflict",
            )
            for observation in selected
        ]
        return [*observations, *conflicts]

    def inject_weather_quality(
        self, observations: list[TestbedObservation], pct: float = 10.0
    ) -> list[TestbedObservation]:
        """Mark a deterministic subset as weather or input-quality degraded."""
        count = int(len(observations) * pct / 100.0)
        if count == 0:
            return list(observations)
        selected = set(self._rng.choice(len(observations), count, replace=False).tolist())
        return [
            dataclasses.replace(observation, event_type="weather_low_quality")
            if index in selected else observation
            for index, observation in enumerate(observations)
        ]


__all__ = ["RobustnessFailureMixin"]
