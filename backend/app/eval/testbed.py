"""Replayable cyclone-flood digital twin testbed (T41).

City-scale digital twin for an Indian coastal-city cyclone-flood scenario
(Mumbai coordinates ~19.0N, 72.8E). Generates terrain, buildings, roads,
hospitals, shelters, population (H3 hexes), substations, cell towers,
responder stations, and citizen devices. Same seed + same params -> identical
output. Replayable with different parameters and seeds.
"""

from __future__ import annotations

import numpy as np

from app.eval.testbed_helpers import (
    gen_buildings,
    gen_cell_towers,
    gen_citizens,
    gen_hospitals,
    gen_population,
    gen_responders,
    gen_roads,
    gen_shelters,
    gen_substations,
    gen_terrain,
)
from app.eval.testbed_types import (
    ObservationSource,
    PopulationHex,
    RoadGraph,
    TestbedInfrastructure,
    TestbedObservation,
    TestbedParams,
    fingerprint,
)

_BASE_TS_MS = 1_753_000_000_000  # 2026-07-20T00:00:00Z


class DigitalTwinTestbed:
    """Replayable city-scale digital twin for cyclone-flood scenarios.

    Deterministic: same seed + same params always produces identical
    infrastructure and observation stream. Different seeds or params
    produce different output.
    """

    def __init__(self, params: TestbedParams | None = None) -> None:
        self._params = params or TestbedParams()
        self._infra: TestbedInfrastructure | None = None
        self._seed: int = 0

    def generate(
        self, seed: int, params: TestbedParams | None = None
    ) -> TestbedInfrastructure:
        """Generate deterministic testbed infrastructure.

        Same seed + same params always produces identical output.
        """
        if params is not None:
            self._params = params
        self._seed = seed
        p, rng = self._params, np.random.default_rng(seed)
        bbox = self._bbox(p)
        terrain = gen_terrain(rng, p, bbox)
        self._infra = TestbedInfrastructure(
            terrain=terrain,
            buildings=gen_buildings(rng, p, terrain, self._seed),
            roads=gen_roads(rng, p, terrain, self._seed),
            hospitals=gen_hospitals(rng, p, bbox, self._seed),
            shelters=gen_shelters(rng, p, bbox, self._seed),
            population=gen_population(rng, p, bbox, self._seed),
            substations=gen_substations(rng, p, bbox, self._seed),
            cell_towers=gen_cell_towers(rng, p, bbox, self._seed),
            responder_stations=gen_responders(rng, p, bbox, self._seed),
            citizen_devices=gen_citizens(rng, p, bbox, self._seed),
        )
        return self._infra

    def _bbox(self, p: TestbedParams) -> tuple[float, float, float, float]:
        clat, clon, ext = p.city_center_lat, p.city_center_lon, p.bbox_extent_deg
        return (clon - ext, clat - ext, clon + ext, clat + ext)

    def generate_observation_stream(
        self, seed: int, duration_hours: int
    ) -> list[TestbedObservation]:
        """Produce reproducible observation stream over duration_hours.

        Generates sensor readings (water level at substations), citizen reports
        (flood reports from citizen devices), and official alerts (cyclone
        alerts at regular intervals). Same seed + same infrastructure always
        produces the same stream.
        """
        if self._infra is None:
            raise RuntimeError("Call generate() before generate_observation_stream()")
        rng = np.random.default_rng(seed)
        p = self._params
        start_ms, end_ms = _BASE_TS_MS, _BASE_TS_MS + duration_hours * 3_600_000
        obs: list[TestbedObservation] = []
        for sub in self._infra.substations:
            t = start_ms
            while t < end_ms:
                obs.append(TestbedObservation(int(t), ObservationSource.sensor,
                    sub.lon, sub.lat, float(rng.uniform(0, 3.0)), "m", "water_level"))
                t += int(rng.integers(15, 60)) * 60_000
        for dev in self._infra.citizen_devices[:50]:
            for _ in range(int(rng.integers(0, 3))):
                obs.append(TestbedObservation(int(rng.integers(start_ms, end_ms)),
                    ObservationSource.citizen_report, dev.lon, dev.lat,
                    float(rng.uniform(0, 1)), "severity", "flood_report"))
        for i in range(max(1, duration_hours // 2)):
            obs.append(TestbedObservation(start_ms + i * 2 * 3_600_000,
                ObservationSource.official_alert, p.city_center_lon,
                p.city_center_lat, float(rng.uniform(0.5, 1.0)), "severity",
                "cyclone_alert"))
        obs.sort(key=lambda o: o.timestamp_ms)
        return obs

    def get_infrastructure(self) -> TestbedInfrastructure:
        if self._infra is None:
            raise RuntimeError("Call generate() first")
        return self._infra

    def get_population(self) -> tuple[PopulationHex, ...]:
        if self._infra is None:
            raise RuntimeError("Call generate() first")
        return self._infra.population

    def get_road_graph(self) -> RoadGraph:
        if self._infra is None:
            raise RuntimeError("Call generate() first")
        return self._infra.roads

    def fingerprint(self) -> str:
        """SHA-256 hash of canonical infrastructure serialization."""
        if self._infra is None:
            raise RuntimeError("Call generate() first")
        return fingerprint(self._infra)


__all__ = ["DigitalTwinTestbed"]
