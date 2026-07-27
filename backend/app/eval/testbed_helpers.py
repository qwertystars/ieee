"""Infrastructure generation helpers for the digital twin testbed (T41).

Split from ``testbed.py`` to keep both files under the 250 pure LOC ceiling.
Each function is a pure generator: same (rng, params, bbox, seed) -> identical
output. Called by ``DigitalTwinTestbed.generate()``.
"""

from __future__ import annotations

import numpy as np

from app.eval.testbed_types import (
    Building,
    BuildingType,
    CellTower,
    CitizenDevice,
    EntityStatus,
    Hospital,
    PopulationHex,
    ResponderStation,
    RoadClass,
    RoadEdge,
    RoadGraph,
    RoadNode,
    Shelter,
    Substation,
    TerrainDEM,
    TestbedParams,
    stable_id,
)

_DEG_TO_M = 111_320.0


def gen_terrain(
    rng: np.random.Generator,
    p: TestbedParams,
    bbox: tuple[float, float, float, float],
) -> TerrainDEM:
    res = p.dem_resolution
    min_lon, _min_lat, max_lon, _max_lat = bbox
    lons = np.linspace(min_lon, max_lon, res)
    base = np.abs(lons - min_lon) * 50.0 / p.bbox_extent_deg
    noise = rng.normal(0, 3.0, size=(res, res))
    grid = np.maximum(0.0, base[np.newaxis, :] + noise).astype(np.float32)
    return TerrainDEM(grid=grid, resolution=res, bounds=bbox)


def elev_at(lon: float, lat: float, t: TerrainDEM) -> float:
    min_lon, min_lat, max_lon, max_lat = t.bounds
    res = t.resolution
    j = max(0, min(res - 1, int((lon - min_lon) / (max_lon - min_lon) * (res - 1))))
    i = max(0, min(res - 1, int((lat - min_lat) / (max_lat - min_lat) * (res - 1))))
    return float(t.grid[i, j])


def gen_buildings(
    rng: np.random.Generator,
    p: TestbedParams,
    terrain: TerrainDEM,
    seed: int,
) -> tuple[Building, ...]:
    min_lon, min_lat, max_lon, max_lat = terrain.bounds
    n = p.building_count
    lons = rng.uniform(min_lon, max_lon, n)
    lats = rng.uniform(min_lat, max_lat, n)
    heights = rng.integers(1, 31, n)
    ages = rng.integers(1, 81, n)
    quals = rng.uniform(0.3, 1.0, n)
    footprints = rng.uniform(50, 500, n)
    tidx = rng.choice(5, n, p=[0.6, 0.2, 0.1, 0.05, 0.05])
    types = list(BuildingType)
    coast = np.abs(lons - min_lon)
    vulns = np.minimum(1.0, (ages / 80.0) * 0.3 + (heights / 30.0) * 0.2
                       + (1.0 - quals) * 0.3 + (1.0 - coast / p.bbox_extent_deg) * 0.2)
    return tuple(
        Building(id=stable_id("bld", seed, i), lon=float(lons[i]),
                 lat=float(lats[i]), footprint_area_m2=float(footprints[i]),
                 building_type=types[int(tidx[i])], height_floors=int(heights[i]),
                 age_years=int(ages[i]), construction_quality=float(quals[i]),
                 vulnerability_score=float(vulns[i]))
        for i in range(n))


def gen_roads(
    rng: np.random.Generator,
    p: TestbedParams,
    terrain: TerrainDEM,
    seed: int,
) -> RoadGraph:
    min_lon, min_lat, max_lon, max_lat = terrain.bounds
    n_side = int(np.ceil(np.sqrt(p.road_count)))
    nodes = tuple(
        RoadNode(id=stable_id("node", seed, r * n_side + c),
                 lon=float(min_lon + (max_lon - min_lon) * c / max(1, n_side - 1)),
                 lat=float(min_lat + (max_lat - min_lat) * r / max(1, n_side - 1)))
        for r in range(n_side) for c in range(n_side))
    edges: list[RoadEdge] = []
    classes = list(RoadClass)
    cprobs = [0.1, 0.3, 0.6]
    for idx, n1 in enumerate(nodes):
        for nbr in (idx + 1, idx + n_side):
            if len(edges) >= p.road_count or nbr >= len(nodes):
                continue
            n2 = nodes[nbr]
            length = (((n2.lon - n1.lon) ** 2 + (n2.lat - n1.lat) ** 2) ** 0.5) * _DEG_TO_M
            rc = classes[int(rng.choice(3, p=cprobs))]
            elev = elev_at(n1.lon, n1.lat, terrain)
            vuln = float(min(1.0, max(0.0, 1.0 - elev / 50.0)))
            edges.append(RoadEdge(id=stable_id("road", seed, len(edges)),
                                  from_node=n1.id, to_node=n2.id, road_class=rc,
                                  length_m=float(length), flood_vulnerability=vuln))
    return RoadGraph(nodes=nodes, edges=tuple(edges))


def gen_hospitals(
    rng: np.random.Generator,
    p: TestbedParams,
    bbox: tuple[float, float, float, float],
    seed: int,
) -> tuple[Hospital, ...]:
    min_lon, min_lat, max_lon, max_lat = bbox
    lons = rng.uniform(min_lon, max_lon, p.hospital_count)
    lats = rng.uniform(min_lat, max_lat, p.hospital_count)
    caps = rng.integers(100, 500, p.hospital_count)
    return tuple(
        Hospital(id=stable_id("hosp", seed, i), lon=float(lons[i]),
                 lat=float(lats[i]), capacity=int(caps[i]),
                 status=EntityStatus.operational)
        for i in range(p.hospital_count))


def gen_shelters(
    rng: np.random.Generator,
    p: TestbedParams,
    bbox: tuple[float, float, float, float],
    seed: int,
) -> tuple[Shelter, ...]:
    min_lon, min_lat, max_lon, max_lat = bbox
    n = p.shelter_count
    lons = rng.uniform(min_lon, max_lon, n)
    lats = rng.uniform(min_lat, max_lat, n)
    caps = rng.integers(50, 500, n)
    occs = np.array([int(rng.integers(0, c + 1)) for c in caps])
    return tuple(
        Shelter(id=stable_id("shl", seed, i), lon=float(lons[i]),
                lat=float(lats[i]), capacity=int(caps[i]),
                occupancy=int(occs[i]), status=EntityStatus.operational)
        for i in range(n))


def gen_population(
    rng: np.random.Generator,
    p: TestbedParams,
    bbox: tuple[float, float, float, float],
    seed: int,
) -> tuple[PopulationHex, ...]:
    min_lon, min_lat, max_lon, max_lat = bbox
    n_hex = 36
    shares = rng.dirichlet(np.ones(n_hex))
    pops = (shares * p.population).astype(int)
    pops[0] += p.population - int(pops.sum())
    hw, hh = (max_lon - min_lon) / 6, (max_lat - min_lat) / 6
    vulns = ["low", "medium", "high"]
    vidx = rng.choice(3, n_hex, p=[0.3, 0.4, 0.3])
    return tuple(
        PopulationHex(h3_index=stable_id("h3", seed, i),
            lon=float(min_lon + (i % 6 + 0.5) * hw),
            lat=float(min_lat + (i // 6 + 0.5) * hh),
            population=int(pops[i]), vulnerability=str(vulns[int(vidx[i])]))
        for i in range(n_hex))


def gen_substations(
    rng: np.random.Generator,
    p: TestbedParams,
    bbox: tuple[float, float, float, float],
    seed: int,
) -> tuple[Substation, ...]:
    min_lon, min_lat, max_lon, max_lat = bbox
    lons = rng.uniform(min_lon, max_lon, p.substation_count)
    lats = rng.uniform(min_lat, max_lat, p.substation_count)
    caps = rng.uniform(10, 100, p.substation_count)
    return tuple(
        Substation(id=stable_id("sub", seed, i), lon=float(lons[i]),
                   lat=float(lats[i]), capacity_mw=float(caps[i]),
                   status=EntityStatus.operational)
        for i in range(p.substation_count))


def gen_cell_towers(
    rng: np.random.Generator,
    p: TestbedParams,
    bbox: tuple[float, float, float, float],
    seed: int,
) -> tuple[CellTower, ...]:
    min_lon, min_lat, max_lon, max_lat = bbox
    lons = rng.uniform(min_lon, max_lon, p.cell_tower_count)
    lats = rng.uniform(min_lat, max_lat, p.cell_tower_count)
    ranges = rng.uniform(500, 3000, p.cell_tower_count)
    return tuple(
        CellTower(id=stable_id("tow", seed, i), lon=float(lons[i]),
                  lat=float(lats[i]), range_m=float(ranges[i]),
                  status=EntityStatus.operational)
        for i in range(p.cell_tower_count))


def gen_responders(
    rng: np.random.Generator,
    p: TestbedParams,
    bbox: tuple[float, float, float, float],
    seed: int,
) -> tuple[ResponderStation, ...]:
    min_lon, min_lat, max_lon, max_lat = bbox
    teams = ["fire", "medical", "rescue", "police"]
    lons = rng.uniform(min_lon, max_lon, p.responder_station_count)
    lats = rng.uniform(min_lat, max_lat, p.responder_station_count)
    tidx = rng.integers(0, len(teams), p.responder_station_count)
    caps = rng.integers(5, 20, p.responder_station_count)
    return tuple(
        ResponderStation(id=stable_id("resp", seed, i),
            lon=float(lons[i]), lat=float(lats[i]),
            team_type=str(teams[int(tidx[i])]), capacity=int(caps[i]),
            status=EntityStatus.operational)
        for i in range(p.responder_station_count))


def gen_citizens(
    rng: np.random.Generator,
    p: TestbedParams,
    bbox: tuple[float, float, float, float],
    seed: int,
) -> tuple[CitizenDevice, ...]:
    min_lon, min_lat, max_lon, max_lat = bbox
    dtypes = ["android", "ios", "feature_phone"]
    lons = rng.uniform(min_lon, max_lon, p.citizen_device_count)
    lats = rng.uniform(min_lat, max_lat, p.citizen_device_count)
    didx = rng.integers(0, len(dtypes), p.citizen_device_count)
    batts = rng.uniform(5, 100, p.citizen_device_count)
    return tuple(
        CitizenDevice(id=stable_id("dev", seed, i),
            lon=float(lons[i]), lat=float(lats[i]),
            device_type=str(dtypes[int(didx[i])]), battery_pct=float(batts[i]))
        for i in range(p.citizen_device_count))


__all__ = [
    "elev_at",
    "gen_buildings",
    "gen_cell_towers",
    "gen_citizens",
    "gen_hospitals",
    "gen_population",
    "gen_responders",
    "gen_roads",
    "gen_shelters",
    "gen_substations",
    "gen_terrain",
]
