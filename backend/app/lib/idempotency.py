from __future__ import annotations

from sqlalchemy import BigInteger, String, UniqueConstraint, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.lib.audit import JSONValue, canonical_json_bytes, sha256_hex
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.events import Event, RawEvent, RawEventRecord
from app.models.observation import Observation

INGESTION_FAILURE_RETENTION_DAYS = 30


class IdempotencyConflictError(Exception):
    __slots__ = ("external_id", "org_id", "source")

    def __init__(self, org_id: str, source: str, external_id: str) -> None:
        super().__init__()
        self.org_id = org_id
        self.source = source
        self.external_id = external_id

    def __str__(self) -> str:
        return f"idempotency key conflicts with a different payload: {self.org_id}/{self.source}/{self.external_id}"


class InvalidIdempotencyKeyError(Exception):
    __slots__ = ("field",)

    def __init__(self, field: str) -> None:
        super().__init__()
        self.field = field

    def __str__(self) -> str:
        return f"idempotency key field is required: {self.field}"


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "source", "external_id", name="uq_idempotency_org_source_external"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    incident_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    schema_version: Mapped[str] = mapped_column(String, nullable=False, default="1.0")
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=now_ms)


def check_and_record(
    db: Session,
    source: str,
    external_id: str,
    *,
    org_id: str = "",
    incident_id: str = "",
    payload: dict[str, JSONValue] | None = None,
    commit: bool = True,
) -> bool:
    if not source:
        raise InvalidIdempotencyKeyError("source")
    if not external_id:
        raise InvalidIdempotencyKeyError("external_id")
    if payload is not None and not org_id:
        raise InvalidIdempotencyKeyError("org_id")
    request_hash = sha256_hex(canonical_json_bytes(payload)) if payload is not None else None
    row = IdempotencyKey(
        org_id=org_id,
        incident_id=incident_id,
        source=source,
        external_id=external_id,
        request_hash=request_hash,
        payload=payload,
        created_at=now_ms(),
    )
    if commit:
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return _resolve_duplicate(db, org_id, source, external_id, request_hash)
        return True
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return _resolve_duplicate(db, org_id, source, external_id, request_hash)
    return True


def _resolve_duplicate(
    db: Session,
    org_id: str,
    source: str,
    external_id: str,
    request_hash: str | None,
) -> bool:
    existing = db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.org_id == org_id,
            IdempotencyKey.source == source,
            IdempotencyKey.external_id == external_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        raise IdempotencyConflictError(org_id, source, external_id) from None
    if existing.request_hash != request_hash:
        raise IdempotencyConflictError(org_id, source, external_id) from None
    return False


def record_raw_event(db: Session, event: RawEvent) -> bool:
    row = RawEventRecord(
        id=event.event_id,
        org_id=event.org_id,
        incident_id=event.incident_id,
        source_id=event.source_id,
        external_id=event.external_id,
        event_type=event.event_type,
        source_time_ms=event.source_time_ms,
        receipt_time_ms=event.receipt_time_ms,
        sequence=event.sequence,
        payload=event.payload,
        provenance=(
            event.provenance.model_dump(mode="json")
            if event.provenance is not None
            else None
        ),
        visibility=event.visibility.value,
        review_status=event.review_status.value,
        schema_version=event.schema_version,
        canonical_hash=event.canonical_hash(),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = db.execute(
            select(RawEventRecord).where(
                RawEventRecord.org_id == event.org_id,
                RawEventRecord.source_id == event.source_id,
                RawEventRecord.external_id == event.external_id,
            )
        ).scalar_one_or_none()
        if existing is None or existing.canonical_hash != event.canonical_hash():
            raise IdempotencyConflictError(
                event.org_id, event.source_id, event.external_id
            ) from None
        return False
    return True


def next_raw_sequence(db: Session, org_id: str, source_id: str) -> int:
    latest = db.execute(
        select(func.max(RawEventRecord.sequence)).where(
            RawEventRecord.org_id == org_id,
            RawEventRecord.source_id == source_id,
        )
    ).scalar_one()
    return int(latest or 0) + 1


def claim_raw_event(
    db: Session,
    event: RawEvent,
    payload: dict[str, JSONValue],
    idempotency_key: str | None = None,
) -> bool:
    is_new = check_and_record(
        db,
        event.source_id,
        event.external_id,
        org_id=event.org_id,
        incident_id=event.incident_id,
        payload=payload,
        commit=False,
    )
    if idempotency_key and idempotency_key != event.external_id:
        check_and_record(
            db,
            f"{event.source_id}:idempotency",
            idempotency_key,
            org_id=event.org_id,
            incident_id=event.incident_id,
            payload=payload,
            commit=False,
        )
    if not is_new:
        return False
    record_raw_event(db, event)
    return True


def stable_ingestion_claim(payload: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {
        "external_id": payload["external_id"],
        "raw_data_hash": payload["raw_data_hash"],
        "source_id": payload["source_id"],
        "org_id": payload["org_id"],
        "incident_id": payload["incident_id"],
    }


def record_published_raw_event(db: Session, payload: dict[str, JSONValue]) -> bool:
    def epoch_ms(key: str) -> int:
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{key} must be an epoch integer")
        return value

    event = RawEvent(
        event_id=str(payload["observation_id"]),
        org_id=str(payload["org_id"]),
        incident_id=str(payload["incident_id"]),
        source_id=str(payload["source_id"]),
        external_id=str(payload["external_id"]),
        event_type=str(payload["event_type"]),
        source_time_ms=epoch_ms("observed_at"),
        receipt_time_ms=epoch_ms("received_at"),
        sequence=next_raw_sequence(db, str(payload["org_id"]), str(payload["source_id"])),
        payload=payload,
    )
    return record_raw_event(db, event)


def lookup_observation_id(
    db: Session, org_id: str, source_id: str, external_id: str
) -> str | None:
    raw = db.execute(
        select(RawEventRecord).where(
            RawEventRecord.org_id == org_id,
            RawEventRecord.source_id == source_id,
            RawEventRecord.external_id == external_id,
        )
    ).scalar_one_or_none()
    if raw is None:
        return None
    return db.execute(
        select(Observation.observation_id).where(
            Observation.raw_event_id == raw.id,
            Observation.org_id == org_id,
        )
    ).scalar_one_or_none()


def record_ingestion_failure(
    db: Session,
    payload: dict[str, JSONValue],
    error: str,
) -> Event:
    org_id = payload.get("org_id")
    incident_id = payload.get("incident_id")
    source_id = payload.get("source_id")
    external_id = payload.get("external_id") or payload.get("observation_id")
    resolved_org_id = org_id if isinstance(org_id, str) and org_id else "unknown"
    resolved_incident_id = (
        incident_id if isinstance(incident_id, str) else ""
    )
    resolved_source_id = source_id if isinstance(source_id, str) and source_id else "unknown"
    resolved_external_id = (
        external_id
        if isinstance(external_id, str) and external_id
        else f"failure-{generate_ulid()}"
    )
    existing = db.execute(
        select(Event)
        .where(
            Event.org_id == resolved_org_id,
            Event.action == "ingestion.failed",
            Event.entity == resolved_external_id,
        )
        .order_by(Event.sequence.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    from app.lib.audit import write_audit

    return write_audit(
        db,
        org_id=resolved_org_id,
        incident_id=resolved_incident_id,
        actor="streaming-consumer",
        action="ingestion.failed",
        entity=resolved_external_id,
        event_type="ingestion_failure",
        source_id=resolved_source_id,
        external_id=resolved_external_id,
        after={
            "error": error[:1000],
            "payload": payload,
            "replayable": True,
            "dlq_retention_days": INGESTION_FAILURE_RETENTION_DAYS,
        },
    )


def authorize_replay(
    db: Session, entity: str, *, org_id: str, actor: str, role: str
) -> Event:
    if role != "admin":
        raise PermissionError("only admin may replay ingestion failures")
    failure = db.execute(
        select(Event)
        .where(
            Event.org_id == org_id,
            Event.action == "ingestion.failed",
            Event.entity == entity,
        )
        .order_by(Event.sequence.desc())
        .limit(1)
    ).scalar_one_or_none()
    if failure is None:
        raise LookupError(f"ingestion failure not found: {entity}")
    from app.lib.audit import write_audit

    return write_audit(
        db,
        org_id=failure.org_id,
        incident_id=failure.incident_id,
        actor=actor,
        action="ingestion.replay",
        entity=entity,
        event_type="ingestion_replay",
        source_id=failure.source_id,
        external_id=failure.external_id,
        after={
            "failure_event_id": failure.id,
            "failure_hash": failure.hash,
            "authorized_role": role,
        },
    )


def replay_payload(
    db: Session, entity: str, *, org_id: str, role: str
) -> tuple[Event, dict[str, JSONValue]]:
    if role != "admin":
        raise PermissionError("only admin may replay ingestion failures")
    failure = db.execute(
        select(Event)
        .where(
            Event.org_id == org_id,
            Event.action == "ingestion.failed",
            Event.entity == entity,
        )
        .order_by(Event.sequence.desc())
        .limit(1)
    ).scalar_one_or_none()
    if failure is None or not isinstance(failure.after, dict):
        raise LookupError(f"ingestion failure not found: {entity}")
    payload = failure.after.get("payload")
    if not isinstance(payload, dict):
        raise TypeError("ingestion failure payload is not replayable")
    return failure, payload


def record_replay_dispatch(
    db: Session, failure: Event, *, actor: str, role: str
) -> Event:
    from app.lib.audit import write_audit

    return write_audit(
        db,
        org_id=failure.org_id,
        incident_id=failure.incident_id,
        actor=actor,
        action="ingestion.replay",
        entity=failure.entity,
        event_type="ingestion_replay",
        source_id=failure.source_id,
        external_id=failure.external_id,
        after={
            "failure_event_id": failure.id,
            "failure_hash": failure.hash,
            "authorized_role": role,
        },
    )


__all__ = [
    "INGESTION_FAILURE_RETENTION_DAYS",
    "IdempotencyConflictError",
    "IdempotencyKey",
    "InvalidIdempotencyKeyError",
    "authorize_replay",
    "check_and_record",
    "claim_raw_event",
    "lookup_observation_id",
    "next_raw_sequence",
    "record_ingestion_failure",
    "record_published_raw_event",
    "record_raw_event",
    "record_replay_dispatch",
    "replay_payload",
    "stable_ingestion_claim",
]
