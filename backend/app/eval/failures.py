"""Failure injection framework for eval testbed (T42).

Configurable failures: feed loss, delays, false reports, duplicates, geolocation
ambiguity, cloud cover, SAR noise, tower/shelter/responder/road/hospital failures,
multilingual, adversarial misinformation. All inject_* return new collections.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from app.eval.failure_robustness import RobustnessFailureMixin
from app.eval.testbed_types import (
    EntityStatus,
    Hospital,
    ObservationSource,
    ResponderStation,
    RoadGraph,
    Shelter,
    TestbedInfrastructure,
    TestbedObservation,
)

if TYPE_CHECKING:
    from app.eval.testbed import DigitalTwinTestbed

_DEG_TO_M = 111_320.0
_MISINFO_TYPES = frozenset({"misinformation", "adversarial"})
_LANGS = ("hi", "en_hi", "ta", "bn", "te", "mr")

_OBS_DISPATCH: dict[str, str] = {"feed_loss": "inject_feed_loss", "delay": "inject_delay", "false_reports": "inject_false_reports", "duplicates": "inject_duplicates", "geolocation_ambiguity": "inject_geolocation_ambiguity", "multilingual": "inject_multilingual", "adversarial_misinformation": "inject_adversarial_misinformation", "sensor_outage": "inject_sensor_outage", "sensor_delay": "inject_sensor_delay", "sensor_duplicates": "inject_sensor_duplicates", "sensor_conflict": "inject_conflicting_sensors", "weather_quality": "inject_weather_quality"}
_INFRA_DISPATCH: dict[str, tuple[str, str | None]] = {
    "tower_failure": ("inject_tower_failure", None),
    "shelter_capacity_change": ("inject_shelter_capacity_change", "shelters"),
    "responder_unavailability": ("inject_responder_unavailability", "responder_stations"),
    "road_failure": ("inject_road_failure", "roads"),
    "hospital_closure": ("inject_hospital_closure", "hospitals"),
}


def confidence_vector(observations: list[TestbedObservation]) -> list[float]:
    """Confidence [0.0, 1.0] per observation. Misinformation -> 0.0."""
    return [0.0 if o.event_type in _MISINFO_TYPES else 1.0 for o in observations]


def _distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return ((lon2 - lon1) ** 2 + (lat2 - lat1) ** 2) ** 0.5 * _DEG_TO_M


class FailureInjector(RobustnessFailureMixin):
    """Inject configurable failures into testbed infrastructure and observations."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = np.random.default_rng(seed)

    def inject_feed_loss(
        self, observations: list[TestbedObservation], loss_pct: float
    ) -> list[TestbedObservation]:
        """Remove loss_pct% of observations."""
        n = len(observations)
        k = int(n * loss_pct / 100.0)
        if k == 0:
            return list(observations)
        drop = set(self._rng.choice(n, k, replace=False).tolist())
        return [o for i, o in enumerate(observations) if i not in drop]

    def inject_delay(
        self, observations: list[TestbedObservation], delay_minutes: int
    ) -> list[TestbedObservation]:
        """Add delay to official reports."""
        d = int(delay_minutes) * 60_000
        return [
            dataclasses.replace(o, timestamp_ms=o.timestamp_ms + d)
            if o.source_type == ObservationSource.official_alert else o
            for o in observations
        ]

    def _inject_synthetic(
        self, observations: list[TestbedObservation], count: int,
        event_type: str, value_fn: Callable[[int], float], interval_ms: int,
    ) -> list[TestbedObservation]:
        """Build synthetic citizen reports at random locations within the bbox."""
        if not observations:
            return list(observations)
        lons = [o.lon for o in observations]
        lats = [o.lat for o in observations]
        ts0 = observations[0].timestamp_ms
        out = list(observations)
        for i in range(count):
            out.append(TestbedObservation(
                ts0 + i * interval_ms, ObservationSource.citizen_report,
                float(self._rng.uniform(min(lons), max(lons))),
                float(self._rng.uniform(min(lats), max(lats))),
                value_fn(i), "severity", event_type))
        return out

    def inject_false_reports(
        self, observations: list[TestbedObservation], count: int
    ) -> list[TestbedObservation]:
        """Inject misinformation reports (flagged by confidence_vector)."""
        return self._inject_synthetic(
            observations, count, "misinformation",
            lambda _: float(self._rng.uniform(0.8, 1.0)), 60_000)

    def inject_duplicates(
        self, observations: list[TestbedObservation], count: int
    ) -> list[TestbedObservation]:
        """Inject duplicate posts."""
        if not observations:
            return list(observations)
        out = list(observations)
        for _ in range(count):
            out.append(observations[int(self._rng.integers(0, len(observations)))])
        return out

    def inject_geolocation_ambiguity(
        self, observations: list[TestbedObservation], pct: float
    ) -> list[TestbedObservation]:
        """Replace exact coords with vague place names (rounded coords)."""
        n = len(observations)
        k = int(n * pct / 100.0)
        if k == 0:
            return list(observations)
        idx = set(self._rng.choice(n, k, replace=False).tolist())
        return [
            dataclasses.replace(o, lon=round(o.lon, 1), lat=round(o.lat, 1))
            if i in idx else o
            for i, o in enumerate(observations)
        ]

    def inject_multilingual(
        self, observations: list[TestbedObservation], pct: float
    ) -> list[TestbedObservation]:
        """Add multilingual/code-mixed reports (language tag in event_type)."""
        cidx = [i for i, o in enumerate(observations)
                if o.source_type == ObservationSource.citizen_report]
        k = int(len(cidx) * pct / 100.0)
        if k == 0:
            return list(observations)
        sel = set(self._rng.choice(len(cidx), k, replace=False).tolist())
        lang = {cidx[j]: str(self._rng.choice(_LANGS)) for j in sel}
        return [
            dataclasses.replace(o, event_type=f"{o.event_type}_{lang[i]}")
            if i in lang else o
            for i, o in enumerate(observations)
        ]

    def inject_adversarial_misinformation(
        self, observations: list[TestbedObservation], count: int
    ) -> list[TestbedObservation]:
        """Inject adversarial misinformation (panic-inducing, max severity)."""
        return self._inject_synthetic(
            observations, count, "adversarial", lambda _: 1.0, 30_000)

    def inject_cloud_cover(self, satellite_data: np.ndarray) -> np.ndarray:
        """Block optical imagery (Sentinel-2) via cloud cover."""
        return np.zeros_like(satellite_data)

    def inject_sar_noise(
        self, flood_map: np.ndarray, noise_level: float
    ) -> np.ndarray:
        """Add Gaussian noise to SAR flood map."""
        noise = self._rng.normal(0, noise_level, size=flood_map.shape)
        return np.clip(flood_map + noise, 0.0, 1.0).astype(flood_map.dtype)

    def inject_tower_failure(
        self, infrastructure: TestbedInfrastructure, tower_id: str
    ) -> TestbedInfrastructure:
        """Disable a cell tower."""
        towers = tuple(
            dataclasses.replace(t, status=EntityStatus.offline) if t.id == tower_id else t
            for t in infrastructure.cell_towers
        )
        return dataclasses.replace(infrastructure, cell_towers=towers)

    def inject_shelter_capacity_change(
        self, shelters: tuple[Shelter, ...], change_pct: float
    ) -> tuple[Shelter, ...]:
        """Change shelter capacity by change_pct%."""
        f = 1.0 + change_pct / 100.0
        return tuple(
            dataclasses.replace(s, capacity=max(0, int(s.capacity * f)))
            for s in shelters
        )

    def inject_responder_unavailability(
        self, responders: tuple[ResponderStation, ...], count: int
    ) -> tuple[ResponderStation, ...]:
        """Mark count responders as unavailable (offline)."""
        n = len(responders)
        k = min(count, n)
        idx = set(self._rng.choice(n, k, replace=False).tolist()) if k > 0 else set()
        return tuple(
            dataclasses.replace(r, status=EntityStatus.offline) if i in idx else r
            for i, r in enumerate(responders)
        )

    def inject_road_failure(self, roads: RoadGraph, count: int) -> RoadGraph:
        """Mark count roads as failed (flood_vulnerability = 1.0)."""
        edges = list(roads.edges)
        n = len(edges)
        k = min(count, n)
        idx = set(self._rng.choice(n, k, replace=False).tolist()) if k > 0 else set()
        new = [
            dataclasses.replace(e, flood_vulnerability=1.0) if i in idx else e
            for i, e in enumerate(edges)
        ]
        return dataclasses.replace(roads, edges=tuple(new))

    def inject_hospital_closure(
        self, hospitals: tuple[Hospital, ...], hospital_id: str
    ) -> tuple[Hospital, ...]:
        """Close a hospital."""
        return tuple(
            dataclasses.replace(h, status=EntityStatus.offline) if h.id == hospital_id else h
            for h in hospitals
        )

    def apply_tower_cascade(
        self, infrastructure: TestbedInfrastructure,
        observations: list[TestbedObservation],
    ) -> list[TestbedObservation]:
        """Silence citizen reports from devices near offline towers."""
        offline = [t for t in infrastructure.cell_towers
                   if t.status == EntityStatus.offline]
        if not offline:
            return list(observations)
        return [
            o for o in observations
            if o.source_type != ObservationSource.citizen_report
            or not any(
                _distance_m(t.lon, t.lat, o.lon, o.lat) <= t.range_m
                for t in offline
            )
        ]

    def apply_failures(
        self, testbed: DigitalTwinTestbed, failure_config: list[dict[str, Any]],
        obs_seed: int = 42, duration_hours: int = 24,
    ) -> dict[str, Any]:
        """Apply all configured failures to testbed.

        failure_config: list of {"type": str, "params": dict}.
        Returns dict with infrastructure, observations, and metrics.
        """
        infra = testbed.get_infrastructure()
        obs = testbed.generate_observation_stream(
            seed=obs_seed, duration_hours=duration_hours
        )
        orig_count = len(obs)
        for f in failure_config:
            ft, p = f["type"], f.get("params", {})
            if ft in _OBS_DISPATCH:
                obs = getattr(self, _OBS_DISPATCH[ft])(obs, **p)
            elif ft in _INFRA_DISPATCH:
                m, attr = _INFRA_DISPATCH[ft]
                if attr is None:
                    infra = getattr(self, m)(infra, **p)
                else:
                    new_val = getattr(self, m)(getattr(infra, attr), **p)
                    infra = dataclasses.replace(infra, **{attr: new_val})
        obs = self.apply_tower_cascade(infra, obs)
        testbed._infra = infra
        return {
            "infrastructure": infra,
            "observations": obs,
            "metrics": {
                "original_obs_count": orig_count, "final_obs_count": len(obs),
                "failed_towers": sum(1 for t in infra.cell_towers if t.status == EntityStatus.offline),
                "failed_roads": sum(1 for e in infra.roads.edges if e.flood_vulnerability >= 1.0),
                "closed_hospitals": sum(1 for h in infra.hospitals if h.status == EntityStatus.offline),
                "offline_responders": sum(1 for r in infra.responder_stations if r.status == EntityStatus.offline),
            },
        }


__all__ = ["FailureInjector", "confidence_vector"]
