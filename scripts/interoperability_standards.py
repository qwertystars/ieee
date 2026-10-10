from __future__ import annotations

import base64
import binascii
import re
import struct
from datetime import datetime
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from scripts.interoperability_contract import (
    JsonObject,
    JsonValue,
    canonical,
    metadata,
    text,
    timestamp,
)

OGC_URIS: Final = {
    "core": "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "crs": "http://www.opengis.net/spec/ogcapi-features-2/1.0/conf/crs",
    "query": "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/query",
}
UCUM_RE: Final = re.compile(r"^[A-Za-z%0-9./()*^{}+-]+$")
CAP_REQUIRED: Final = ("identifier", "sender", "sent", "status", "msgType", "scope")


def _links(value: JsonValue, label: str, findings: list[str], required: set[str]) -> None:
    if not isinstance(value, list):
        findings.append(f"{label} must be an array")
        return
    rels = {item.get("rel") for item in value if isinstance(item, dict)}
    for rel in required - rels:
        findings.append(f"{label} is missing rel={rel}")
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("href"), str) and not item["href"].startswith("https://"):
            findings.append(f"{label} contains a non-HTTPS link")


def _ulid_bytes(value: str) -> bytes:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    if len(value) != 26 or any(char not in alphabet for char in value):
        raise ValueError("nonce must be a ULID")
    number = 0
    for char in value:
        number = number * 32 + alphabet.index(char)
    if number >= 1 << 128:
        raise ValueError("nonce exceeds ULID range")
    return number.to_bytes(16, "big")


def _signatures(record: JsonObject, label: str, findings: list[str]) -> None:
    approvals = record.get("approvals")
    now_ms = record.get("now_ms")
    payload = record.get("signature_payload")
    if not isinstance(approvals, list) or len(approvals) != 2 or not isinstance(now_ms, int) or not isinstance(payload, dict):
        findings.append(f"{label} requires exactly two Ed25519 approvals")
        return
    roles: set[str] = set()
    users: set[str] = set()
    nonces: set[str] = set()
    for index, value in enumerate(approvals):
        approval_label = f"{label}.approvals[{index}]"
        if not isinstance(value, dict):
            findings.append(f"{approval_label} must be an object")
            continue
        required = {"user_id", "role", "key_id", "public_key", "nonce", "signed_at_ms", "expires_at_ms", "signature", "payload", "revoked"}
        if set(value) != required:
            findings.append(f"{approval_label} has incomplete signature fields")
            continue
        role = value.get("role")
        user = value.get("user_id")
        nonce = value.get("nonce")
        if role not in {"emergency_manager", "responder_coordinator"} or not isinstance(user, str) or not isinstance(nonce, str):
            findings.append(f"{approval_label} has an invalid approver identity")
            continue
        roles.add(role)
        users.add(user)
        if nonce in nonces:
            findings.append(f"{label} reuses an approval nonce")
        nonces.add(nonce)
        signed_at = value.get("signed_at_ms")
        expires_at = value.get("expires_at_ms")
        if not isinstance(signed_at, int) or not isinstance(expires_at, int) or signed_at > now_ms + 30_000 or now_ms - signed_at > 300_000 or expires_at < now_ms or expires_at - signed_at > 300_000:
            findings.append(f"{approval_label} is outside the freshness or clock-skew window")
            continue
        if value.get("revoked") is not False or value.get("payload") != payload:
            findings.append(f"{approval_label} is revoked or signs a different payload")
            continue
        try:
            public_key = base64.b64decode(value["public_key"], validate=True)
            signature = base64.b64decode(value["signature"], validate=True)
            signed_bytes = canonical(payload)
            framed = b"RESQNET-SIG-V1" + struct.pack(">I", len(signed_bytes)) + signed_bytes + _ulid_bytes(nonce) + struct.pack(">Q", expires_at)
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, framed)
        except (ValueError, TypeError, struct.error, binascii.Error, InvalidSignature):
            findings.append(f"{approval_label} Ed25519 verification failed")
    if roles != {"emergency_manager", "responder_coordinator"} or len(users) != 2:
        findings.append(f"{label} requires distinct emergency_manager and responder_coordinator approvals")


def _cap_message(raw: JsonObject, index: int, previous: dict[tuple[str, str, str], datetime], findings: list[str]) -> None:
    label = f"cap.messages[{index}]"
    for field in CAP_REQUIRED:
        text(raw.get(field), f"{label}.{field}", findings)
    identifier, sender = raw.get("identifier"), raw.get("sender")
    sent = timestamp(raw.get("sent"), f"{label}.sent", findings)
    message_type = raw.get("msgType")
    if raw.get("status") not in {"Actual", "Exercise", "System", "Test", "Draft"}:
        findings.append(f"{label}.status is not a CAP 1.2 value")
    if message_type not in {"Alert", "Update", "Cancel", "Ack", "Error"}:
        findings.append(f"{label}.msgType is not a CAP 1.2 value")
    if raw.get("scope") not in {"Public", "Restricted", "Private"}:
        findings.append(f"{label}.scope is not a CAP 1.2 value")
    if raw.get("code") != "IPAWSv1.0":
        findings.append(f"{label}.code must include IPAWSv1.0")
    info = raw.get("info")
    if not isinstance(info, dict):
        findings.append(f"{label}.info is required")
    else:
        for field in ("category", "event", "urgency", "severity", "certainty", "headline", "description", "expires"):
            text(info.get(field), f"{label}.info.{field}", findings)
        if info.get("area") is None:
            findings.append(f"{label}.info.area is required")
        event_code = info.get("eventCode")
        if not isinstance(event_code, dict) or event_code.get("valueName") != "SAME" or not isinstance(event_code.get("value"), str):
            findings.append(f"{label}.info.eventCode must provide SAME")
    references = raw.get("references")
    if message_type in {"Update", "Cancel"}:
        if not isinstance(references, str) or len(references.split(",")) != 3:
            findings.append(f"{label} requires sender,identifier,sent references")
        else:
            ref = references.split(",")
            ref_sent = timestamp(ref[2], f"{label}.references.sent", findings)
            if ref[:2] != [sender, identifier]:
                findings.append(f"{label} must reuse sender and identifier from its reference")
            if (ref[0], ref[1], ref[2]) not in previous:
                findings.append(f"{label} references a missing or stale CAP message")
            if sent is not None and ref_sent is not None and sent <= ref_sent:
                findings.append(f"{label}.sent must supersede its referenced message")
    if isinstance(sender, str) and isinstance(identifier, str) and isinstance(sent, datetime) and isinstance(raw.get("sent"), str):
        previous[(sender, identifier, raw["sent"])] = sent
    metadata(raw, label, findings)
    if message_type == "Cancel":
        _signatures(raw, label, findings)


def validate_cap(record: JsonObject, findings: list[str]) -> None:
    """Validate CAP 1.2 and the FEMA IPAWS Profile 1.0 fixture shape."""
    messages = record.get("messages")
    if record.get("profile") != "FEMA IPAWS CAP Profile 1.0" or not isinstance(messages, list) or not messages:
        findings.append("CAP fixture must declare FEMA IPAWS CAP Profile 1.0 and messages")
        return
    previous: dict[tuple[str, str, str], datetime] = {}
    for index, message in enumerate(messages):
        if isinstance(message, dict):
            checked = dict(message)
            if "now_ms" not in checked and isinstance(record.get("now_ms"), int):
                checked["now_ms"] = record["now_ms"]
            _cap_message(checked, index, previous, findings)
        else:
            findings.append(f"cap.messages[{index}] must be an object")


def validate_ogc(record: JsonObject, findings: list[str]) -> None:
    transport = record.get("transport")
    if not isinstance(transport, dict) or transport.get("scheme") != "https" or transport.get("media_type") not in {"application/json", "application/geo+json"}:
        findings.append("OGC binding must use HTTPS JSON")
    landing = record.get("landing_page")
    if not isinstance(landing, dict):
        findings.append("OGC landing_page is required")
    else:
        conforms = landing.get("conformsTo")
        if not isinstance(conforms, list) or any(OGC_URIS[name] not in conforms for name in OGC_URIS):
            findings.append("OGC landing page must advertise Core, CRS, and Query conformance")
        _links(landing.get("links"), "OGC landing_page.links", findings, {"self", "service-desc", "conformance"})
    collections = record.get("collections")
    if not isinstance(collections, dict) or not isinstance(collections.get("collections"), list) or not collections["collections"]:
        findings.append("OGC collections response must contain collections")
    else:
        for index, collection in enumerate(collections["collections"]):
            if not isinstance(collection, dict) or not isinstance(collection.get("id"), str) or not isinstance(collection.get("title"), str):
                findings.append(f"OGC collections[{index}] must map id and title")
                continue
            crs = collection.get("crs")
            if not isinstance(crs, list) or "EPSG:4326" not in crs or collection.get("storageCrs") != "EPSG:4326":
                findings.append(f"OGC collections[{index}] must declare EPSG:4326 storage CRS")
            _links(collection.get("links"), f"OGC collections[{index}].links", findings, {"items"})
    items = record.get("items")
    if not isinstance(items, dict) or items.get("type") != "FeatureCollection" or not isinstance(items.get("features"), list):
        findings.append("OGC paging response must be a FeatureCollection")
    else:
        if items.get("crs") != "EPSG:4326":
            findings.append("OGC FeatureCollection must use EPSG:4326")
        matched, returned = items.get("numberMatched"), items.get("numberReturned")
        if not isinstance(matched, int) or not isinstance(returned, int) or returned > matched:
            findings.append("OGC paging counts are invalid")
        elif matched > returned:
            _links(items.get("links"), "OGC paging.links", findings, {"next"})
    query = record.get("query")
    if not isinstance(query, dict) or not isinstance(query.get("limit"), int) or query["limit"] < 1 or query["limit"] > 10_000 or not isinstance(query.get("bbox"), list) or len(query["bbox"]) not in {4, 6}:
        findings.append("OGC Query must provide bounded limit and four- or six-coordinate bbox")
    metadata(record, "ogc", findings)


def _entity_map(entities: JsonValue, findings: list[str]) -> dict[str, dict[str, JsonObject]]:
    if not isinstance(entities, dict):
        findings.append("SensorThings entities must be an object")
        return {}
    result: dict[str, dict[str, JsonObject]] = {}
    for kind in ("Thing", "Datastream", "Sensor", "ObservedProperty", "Observation", "FeatureOfInterest"):
        values = entities.get(kind)
        if not isinstance(values, list) or not values:
            findings.append(f"entities.{kind} must contain an entity")
            continue
        mapped: dict[str, JsonObject] = {}
        for index, item in enumerate(values):
            if not isinstance(item, dict) or not isinstance(item.get("@iot.id"), str):
                findings.append(f"entities.{kind}[{index}] requires @iot.id")
            else:
                mapped[item["@iot.id"]] = item
        result[kind] = mapped
    return result


def validate_sensor_things(record: JsonObject, findings: list[str]) -> None:
    if record.get("version") != "1.1":
        findings.append("SensorThings fixture must pin Sensing 1.1")
    transport = record.get("transport")
    if not isinstance(transport, dict) or transport.get("http") != "HTTPS+JSON" or transport.get("mqtt") != "3.1.1":
        findings.append("SensorThings bindings must pin HTTPS JSON and MQTT 3.1.1")
    mqtt = record.get("mqtt")
    if not isinstance(mqtt, dict) or not isinstance(mqtt.get("topic"), str) or not mqtt["topic"].startswith("v1.1/"):
        findings.append("SensorThings MQTT topic must use the v1.1 version prefix")
    entities = _entity_map(record.get("entities"), findings)
    thing = next(iter(entities.get("Thing", {}).values()), None)
    datastream = next(iter(entities.get("Datastream", {}).values()), None)
    observation = next(iter(entities.get("Observation", {}).values()), None)
    foi = next(iter(entities.get("FeatureOfInterest", {}).values()), None)
    if thing is not None and (not isinstance(thing.get("name"), str) or not isinstance(thing.get("description"), str)):
        findings.append("SensorThings Thing requires name and description")
    if datastream is not None:
        unit = datastream.get("unitOfMeasurement")
        symbol = unit.get("symbol") if isinstance(unit, dict) else None
        if not isinstance(unit, dict) or not isinstance(symbol, str) or not symbol or " " in symbol or UCUM_RE.fullmatch(symbol) is None or not all(isinstance(unit.get(field), str) for field in ("name", "definition")):
            findings.append("SensorThings Datastream requires a syntactically valid UCUM unit")
        for relation in ("Thing", "Sensor", "ObservedProperty"):
            if not isinstance(datastream.get(relation), dict) or not isinstance(datastream[relation].get("@iot.id"), str):
                findings.append(f"SensorThings Datastream must map {relation}")
    if observation is not None:
        for relation in ("Datastream", "FeatureOfInterest"):
            if not isinstance(observation.get(relation), dict) or not isinstance(observation[relation].get("@iot.id"), str):
                findings.append(f"SensorThings Observation must map {relation}")
        timestamp(observation.get("phenomenonTime"), "SensorThings Observation.phenomenonTime", findings)
        quality = observation.get("quality")
        if not isinstance(quality, dict) or not isinstance(quality.get("quality_flag"), str) or not isinstance(quality.get("clock_offset_ms"), int) or not isinstance(quality.get("calibration_version"), str):
            findings.append("SensorThings Observation requires quality, clock, and calibration metadata")
    if foi is not None:
        feature = foi.get("feature")
        if not isinstance(feature, dict) or feature.get("type") != "Point" or not isinstance(feature.get("coordinates"), list) or len(feature["coordinates"]) != 2 or foi.get("crs") != "EPSG:4326":
            findings.append("SensorThings FeatureOfInterest must map an EPSG:4326 point")
    metadata(record, "sensorthings", findings)


def validate_offline(record: JsonObject, findings: list[str]) -> None:
    if record.get("offline_only") is not True or record.get("contracts") != ["cap", "ogc", "sensorthings"]:
        findings.append("offline fixture must enumerate CAP, OGC, and SensorThings contracts")


__all__ = ["validate_cap", "validate_offline", "validate_ogc", "validate_sensor_things"]
