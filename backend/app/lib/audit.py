"""Hash-chained append-only audit log.

Each event's `hash` is sha256(prev_hash + canonical_json(payload)). Tampering
with any row breaks the chain at that point; `verify_chain` reports the index
of the first mismatch (or True if the whole chain is intact).
"""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.events import Event


def _canonical_payload(
    actor: str,
    action: str,
    entity: str,
    before: dict | None,
    after: dict | None,
    ts: int,
) -> str:
    """Canonical JSON serialization of the audit payload.

    `sort_keys=True` guarantees byte-stable hashing regardless of dict order.
    `default=str` covers any non-JSON-native values (datetimes, enums, etc.).
    """
    return json.dumps(
        {
            "actor": actor,
            "action": action,
            "entity": entity,
            "before": before,
            "after": after,
            "ts": ts,
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def _compute_hash(prev_hash: str, payload: str) -> str:
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


def write_audit(
    db: Session,
    org_id: str,
    incident_id: str,
    actor: str,
    action: str,
    entity: str,
    before: dict | None = None,
    after: dict | None = None,
) -> Event:
    """Append an event to the hash-chained audit log.

    1. Look up the last event's hash for this org_id (empty string if none).
    2. Build the canonical payload and compute sha256(prev_hash + payload).
    3. Insert the Event row, commit, and return it.
    """
    last = db.execute(
        select(Event.hash)
        .where(Event.org_id == org_id)
        .order_by(Event.ts.desc(), Event.id.desc())
        .limit(1)
    ).first()
    prev_hash = last[0] if last else ""

    ts = now_ms()
    payload = _canonical_payload(actor, action, entity, before, after, ts)
    h = _compute_hash(prev_hash, payload)

    event = Event(
        id=generate_ulid(),
        org_id=org_id,
        incident_id=incident_id,
        actor=actor,
        action=action,
        entity=entity,
        before=before,
        after=after,
        ts=ts,
        prev_hash=prev_hash,
        hash=h,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def verify_chain(db: Session, org_id: str) -> bool | int:
    """Verify the audit chain for an org.

    Returns True if every event's hash matches the recomputed value.
    Returns the 0-based index of the first mismatched event otherwise.
    """
    rows = db.execute(
        select(Event).where(Event.org_id == org_id).order_by(Event.ts, Event.id)
    ).scalars().all()

    prev_hash = ""
    for i, ev in enumerate(rows):
        payload = _canonical_payload(
            ev.actor, ev.action, ev.entity, ev.before, ev.after, ev.ts
        )
        expected = _compute_hash(prev_hash, payload)
        if ev.hash != expected:
            return i
        prev_hash = ev.hash
    return True


def write_break_glass_audit_if_outage(
    db: Session,
    org_id: str,
    incident_id: str,
    actor: str,
    entity: str,
    op: str,
) -> None:
    """Write a break-glass audit entry if Redis is unavailable (fail-open path).

    Called after a fail-open sensitive operation proceeds during a Redis
    outage. Records the break-glass decision in the hash-chained audit log.
    No-op if Redis is available (normal path, no break-glass needed).
    """
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
        before=None,
        after={"reason": "redis_outage_fail_open"},
    )


__all__ = ["verify_chain", "write_audit", "write_break_glass_audit_if_outage"]
