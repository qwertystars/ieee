"""Incident reconstruction across immutable audit, command, and conflict rows."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lib.audit import JSONValue, verify_chain
from app.lib.audit_privacy import sanitize_audit_value
from app.models.alert import CommandApproval
from app.models.events import Event
from app.realtime.sync import SyncConflict


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Stable provenance fields attached to an immutable audit event."""

    actor_id: str | None = None
    agency_id: str | None = None
    device_id: str | None = None
    auth_method: str | None = None
    source_id: str | None = None
    derivation: tuple[str, ...] = ()
    signature_hash: str | None = None
    payload_hash: str | None = None
    retention_until_ms: int | None = None
    legal_retention_reason: str | None = None

    def as_mapping(self) -> dict[str, JSONValue]:
        """Return only non-empty context fields for the canonical record."""
        values: dict[str, JSONValue] = {
            "actor_id": self.actor_id,
            "agency_id": self.agency_id,
            "device_id": self.device_id,
            "auth_method": self.auth_method,
            "source_id": self.source_id,
            "derivation": list(self.derivation),
            "signature_hash": self.signature_hash,
            "payload_hash": self.payload_hash,
            "retention_until_ms": self.retention_until_ms,
            "legal_retention_reason": self.legal_retention_reason,
        }
        return {key: value for key, value in values.items() if value is not None}


class IncidentReconstruction(TypedDict):
    incident_id: str
    integrity: dict[str, JSONValue]
    events: list[dict[str, JSONValue]]
    commands: list[dict[str, JSONValue]]
    conflict_history: list[dict[str, JSONValue]]


def _event_record(event: Event) -> dict[str, JSONValue]:
    provenance = event.provenance if isinstance(event.provenance, dict) else {}
    audit = provenance.get("audit")
    context = audit if isinstance(audit, dict) else {}
    record: dict[str, JSONValue] = {
        "event_id": event.id,
        "actor": event.actor,
        "agency": context.get("agency_id"),
        "device": context.get("device_id"),
        "auth": context.get("auth_method"),
        "source": event.source_id,
        "source_time_ms": event.source_time_ms,
        "receipt_time_ms": event.receipt_time_ms,
        "sequence": event.sequence,
        "derivation": context.get("derivation", []),
        "signature_hash": context.get("signature_hash"),
        "payload_hash": context.get("payload_hash"),
        "retention": {
            "until_ms": context.get("retention_until_ms"),
            "legal_reason": context.get("legal_retention_reason"),
        },
        "prev_hash": event.prev_hash,
        "hash": event.hash,
        "action": event.action,
        "entity": event.entity,
        "before": sanitize_audit_value(event.before),
        "after": sanitize_audit_value(event.after),
    }
    return record


def _command_record(approval: CommandApproval) -> dict[str, JSONValue]:
    signature_hash = hashlib.sha256(approval.signature.encode("ascii")).hexdigest()
    return {
        "approval_id": approval.id,
        "decision_id": approval.decision_id,
        "approver": approval.approver_id,
        "role": approval.approver_role,
        "key_id": approval.key_id,
        "nonce": approval.nonce,
        "signed_at_ms": approval.signed_at_ms,
        "expires_at_ms": approval.expires_at_ms,
        "signature_hash": f"sha256:{signature_hash}",
    }


def _conflict_record(conflict: SyncConflict) -> dict[str, JSONValue]:
    return {
        "id": str(conflict.id),
        "entity_type": conflict.entity_type,
        "entity_id": conflict.entity_id,
        "detected_at": conflict.detected_at,
        "local_hash": conflict.content_hash_local,
        "remote_hash": conflict.content_hash_remote,
        "local": sanitize_audit_value(conflict.local),
        "remote": sanitize_audit_value(conflict.remote),
    }


def reconstruct_incident(
    db: Session,
    org_id: str,
    incident_id: str,
) -> IncidentReconstruction:
    """Rebuild an incident timeline without returning raw PII or signatures."""
    events = db.execute(
        select(Event).where(
            Event.org_id == org_id,
            Event.incident_id == incident_id,
        ).order_by(Event.sequence, Event.ts, Event.id)
    ).scalars().all()
    approvals = db.execute(
        select(CommandApproval).where(
            CommandApproval.org_id == org_id,
            CommandApproval.incident_id == incident_id,
        ).order_by(CommandApproval.created_at, CommandApproval.id)
    ).scalars().all()
    conflicts = db.execute(
        select(SyncConflict).where(
            SyncConflict.org_id == org_id,
            SyncConflict.incident_id == incident_id,
        ).order_by(SyncConflict.detected_at, SyncConflict.id)
    ).scalars().all()
    chain_result = verify_chain(db, org_id)
    return {
        "incident_id": incident_id,
        "integrity": {
            "audit_chain_valid": chain_result is True,
            "first_broken_index": chain_result if chain_result is not True else None,
            "event_count": len(events),
        },
        "events": [_event_record(event) for event in events],
        "commands": [_command_record(approval) for approval in approvals],
        "conflict_history": [_conflict_record(conflict) for conflict in conflicts],
    }


__all__ = ["AuditContext", "IncidentReconstruction", "reconstruct_incident"]
