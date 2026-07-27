"""CAP 1.2 adapter — parse OASIS Common Alerting Protocol alerts into Observations.

OASIS CAP 1.2 spec: https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2.html

Coordinate conventions:
  - CAP polygon:  space-delimited ``lat,lon lat,lon ...`` pairs (lat first).
  - CAP circle:   ``lat,lon radius_km`` (single pair + radius in kilometers).
  - WKT/PostGIS:  ``lon lat`` ordering (longitude first).

All alerts land as ``corroboration_state=uncorroborated`` (draft) until a human
or fusion engine confirms them. ``access_policy`` is derived from severity:
extreme/severe -> sensitive, moderate/minor/unknown -> internal.
"""

import hashlib
import xml.etree.ElementTree as ET
from typing import Any

from geoalchemy2.elements import WKTElement
from shapely.geometry import Point, Polygon
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lib.time import from_iso, now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
_N = f"{{{CAP_NS}}}"  # ElementTree namespace-aware tag prefix.

_SEVERITY_ACCESS: dict[str, AccessPolicy] = {
    "extreme": AccessPolicy.sensitive,
    "severe": AccessPolicy.sensitive,
    "moderate": AccessPolicy.internal,
    "minor": AccessPolicy.internal,
    "unknown": AccessPolicy.internal,
}

# Rough km-to-degree conversion at the equator. Sufficient for alert zones;
# the true radius is preserved in geometry_uncertainty (meters).
_KM_PER_DEGREE = 111.0


def _text(elem: ET.Element | None) -> str | None:
    """Return stripped text of an Element, or None if missing/empty."""
    if elem is None:
        return None
    t = (elem.text or "").strip()
    return t or None


def _parse_polygon(raw: str) -> str:
    """CAP polygon ``lat,lon lat,lon ...`` -> WKT POLYGON ((lon lat, ...))."""
    coords: list[tuple[float, float]] = []
    for token in raw.split():
        lat_s, lon_s = token.split(",")
        coords.append((float(lon_s), float(lat_s)))  # WKT is (lon, lat)
    if not coords:
        raise ValueError("CAP polygon has no coordinate pairs")
    if coords[0] != coords[-1]:
        coords.append(coords[0])  # auto-close ring
    return Polygon(coords).wkt


def _parse_circle(raw: str) -> tuple[str, float]:
    """CAP circle ``lat,lon radius_km`` -> (WKT POLYGON, radius_km)."""
    center_s, radius_s = raw.split()
    lat_s, lon_s = center_s.split(",")
    lat, lon = float(lat_s), float(lon_s)
    radius_km = float(radius_s)
    buffered = Point(lon, lat).buffer(radius_km / _KM_PER_DEGREE)
    return buffered.wkt, radius_km


def parse_cap_alert(xml_string: str) -> dict[str, Any]:
    """Parse a CAP 1.2 XML alert into a normalized dict.

    Extracts: alert_id, sender, sent, status, msg_type, scope, event, urgency,
    severity, certainty, effective, onset, expires, headline, description,
    area_desc, geometry_wkt, geometry_uncertainty, references.

    Raises ValueError if the alert is missing <info> or has no geometry.
    """
    root = ET.fromstring(xml_string)
    info = root.find(f"{_N}info")
    if info is None:
        raise ValueError("CAP alert missing <info> element")

    area = info.find(f"{_N}area")

    # Geometry: prefer polygon, fall back to circle. Observation.geometry is
    # NOT NULL, so we require at least one.
    geometry_wkt: str | None = None
    geometry_uncertainty = 0.0
    if area is not None:
        polygon = _text(area.find(f"{_N}polygon"))
        circle = _text(area.find(f"{_N}circle"))
        if polygon:
            geometry_wkt = _parse_polygon(polygon)
        elif circle:
            geometry_wkt, radius_km = _parse_circle(circle)
            geometry_uncertainty = float(radius_km * 1000.0)  # meters
    if geometry_wkt is None:
        raise ValueError("CAP alert has no polygon or circle geometry")

    return {
        "alert_id": _text(root.find(f"{_N}identifier")),
        "sender": _text(root.find(f"{_N}sender")),
        "sent": _text(root.find(f"{_N}sent")),
        "status": _text(root.find(f"{_N}status")),
        "msg_type": _text(root.find(f"{_N}msgType")),
        "scope": _text(root.find(f"{_N}scope")),
        "event": _text(info.find(f"{_N}event")),
        "urgency": _text(info.find(f"{_N}urgency")),
        "severity": _text(info.find(f"{_N}severity")),
        "certainty": _text(info.find(f"{_N}certainty")),
        "effective": _text(info.find(f"{_N}effective")),
        "onset": _text(info.find(f"{_N}onset")),
        "expires": _text(info.find(f"{_N}expires")),
        "headline": _text(info.find(f"{_N}headline")),
        "description": _text(info.find(f"{_N}description")),
        "area_desc": _text(area.find(f"{_N}areaDesc")) if area is not None else None,
        "geometry_wkt": geometry_wkt,
        "geometry_uncertainty": geometry_uncertainty,
        "references": _text(root.find(f"{_N}references")),
    }


def _raw_hash(xml_string: str) -> str:
    return "sha256:" + hashlib.sha256(xml_string.encode("utf-8")).hexdigest()


def _source_id(parsed: dict[str, Any]) -> str:
    return f"cap:{parsed['sender']}:{parsed['alert_id']}"


def _resolve_supersedes(
    db: Session, parsed: dict[str, Any], org_id: str
) -> str | None:
    """For Update/Cancel messages, find the prior observation by reference id.

    CAP references format: ``sender,identifier,sent sender,identifier,sent ...``
    """
    if parsed["msg_type"] not in ("Update", "Cancel"):
        return None
    refs = parsed.get("references")
    if not refs:
        return None
    for token in refs.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        ref_source_id = f"cap:{parts[0]}:{parts[1]}"
        row = db.execute(
            select(Observation.observation_id).where(
                Observation.source_id == ref_source_id,
                Observation.org_id == org_id,
            )
        ).first()
        if row:
            return row[0]
    return None


def ingest_cap_alert(
    db: Session, xml_string: str, org_id: str, incident_id: str
) -> str:
    """Parse, dedup, and insert a CAP alert as an Observation.

    Idempotent: if an observation with the same ``source_id`` and
    ``raw_data_hash`` already exists, returns its observation_id without
    inserting a duplicate.

    Returns the observation_id (26-char ULID).
    """
    parsed = parse_cap_alert(xml_string)
    source_id = _source_id(parsed)
    raw_hash = _raw_hash(xml_string)

    existing = db.execute(
        select(Observation.observation_id).where(
            Observation.source_id == source_id,
            Observation.raw_data_hash == raw_hash,
            Observation.org_id == org_id,
        )
    ).first()
    if existing:
        return existing[0]

    severity_lower = (parsed["severity"] or "unknown").lower()
    access_policy = _SEVERITY_ACCESS.get(severity_lower, AccessPolicy.internal)

    sent_ms = from_iso(parsed["sent"]) if parsed["sent"] else now_ms()
    effective_ms = (
        from_iso(parsed["effective"]) if parsed["effective"] else sent_ms
    )
    expires_ms = from_iso(parsed["expires"]) if parsed["expires"] else None

    supersedes = _resolve_supersedes(db, parsed, org_id)

    obs = Observation(
        observation_id=generate_ulid(),
        event_type="official_alert",
        phenomenon=parsed["event"] or "unknown",
        value=None,
        unit=None,
        geometry=WKTElement(parsed["geometry_wkt"], srid=4326),
        geometry_uncertainty=parsed["geometry_uncertainty"],
        observed_at=sent_ms,
        valid_from=effective_ms,
        valid_until=expires_ms,
        received_at=now_ms(),
        source_id=source_id,
        source_type=SourceType.official_feed,
        collection_method="cap_xml",
        source_reliability=0.95,
        freshness=1.0,
        corroboration_state=CorroborationState.uncorroborated,
        model_uncertainty=None,
        quality_flags={
            "cap_status": parsed["status"],
            "cap_msg_type": parsed["msg_type"],
            "cap_scope": parsed["scope"],
            "cap_urgency": parsed["urgency"],
            "cap_severity": parsed["severity"],
            "cap_certainty": parsed["certainty"],
            "cap_headline": parsed["headline"],
            "cap_area_desc": parsed["area_desc"],
        },
        access_policy=access_policy,
        provenance_chain={
            "cap_sender": parsed["sender"],
            "cap_identifier": parsed["alert_id"],
            "cap_sent": parsed["sent"],
            "cap_references": parsed["references"],
        },
        raw_data_hash=raw_hash,
        model_version=None,
        supersedes=supersedes,
        duplicate_group=None,
        org_id=org_id,
        incident_id=incident_id,
    )
    db.add(obs)
    db.commit()
    db.refresh(obs)
    return obs.observation_id


__all__ = ["ingest_cap_alert", "parse_cap_alert"]
