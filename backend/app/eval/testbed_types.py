"""Dataclasses + helpers for the digital twin testbed (T41).

All entities are frozen dataclasses for deterministic, hashable infrastructure.
The testbed generates a city-scale digital twin for an Indian coastal-city
cyclone-flood scenario (Mumbai/Chennai-style coordinates ~19.0N, 72.8E).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np


class BuildingType(str, Enum):
    residential = "residential"
    commercial = "commercial"
    industrial = "industrial"
    institutional = "institutional"
    mixed = "mixed"


class RoadClass(str, Enum):
    highway = "highway"
    arterial = "arterial"
    residential = "residential"


class EntityStatus(str, Enum):
    operational = "operational"
    degraded = "degraded"
    offline = "offline"


class ObservationSource(str, Enum):
    sensor = "sensor"
    citizen_report = "citizen_report"
    official_alert = "official_alert"


@dataclass(frozen=True, slots=True)
class TestbedParams:
    """Configurable parameters for testbed generation.

    Defaults produce a Mumbai-scale coastal city: 1000 buildings, 50 roads,
    2 hospitals, 5 shelters, 10000 population.
    """
    __test__ = False  # prevent pytest collection (name starts with "Test")
    population: int = 10_000
    building_count: int = 1_000
    road_count: int = 50
    hospital_count: int = 2
    shelter_count: int = 5
    substation_count: int = 3
    cell_tower_count: int = 5
    responder_station_count: int = 4
    citizen_device_count: int = 200
    dem_resolution: int = 50
    city_center_lat: float = 19.0760
    city_center_lon: float = 72.8777
    bbox_extent_deg: float = 0.15
    road_density: float = 1.0
    hazard_intensity: float = 0.7


@dataclass(frozen=True, slots=True)
class TerrainDEM:
    grid: np.ndarray
    resolution: int
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Building:
    id: str
    lon: float
    lat: float
    footprint_area_m2: float
    building_type: BuildingType
    height_floors: int
    age_years: int
    construction_quality: float
    vulnerability_score: float


@dataclass(frozen=True, slots=True)
class RoadNode:
    id: str
    lon: float
    lat: float


@dataclass(frozen=True, slots=True)
class RoadEdge:
    id: str
    from_node: str
    to_node: str
    road_class: RoadClass
    length_m: float
    flood_vulnerability: float


@dataclass(frozen=True, slots=True)
class RoadGraph:
    nodes: tuple[RoadNode, ...]
    edges: tuple[RoadEdge, ...]


@dataclass(frozen=True, slots=True)
class Hospital:
    id: str
    lon: float
    lat: float
    capacity: int
    status: EntityStatus


@dataclass(frozen=True, slots=True)
class Shelter:
    id: str
    lon: float
    lat: float
    capacity: int
    occupancy: int
    status: EntityStatus


@dataclass(frozen=True, slots=True)
class PopulationHex:
    h3_index: str
    lon: float
    lat: float
    population: int
    vulnerability: str


@dataclass(frozen=True, slots=True)
class Substation:
    id: str
    lon: float
    lat: float
    capacity_mw: float
    status: EntityStatus


@dataclass(frozen=True, slots=True)
class CellTower:
    id: str
    lon: float
    lat: float
    range_m: float
    status: EntityStatus


@dataclass(frozen=True, slots=True)
class ResponderStation:
    id: str
    lon: float
    lat: float
    team_type: str
    capacity: int
    status: EntityStatus


@dataclass(frozen=True, slots=True)
class CitizenDevice:
    id: str
    lon: float
    lat: float
    device_type: str
    battery_pct: float


@dataclass(frozen=True, slots=True)
class TestbedObservation:
    timestamp_ms: int
    source_type: ObservationSource
    lon: float
    lat: float
    value: float
    unit: str
    event_type: str


@dataclass(frozen=True, slots=True)
class TestbedInfrastructure:
    terrain: TerrainDEM
    buildings: tuple[Building, ...]
    roads: RoadGraph
    hospitals: tuple[Hospital, ...]
    shelters: tuple[Shelter, ...]
    population: tuple[PopulationHex, ...]
    substations: tuple[Substation, ...]
    cell_towers: tuple[CellTower, ...]
    responder_stations: tuple[ResponderStation, ...]
    citizen_devices: tuple[CitizenDevice, ...]


def stable_id(prefix: str, seed: int, idx: int) -> str:
    """Deterministic 12-char hex ID from (prefix, seed, idx) — no RNG consumed."""
    h = hashlib.sha256(f"{prefix}:{seed}:{idx}".encode()).hexdigest()[:12]
    return f"{prefix}_{h}"


def serialize(obj: Any) -> Any:
    """Canonical serializer for fingerprinting (numpy + enums + dataclasses)."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, tuple):
        return [serialize(x) for x in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: serialize(getattr(obj, k)) for k in obj.__dataclass_fields__}
    return obj


def fingerprint(infra: TestbedInfrastructure) -> str:
    """SHA-256 hash of canonical infrastructure serialization."""
    canonical = json.dumps(serialize(infra), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


__all__ = [
    "BuildingType", "RoadClass", "EntityStatus", "ObservationSource",
    "TestbedParams", "TerrainDEM", "Building", "RoadNode", "RoadEdge",
    "RoadGraph", "Hospital", "Shelter", "PopulationHex", "Substation",
    "CellTower", "ResponderStation", "CitizenDevice", "TestbedObservation",
    "TestbedInfrastructure", "stable_id", "serialize", "fingerprint",
]
