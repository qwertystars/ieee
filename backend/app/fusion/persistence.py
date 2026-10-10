"""Transactional persistence adapter for deterministic replay results."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.fusion.lineage import canonical_event_hash
from app.fusion.replay import ReplayResult
from app.lib.audit import JSONValue, canonical_json_bytes, sha256_hex
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.fusion_replay import (
    FusionReplayErrorRecord,
    FusionReplayInputRecord,
    FusionReplayOutputRecord,
    FusionReplayRun,
)


class ReplayPersistenceError(ValueError):
    """A replay result failed durable integrity or tenancy checks."""


def persist_replay(
    db: Session,
    result: ReplayResult,
    *,
    org_id: str,
    incident_id: str,
) -> FusionReplayRun:
    """Flush one replay and all children into the caller-owned transaction."""
    lineage = result.lineage
    for event in result.input_events:
        if event.org_id != org_id or event.incident_id != incident_id:
            raise ReplayPersistenceError("replay input scope does not match persistence scope")
    input_payload: list[JSONValue] = [event.model_dump(mode="json") for event in result.input_events]
    computed_input_hash = f"sha256:{sha256_hex(canonical_json_bytes(input_payload))}"
    if computed_input_hash != result.input_hash:
        raise ReplayPersistenceError("replay input hash does not match canonical inputs")
    if any(output.lineage_hash != lineage.lineage_hash for output in result.outputs):
        raise ReplayPersistenceError("replay output lineage does not match run lineage")
    created_at_ms = now_ms()
    run = FusionReplayRun(
        id=generate_ulid(),
        org_id=org_id,
        incident_id=incident_id,
        algorithm_version=lineage.algorithm_version,
        config_version=lineage.config_version,
        runtime_version=lineage.runtime_version,
        library_versions=[
            {"name": name, "version": version}
            for name, version in lineage.library_versions
        ],
        model_versions=[
            {"name": name, "version": version}
            for name, version in lineage.model_versions
        ],
        serialization_version=lineage.serialization_version,
        lineage=lineage.as_dict(),
        float_tolerance=lineage.float_tolerance,
        lineage_hash=lineage.lineage_hash,
        seed=result.seed,
        as_of_ms=result.as_of_ms,
        input_hash=result.input_hash,
        decision_hash=result.decision_hash,
        output_hash=result.output_hash,
        status=result.status,
        created_at_ms=created_at_ms,
    )
    db.add(run)
    db.flush()
    for ordinal, event in enumerate(result.input_events):
        db.add(
            FusionReplayInputRecord(
                id=generate_ulid(),
                run_id=run.id,
                ordinal=ordinal,
                event_id=event.event_id,
                canonical_hash=canonical_event_hash(event),
                canonical_event=event.model_dump(mode="json"),
            )
        )
    for output in result.outputs:
        db.add(
            FusionReplayOutputRecord(
                id=generate_ulid(),
                run_id=run.id,
                output_type=output.output_type,
                output_key=output.output_key,
                payload=output.payload,
                decision_hash=output.decision_hash,
                output_hash=output.output_hash,
                lineage_hash=lineage.lineage_hash,
            )
        )
    for error in result.errors:
        db.add(
            FusionReplayErrorRecord(
                id=generate_ulid(),
                run_id=run.id,
                stage=error.stage,
                event_id=error.event_id,
                error_type=error.error_type,
                message=error.message,
                created_at_ms=created_at_ms,
            )
        )
    db.flush()
    return run


__all__ = ["persist_replay"]
