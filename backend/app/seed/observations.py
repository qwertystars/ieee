"""Observation seeder — creates 50 observations from fixture files and
generated citizen/official reports.

Sources:
  - 3 CAP alerts (official_feed) from cap_alerts/*.xml
  - 17 SensorThings observations (sensor) from sensorthings/*.json
  - 3 STAC items (satellite) from stac_items/*.json
  - 15 citizen reports (citizen_report) — generated
  - 12 official reports (official_feed) — generated
Total: 50 observations
"""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.lib.time import from_iso
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation
from app.seed.ids import INCIDENT_ID, ORG_ID, seed_id

_FIXTURES = Path(__file__).parent / "fixtures"
_BASE_TS = 1753000000000  # 2026-07-20T00:00:00Z


def _hash(data: str) -> str:
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def _obs(db: Session, key: str, event_type: str, phenomenon: str,
         lon: float, lat: float, observed_at: int, source_id: str,
         source_type: SourceType, collection_method: str,
         value: float | None = None, unit: str | None = None,
         reliability: float = 0.8, uncertainty: float = 50.0,
         access: AccessPolicy = AccessPolicy.internal,
         corroboration: CorroborationState = CorroborationState.uncorroborated,
         model_version: str | None = None) -> None:
    """Create and add a single Observation with deterministic ID."""
    db.add(Observation(
        observation_id=seed_id(f"obs:{key}"),
        event_type=event_type,
        phenomenon=phenomenon,
        value=value,
        unit=unit,
        geometry=WKTElement(f"POINT({lon} {lat})", srid=4326),
        geometry_uncertainty=uncertainty,
        observed_at=observed_at,
        valid_from=observed_at,
        received_at=observed_at + 1000,
        source_id=source_id,
        source_type=source_type,
        collection_method=collection_method,
        source_reliability=reliability,
        freshness=0.95,
        corroboration_state=corroboration,
        model_uncertainty=None,
        quality_flags={"seed": True},
        access_policy=access,
        provenance_chain={"source": "seed_demo", "fixture": key},
        raw_data_hash=_hash(key),
        model_version=model_version,
        org_id=ORG_ID,
        incident_id=INCIDENT_ID,
    ))


def _parse_cap(db: Session) -> int:
    """Parse CAP XML fixtures and create observations."""
    count = 0
    for xml_file in sorted((_FIXTURES / "cap_alerts").glob("*.xml")):
        tree = ET.parse(xml_file)
        root = tree.getroot()
        ns = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}
        info = root.find("cap:info", ns)
        if info is None:
            continue
        event = info.findtext("cap:event", default="alert", namespaces=ns)
        severity = info.findtext("cap:severity", default="Minor", namespaces=ns)
        area = info.find("cap:area", ns)
        polygon_text = area.findtext("cap:polygon", default="", namespaces=ns) if area else ""
        if not polygon_text:
            continue
        # Use first point of polygon as observation location
        first_pair = polygon_text.split()[0].split(",")
        lat, lon = float(first_pair[0]), float(first_pair[1])
        sent = root.findtext("cap:sent", default="2026-07-20T00:00:00Z", namespaces=ns)
        observed_at = from_iso(sent)
        access = (AccessPolicy.sensitive if severity in ("Extreme", "Severe")
                  else AccessPolicy.internal)
        _obs(db, f"cap:{xml_file.stem}", "alert", event.lower().replace(" ", "_"),
             lon, lat, observed_at, f"cap:{xml_file.stem}",
             SourceType.official_feed, "cap_xml",
             value=None, unit=None, reliability=0.95, uncertainty=500.0,
             access=access, corroboration=CorroborationState.uncorroborated)
        count += 1
    db.commit()
    return count


def _parse_sensorthings(db: Session) -> int:
    """Parse SensorThings JSON fixtures and create observations."""
    count = 0
    for json_file in sorted((_FIXTURES / "sensorthings").glob("*.json")):
        with open(json_file) as f:
            data = json.load(f)
        for item in data["value"]:
            obs_id = item["@iot.id"]
            result = item["result"]
            ds = item.get("Datastream", {})
            ds_name = ds.get("name", json_file.stem)
            unit_obj = ds.get("unitOfMeasurement", {})
            unit = unit_obj.get("symbol", "")
            foi = item.get("FeatureOfInterest", {})
            feature = foi.get("feature", {})
            coords = feature.get("coordinates", [72.877, 19.076])
            lon, lat = coords[0], coords[1]
            pt = item["phenomenonTime"]
            observed_at = from_iso(pt)
            # Determine phenomenon from datastream name
            name_lower = ds_name.lower()
            if "rain" in name_lower:
                phenomenon, event_type = "rainfall_rate", "rainfall"
            elif "water" in name_lower or "tide" in name_lower:
                phenomenon, event_type = "water_level", "flood"
            elif "wind" in name_lower:
                phenomenon, event_type = "wind_speed", "weather"
            elif "pressure" in name_lower:
                phenomenon, event_type = "atmospheric_pressure", "weather"
            else:
                phenomenon, event_type = "sensor_reading", "sensor"
            key = f"st:{json_file.stem}:{obs_id}:{ds.get('@iot.id', ds_name)}:{pt}"
            _obs(db, key, event_type, phenomenon, lon, lat, observed_at,
                 f"sensorthings:{obs_id}", SourceType.sensor, "sensorthings_api",
                 value=float(result), unit=unit, reliability=0.92,
                 uncertainty=10.0, access=AccessPolicy.internal)
            count += 1
    db.commit()
    return count


def _parse_stac(db: Session) -> int:
    """Parse STAC item fixtures and create observations."""
    count = 0
    for json_file in sorted((_FIXTURES / "stac_items").glob("*.json")):
        if json_file.name == "collection.json":
            continue
        with open(json_file) as f:
            item = json.load(f)
        bbox = item["bbox"]
        lon = (bbox[0] + bbox[2]) / 2
        lat = (bbox[1] + bbox[3]) / 2
        props = item.get("properties", {})
        dt = props.get("datetime", "2026-07-20T04:30:00Z")
        observed_at = from_iso(dt)
        platform = props.get("platform", "sentinel-1a")
        constellation = props.get("constellation", "sentinel-1")
        _obs(db, f"stac:{json_file.stem}", "satellite_imagery", constellation,
             lon, lat, observed_at, f"stac:{item['id']}",
             SourceType.satellite, "stac_api",
             value=None, unit=None, reliability=0.9, uncertainty=100.0,
             access=AccessPolicy.internal,
             corroboration=CorroborationState.uncorroborated,
             model_version=f"{platform}:1.0")
        count += 1
    db.commit()
    return count


def _gen_citizen_reports(db: Session) -> int:
    """Generate 15 citizen report observations."""
    reports = [
        ("flood", "water_level", 72.870, 19.072, 1.5, "m", "Water on Main Street"),
        ("flood", "water_level", 72.875, 19.068, 2.0, "m", "Bridge BR-04 underwater"),
        ("road", "road_passability", 72.872, 19.070, 0.0, "bool", "Coastal Highway impassable"),
        ("flood", "water_level", 72.880, 19.065, 0.8, "m", "Water entering homes Ward 2"),
        ("rescue", "rescue_request", 72.868, 19.075, None, None, "Family trapped on rooftop"),
        ("flood", "water_level", 72.885, 19.060, 1.2, "m", "Beach Road flooded"),
        ("power", "power_outage", 72.872, 19.068, 1.0, "bool", "Power out in Ward 2"),
        ("road", "road_passability", 72.878, 19.076, 1.0, "bool", "Hospital Road passable"),
        ("rescue", "rescue_request", 72.890, 19.058, None, None, "Need boat evacuation Ward 1"),
        ("flood", "water_level", 72.865, 19.080, 0.3, "m", "Minor flooding Ward 3"),
        ("communication", "network_status", 72.874, 19.070, 0.0, "bool", "Cell tower down Ward 2"),
        ("shelter", "shelter_capacity", 72.878, 19.076, 1.0, "bool", "Shelter ST-01 accepting people"),
        ("road", "road_passability", 72.882, 19.088, 1.0, "bool", "Hill Road passable"),
        ("flood", "water_level", 72.870, 19.072, 1.8, "m", "Water rising fast near river"),
        ("medical", "medical_emergency", 72.888, 19.062, None, None, "Need ambulance at Coastal Hospital"),
    ]
    for i, (etype, phen, lon, lat, val, unit, note) in enumerate(reports):
        _obs(db, f"citizen:{i+1}", etype, phen, lon, lat,
             _BASE_TS + i * 300000,  # 5-min intervals
             f"citizen:user_{i+1:03d}", SourceType.citizen_report,
             "mobile_app", value=val, unit=unit, reliability=0.6,
             uncertainty=200.0, access=AccessPolicy.internal,
             corroboration=CorroborationState.uncorroborated)
    db.commit()
    return len(reports)


def _gen_official_reports(db: Session) -> int:
    """Generate 12 official report observations."""
    reports = [
        ("flood", "flood_extent", 72.85, 19.05, 35.0, "%", "Ward 1 35% flooded"),
        ("flood", "flood_extent", 72.87, 19.07, 28.0, "%", "Ward 2 28% flooded"),
        ("infrastructure", "bridge_status", 72.875, 19.068, 0.0, "bool", "Bridge BR-04 closed"),
        ("infrastructure", "substation_status", 72.872, 19.068, 0.0, "bool", "SS-02 offline"),
        ("infrastructure", "cell_tower_status", 72.874, 19.070, 0.0, "bool", "CT-02 offline"),
        ("evacuation", "evacuation_progress", 72.86, 19.07, 60.0, "%", "Ward 1 60% evacuated"),
        ("evacuation", "evacuation_progress", 72.88, 19.07, 45.0, "%", "Ward 2 45% evacuated"),
        ("shelter", "shelter_occupancy", 72.878, 19.076, 312, "persons", "ST-01 at 62% capacity"),
        ("shelter", "shelter_occupancy", 72.890, 19.084, 280, "persons", "ST-02 at 93% capacity"),
        ("medical", "hospital_capacity", 72.878, 19.076, 180, "beds", "General Hospital 180/200 beds"),
        ("medical", "hospital_capacity", 72.888, 19.062, 145, "beds", "Coastal Hospital 145/150 beds"),
        ("weather", "rainfall_accumulation", 72.877, 19.076, 180.0, "mm", "180mm rainfall in 6h"),
    ]
    for i, (etype, phen, lon, lat, val, unit, note) in enumerate(reports):
        _obs(db, f"official:{i+1}", etype, phen, lon, lat,
             _BASE_TS + i * 600000,  # 10-min intervals
             f"official:agency_{i+1:02d}", SourceType.official_feed,
             "official_report", value=val, unit=unit, reliability=0.9,
             uncertainty=100.0, access=AccessPolicy.internal,
             corroboration=CorroborationState.corroborated if i < 6
             else CorroborationState.uncorroborated)
    db.commit()
    return len(reports)


def seed_observations(db: Session) -> int:
    """Create all 50 observations from fixtures and generated data."""
    total = 0
    total += _parse_cap(db)
    total += _parse_sensorthings(db)
    total += _parse_stac(db)
    total += _gen_citizen_reports(db)
    total += _gen_official_reports(db)
    return total
