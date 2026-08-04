from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.lib.audit_privacy import AuditValue, pseudonymize_actor, sanitize_audit_value
from app.lib.canonical_json import canonical_json_bytes, sha256_hex
from app.lib.observability import telemetry_span
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.events import (
    LEGACY_SERIALIZATION_VERSION,
    AuditChainHead,
    Event,
)

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]

if TYPE_CHECKING:
    from app.audit.reconstruction import AuditContext


def _canonical_payload(
    actor: str,
    action: str,
    entity: str,
    before: dict | None,
    after: dict | None,
    ts: int,
) -> str:
    import json

    return json.dumps(
        {"actor": actor, "action": action, "entity": entity, "before": before, "after": after, "ts": ts},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def _compute_hash(prev_hash: str, payload: str | bytes) -> str:
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    return sha256_hex(prev_hash.encode("ascii") + payload_bytes)


def _canonical_event_bytes(event: Event) -> bytes:
    return canonical_json_bytes(
        {
            "event_id": event.id,
            "org_id": event.org_id,
            "incident_id": event.incident_id,
            "event_type": event.event_type or "audit",
            "source_id": event.source_id or event.actor,
            "external_id": event.external_id,
            "source_time_ms": event.source_time_ms if event.source_time_ms is not None else event.ts,
            "receipt_time_ms": event.receipt_time_ms if event.receipt_time_ms is not None else event.ts,
            "sequence": event.sequence,
            "actor": event.actor,
            "action": event.action,
            "entity": event.entity,
            "before": event.before,
            "after": event.after,
            "payload": event.payload,
            "provenance": event.provenance,
            "visibility": event.visibility or "internal",
            "review_status": event.review_status or "official",
            "schema_version": event.schema_version or "1.0",
            "serialization_version": event.serialization_version,
        }
    )


def _audit_provenance(
    provenance: dict | None,
    audit_context: AuditContext | None,
    timestamp: int,
) -> dict:
    safe_value = sanitize_audit_value(provenance or {})
    safe: dict[str, AuditValue]
    if isinstance(safe_value, dict):
        safe = safe_value
    else:
        safe = {}
    retention: dict[str, AuditValue] = {
        "retention_until_ms": timestamp + 7 * 366 * 86_400_000,
        "legal_retention_reason": "immutable_audit_retention",
    }
    if audit_context is not None:
        retention.update(audit_context.as_mapping())
    safe["audit"] = retention
    return safe


def _last_event(db: Session, org_id: str) -> Event | None:
    return db.execute(
        select(Event)
        .where(Event.org_id == org_id)
        .order_by(func.coalesce(Event.sequence, 0).desc(), Event.ts.desc(), Event.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def write_audit(
    db: Session,
    org_id: str,
    incident_id: str,
    actor: str,
    action: str,
    entity: str,
    before: dict | None = None,
    after: dict | None = None,
    *,
    event_type: str = "audit",
    source_id: str | None = None,
    external_id: str | None = None,
    source_time_ms: int | None = None,
    visibility: str = "internal",
    review_status: str = "official",
    provenance: dict | None = None,
    audit_context: AuditContext | None = None,
) -> Event:
    head = db.execute(
        select(AuditChainHead).where(AuditChainHead.org_id == org_id).with_for_update()
    ).scalar_one_or_none()
    last = _last_event(db, org_id)
    if last is None:
        previous_hash = ""
        sequence = 1
        if head is not None:
            head.last_sequence = 0
            head.last_hash = ""
    elif head is None:
        previous_hash = last.hash
        sequence = (last.sequence or 0) + 1
        head = AuditChainHead(
            org_id=org_id,
            last_sequence=last.sequence or sequence - 1,
            last_hash=last.hash,
            updated_at=now_ms(),
        )
        db.add(head)
    else:
        previous_hash = head.last_hash
        sequence = head.last_sequence + 1
    timestamp = now_ms()
    safe_before = sanitize_audit_value(before)
    safe_after = sanitize_audit_value(after)
    if not isinstance(safe_before, dict):
        safe_before = {}
    if not isinstance(safe_after, dict):
        safe_after = {}
    event = Event(
        id=generate_ulid(),
        org_id=org_id,
        incident_id=incident_id,
        actor=pseudonymize_actor(actor),
        action=action,
        entity=pseudonymize_actor(entity),
        before=safe_before,
        after=safe_after,
        ts=timestamp,
        prev_hash=previous_hash,
        event_type=event_type,
        source_id=pseudonymize_actor(source_id) if source_id else pseudonymize_actor(actor),
        external_id=pseudonymize_actor(external_id) if external_id else None,
        source_time_ms=source_time_ms if source_time_ms is not None else timestamp,
        receipt_time_ms=timestamp,
        sequence=sequence,
        payload={"before": safe_before, "after": safe_after},
        provenance=_audit_provenance(provenance, audit_context, timestamp),
        visibility=visibility,
        review_status=review_status,
        schema_version="1.0",
        serialization_version="rfc8785-v2",
        hash="",
    )
    event.hash = _compute_hash(previous_hash, _canonical_event_bytes(event))
    if head is None:
        head = AuditChainHead(org_id=org_id, last_sequence=sequence, last_hash=event.hash, updated_at=timestamp)
        db.add(head)
    else:
        head.last_sequence = sequence
        head.last_hash = event.hash
        head.updated_at = timestamp
    db.add(event)
    with telemetry_span("audit.write", {"action": action}):
        db.commit()
    db.refresh(event)
    return event


def write_security_denial(
    db: Session,
    *,
    org_id: str,
    incident_id: str,
    actor: str,
    action: str,
    entity: str,
    reason_code: str,
) -> Event:
    """Persist a denial after clearing any uncommitted command state."""
    db.rollback()
    return write_audit(
        db,
        org_id=org_id,
        incident_id=incident_id,
        actor=actor,
        action=f"security.denied.{action}",
        entity=entity,
        after={"reason_code": reason_code, "effect": "none"},
    )


def verify_chain(db: Session, org_id: str) -> bool | int:
    rows = db.execute(
        select(Event).where(Event.org_id == org_id).order_by(Event.sequence, Event.ts, Event.id)
    ).scalars().all()
    head = db.get(AuditChainHead, org_id)
    if not rows:
        return True if head is None or (head.last_sequence == 0 and head.last_hash == "") else 0
    if head is None:
        return 0
    previous_hash = ""
    for index, event in enumerate(rows):
        if event.sequence != index + 1 or (event.prev_hash or "") != previous_hash:
            return index
        if event.serialization_version == LEGACY_SERIALIZATION_VERSION or event.serialization_version is None:
            payload = _canonical_payload(event.actor, event.action, event.entity, event.before, event.after, event.ts)
            expected = _compute_hash(previous_hash, payload)
        else:
            expected = _compute_hash(previous_hash, _canonical_event_bytes(event))
        if event.hash != expected:
            return index
        previous_hash = event.hash
    if head.last_sequence != len(rows) or head.last_hash != previous_hash:
        return len(rows)
    return True


def write_break_glass_audit_if_outage(
    db: Session,
    org_id: str,
    incident_id: str,
    actor: str,
    entity: str,
    op: str,
) -> None:
    from app.deps import get_redis

    if get_redis() is not None:
        return
    write_audit(
        db,
        org_id=org_id,
        incident_id=incident_id,
        actor=actor,
        action=f"break_glass_{op}",
        entity=entity,
        after={"reason": "redis_outage_fail_open"},
    )


__all__ = [
    "canonical_json_bytes",
    "sha256_hex",
    "verify_chain",
    "write_audit",
    "write_break_glass_audit_if_outage",
    "write_security_denial",
]
