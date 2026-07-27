"""Entity seeder — creates zones, roads, shelters, hospitals, buildings,
substations, cell towers, responders, vehicles from GeoJSON fixtures.

Each entity gets a deterministic ID via seed_id(entity_type + feature_id).
All entities are scoped to the demo org_id and incident_id.
"""

import json
from pathlib import Path

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.models.entities import (
    Building,
    CellTower,
    Hospital,
    PowerSubstation,
    Responder,
    RoadSegment,
    Sensor,
    Shelter,
    Vehicle,
    Zone,
)
from app.seed.ids import (
    INCIDENT_ID,
    ORG_ID,
    RESCUE_BALL_DEVICE_1_ID,
    RESCUE_BALL_DEVICE_2_ID,
    seed_id,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "geojson"


def _load_geojson(name: str) -> list[dict]:
    """Load a GeoJSON FeatureCollection from the fixtures directory."""
    path = _FIXTURES_DIR / name
    with open(path) as f:
        data = json.load(f)
    return data["features"]


def _geom_to_wkt(geom: dict) -> WKTElement:
    """Convert a GeoJSON geometry dict to a WKTElement (srid=4326)."""
    gtype = geom["type"]
    if gtype == "Point":
        lon, lat = geom["coordinates"]
        return WKTElement(f"POINT({lon} {lat})", srid=4326)
    if gtype == "LineString":
        coords = ", ".join(f"{c[0]} {c[1]}" for c in geom["coordinates"])
        return WKTElement(f"LINESTRING({coords})", srid=4326)
    if gtype == "Polygon":
        ring = geom["coordinates"][0]
        coords = ", ".join(f"{c[0]} {c[1]}" for c in ring)
        return WKTElement(f"POLYGON(({coords}))", srid=4326)
    raise ValueError(f"Unsupported geometry type: {gtype}")


def _ts() -> int:
    return now_ms()


def seed_zones(db: Session) -> int:
    """Create 5 zones (wards) from zones.geojson."""
    features = _load_geojson("zones.geojson")
    for feat in features:
        base = feat["properties"]
        props = {**base, **_ZONE_DEMOGRAPHICS.get(base.get("name", ""), {})}
        db.add(Zone(
            id=seed_id(f"zone:{feat['id']}"),
            org_id=ORG_ID,
            incident_id=INCIDENT_ID,
            name=props["name"],
            zone_type=props["zone_type"],
            geometry=_geom_to_wkt(feat["geometry"]),
            properties=props,
            created_at=_ts(),
            updated_at=_ts(),
        ))
    db.commit()
    return len(features)


_ZONE_DEMOGRAPHICS = {
    "Ward-1-Coastal": {"vulnerable_population": 9000, "median_age": 34, "households": 11000, "density_per_sqkm": 4500},
    "Ward-2-Riverside": {"vulnerable_population": 7600, "median_age": 36, "households": 9500, "density_per_sqkm": 3800},
    "Ward-3-Lowland": {"vulnerable_population": 10400, "median_age": 33, "households": 13000, "density_per_sqkm": 5200},
    "Ward-4-Uptown": {"vulnerable_population": 6100, "median_age": 38, "households": 15000, "density_per_sqkm": 6100},
    "Ward-5-Industrial": {"vulnerable_population": 2800, "median_age": 41, "households": 7000, "density_per_sqkm": 2800},
}


def seed_roads(db: Session) -> int:
    """Create 20 road segments from roads.geojson."""
    features = _load_geojson("roads.geojson")
    for feat in features:
        props = feat["properties"]
        db.add(RoadSegment(
            id=seed_id(f"road:{feat['id']}"),
            org_id=ORG_ID,
            incident_id=INCIDENT_ID,
            name=props["name"],
            status=props["status"],
            geometry=_geom_to_wkt(feat["geometry"]),
            properties=props,
            created_at=_ts(),
            updated_at=_ts(),
        ))
    db.commit()
    return len(features)


def seed_shelters(db: Session) -> int:
    """Create 3 shelters from shelters.geojson."""
    features = _load_geojson("shelters.geojson")
    for feat in features:
        props = feat["properties"]
        db.add(Shelter(
            id=seed_id(f"shelter:{feat['id']}"),
            org_id=ORG_ID,
            incident_id=INCIDENT_ID,
            name=props["name"],
            status=props["status"],
            capacity=props["capacity"],
            occupancy=props["occupancy"],
            geometry=_geom_to_wkt(feat["geometry"]),
            properties=props,
            created_at=_ts(),
            updated_at=_ts(),
        ))
    db.commit()
    return len(features)


def seed_hospitals(db: Session) -> int:
    """Create 2 hospitals from hospitals.geojson."""
    features = _load_geojson("hospitals.geojson")
    for feat in features:
        props = feat["properties"]
        db.add(Hospital(
            id=seed_id(f"hospital:{feat['id']}"),
            org_id=ORG_ID,
            incident_id=INCIDENT_ID,
            name=props["name"],
            status=props["status"],
            capacity=props["capacity"],
            geometry=_geom_to_wkt(feat["geometry"]),
            properties=props,
            created_at=_ts(),
            updated_at=_ts(),
        ))
    db.commit()
    return len(features)


def seed_buildings(db: Session) -> int:
    """Create 10 buildings from buildings.geojson."""
    features = _load_geojson("buildings.geojson")
    for feat in features:
        props = feat["properties"]
        db.add(Building(
            id=seed_id(f"building:{feat['id']}"),
            org_id=ORG_ID,
            incident_id=INCIDENT_ID,
            name=props["name"],
            building_type=props["building_type"],
            geometry=_geom_to_wkt(feat["geometry"]),
            properties=props,
            created_at=_ts(),
            updated_at=_ts(),
        ))
    db.commit()
    return len(features)


def seed_infrastructure(db: Session) -> tuple[int, int]:
    """Create substations and cell towers from GeoJSON fixtures."""
    subs = _load_geojson("substations.geojson")
    for feat in subs:
        props = feat["properties"]
        db.add(PowerSubstation(
            id=seed_id(f"substation:{feat['id']}"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            name=props["name"], status=props["status"],
            geometry=_geom_to_wkt(feat["geometry"]),
            properties=props, created_at=_ts(), updated_at=_ts(),
        ))
    towers = _load_geojson("cell_towers.geojson")
    for feat in towers:
        props = feat["properties"]
        db.add(CellTower(
            id=seed_id(f"cell_tower:{feat['id']}"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            name=props["name"], status=props["status"],
            geometry=_geom_to_wkt(feat["geometry"]),
            properties=props, created_at=_ts(), updated_at=_ts(),
        ))
    db.commit()
    return len(subs), len(towers)


def seed_responders(db: Session) -> int:
    """Create 5 responders with roles and point locations."""
    responders = [
        ("Aarav Sharma", "team_lead", "active", 72.877, 19.076),
        ("Priya Patel", "medic", "active", 72.872, 19.068),
        ("Rohan Mehta", "engineer", "active", 72.886, 19.058),
        ("Ananya Singh", "rescuer", "active", 72.882, 19.088),
        ("Vikram Reddy", "driver", "available", 72.878, 19.072),
    ]
    for i, (name, role, status, lon, lat) in enumerate(responders):
        db.add(Responder(
            id=seed_id(f"responder:{i+1}"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            name=name, role=role, status=status,
            geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
            properties={"badge": f"R-{i+1:03d}"},
            created_at=_ts(), updated_at=_ts(),
        ))
    db.commit()
    return len(responders)


def seed_vehicles(db: Session) -> int:
    """Create 3 vehicles: boat, ambulance, high-clearance."""
    vehicles = [
        ("Boat-01", "boat", "active", 72.875, 19.068),
        ("AMB-01", "ambulance", "active", 72.878, 19.076),
        ("HCV-01", "high_clearance_vehicle", "active", 72.882, 19.088),
    ]
    for i, (name, vtype, status, lon, lat) in enumerate(vehicles):
        db.add(Vehicle(
            id=seed_id(f"vehicle:{i+1}"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            name=name, vehicle_type=vtype, status=status,
            geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
            properties={"fuel_pct": 80 - i * 10},
            created_at=_ts(), updated_at=_ts(),
        ))
    db.commit()
    return len(vehicles)


def seed_rescue_ball_devices(db: Session) -> int:
    """Create 2 simulated rescue-ball devices as Sensor rows."""
    devices = [
        (RESCUE_BALL_DEVICE_1_ID, "Rescue-Ball-01", 72.872, 19.070),
        (RESCUE_BALL_DEVICE_2_ID, "Rescue-Ball-02", 72.885, 19.065),
    ]
    for dev_id, name, lon, lat in devices:
        db.add(Sensor(
            id=dev_id,
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            name=name, sensor_type="rescue_ball", status="active",
            geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
            properties={"simulated": True, "battery_pct": 95, "firmware": "1.0.0"},
            created_at=_ts(), updated_at=_ts(),
        ))
    db.commit()
    return len(devices)
