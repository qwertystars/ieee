"""Deterministic replay orchestration over canonical raw events."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from app.fusion.kernel import (
    KernelInputError,
    ReplayObservation,
    ReplayOutput,
    confidence,
    make_output,
    parse_observation,
)
from app.fusion.lineage import ReplayConfig, ReplayLineage, order_events
from app.fusion.state import StateInputError, hypothesis_outputs, world_state_outputs
from app.lib.audit import JSONValue, canonical_json_bytes, sha256_hex
from app.lib.time import from_iso
from app.models.events import RawEvent


@dataclass(frozen=True, slots=True)
class ReplayInputError(ValueError):
    """A raw replay input could not be parsed or safely reduced."""

    event_id: str | None
    reason: str

    def __str__(self) -> str:
        prefix = f"event {self.event_id}: " if self.event_id else "replay input: "
        return prefix + self.reason


@dataclass(frozen=True, slots=True)
class ReplayError:
    """A replay error retained as durable, structured output."""

    stage: str
    event_id: str | None
    error_type: str
    message: str

    def as_dict(self) -> dict[str, JSONValue]:
        return {"stage": self.stage, "event_id": self.event_id,
                "error_type": self.error_type, "message": self.message}


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Complete deterministic replay result, suitable for persistence."""

    lineage: ReplayLineage
    seed: int
    as_of_ms: int
    input_event_ids: tuple[str, ...]
    input_events: tuple[RawEvent, ...]
    input_hash: str
    outputs: tuple[ReplayOutput, ...]
    errors: tuple[ReplayError, ...]
    decision_hash: str
    output_hash: str

    @property
    def status(self) -> str:
        return "completed" if not self.errors else "completed_with_errors"

    def as_dict(self) -> dict[str, JSONValue]:
        return {"lineage": self.lineage.as_dict(), "lineage_hash": self.lineage.lineage_hash,
                "seed": self.seed, "as_of_ms": self.as_of_ms,
                "input_event_ids": list(self.input_event_ids),
                "input_events": [event.model_dump(mode="json") for event in self.input_events],
                "input_hash": self.input_hash, "outputs": [output.as_dict() for output in self.outputs],
                "errors": [error.as_dict() for error in self.errors],
                "decision_hash": self.decision_hash, "output_hash": self.output_hash,
                "status": self.status}


def _timestamp(record: Mapping[str, JSONValue], names: tuple[str, ...]) -> int:
    for name in names:
        raw = record.get(name)
        if raw is None:
            continue
        if isinstance(raw, bool):
            raise TypeError(f"{name} must be an epoch integer or ISO timestamp")
        if isinstance(raw, int):
            if raw < 0:
                raise ValueError(f"{name} must be non-negative")
            return raw
        if isinstance(raw, str):
            return from_iso(raw)
        raise TypeError(f"{name} must be an epoch integer or ISO timestamp")
    raise ValueError(f"missing timestamp: {names[0]}")


def event_from_mapping(record: Mapping[str, JSONValue]) -> RawEvent:
    """Parse fixture or database-shaped data into the canonical event contract."""
    try:
        values = dict(record)
        values["source_time_ms"] = _timestamp(record, ("source_time_ms", "source_time", "observed_at"))
        values["receipt_time_ms"] = _timestamp(record, ("receipt_time_ms", "receipt_time", "received_at"))
        for alias in ("source_time", "receipt_time", "observed_at", "received_at"):
            values.pop(alias, None)
        return RawEvent.model_validate(values)
    except (TypeError, ValueError, ValidationError) as exc:
        raw_event_id = record.get("event_id")
        event_id = raw_event_id if isinstance(raw_event_id, str) else None
        raise ReplayInputError(event_id, str(exc)) from exc


def _structural_errors(events: Sequence[RawEvent]) -> tuple[ReplayError, ...]:
    errors: list[ReplayError] = []
    seen_event_ids: set[str] = set()
    seen_external_ids: set[tuple[str, str]] = set()
    scopes = {(event.org_id, event.incident_id) for event in events}
    if len(scopes) > 1:
        errors.append(ReplayError("scope", None, "ReplayScopeError", "events must share org_id and incident_id"))
    for event in events:
        if event.event_id in seen_event_ids:
            errors.append(ReplayError("input", event.event_id, "DuplicateEventError", "event_id is repeated"))
        seen_event_ids.add(event.event_id)
        external_key = (event.source_id, event.external_id)
        if external_key in seen_external_ids:
            errors.append(ReplayError("input", event.event_id, "DuplicateExternalIdError", "source_id and external_id are repeated"))
        seen_external_ids.add(external_key)
        payload = event.payload
        is_hypothesis = "hypothesis" in event.event_type.lower() or "hypothesis_id" in payload
        if not is_hypothesis:
            continue
        for field in ("claim", "entity_id"):
            if not isinstance(payload.get(field), str) or not str(payload[field]).strip():
                errors.append(ReplayError("hypothesis", event.event_id, "MalformedHypothesisError", f"{field} must be a non-empty string"))
        probability = payload.get("probability")
        if probability is not None and (
            isinstance(probability, bool)
            or not isinstance(probability, (int, float))
            or not math.isfinite(float(probability))
            or not 0.0 <= float(probability) <= 1.0
        ):
            errors.append(ReplayError("hypothesis", event.event_id, "MalformedHypothesisError", "probability must be finite and between 0 and 1"))
    return tuple(errors)


def _build_outputs(
    events: Sequence[RawEvent], observations: Sequence[ReplayObservation],
    as_of_ms: int, lineage: ReplayLineage,
) -> list[ReplayOutput]:
    outputs = [make_output("confidence", observation.event.event_id,
                           confidence(observation, observations, as_of_ms), lineage)
               for observation in observations]
    hypotheses, conflicts = hypothesis_outputs(events, observations)
    outputs.extend(make_output("hypothesis", key, payload, lineage) for key, payload in hypotheses)
    outputs.extend(make_output("conflict", str(payload["conflict_key"]), payload, lineage)
                   for payload in conflicts)
    outputs.extend(make_output("world_state", hazard, payload, lineage)
                   for hazard, payload in world_state_outputs(observations, as_of_ms))
    return sorted(outputs, key=lambda output: (output.output_type, output.output_key))


def replay_events(
    events: RawEvent | Mapping[str, JSONValue] | Sequence[RawEvent | Mapping[str, JSONValue]], *, seed: int = 0,
    config: ReplayConfig | None = None,
) -> ReplayResult:
    """Rebuild all replay outputs from canonical events only."""
    replay_config = config or ReplayConfig()
    if isinstance(events, (RawEvent, Mapping)):
        supplied: tuple[RawEvent | Mapping[str, JSONValue], ...] = (events,)
    else:
        supplied = tuple(events)
    errors: list[ReplayError] = []
    parsed_events: list[RawEvent] = []
    for item in supplied:
        if isinstance(item, RawEvent):
            parsed_events.append(item)
            continue
        try:
            parsed_events.append(event_from_mapping(item))
        except ReplayInputError as exc:
            errors.append(ReplayError("input", exc.event_id, type(exc).__name__, str(exc)))
    if isinstance(seed, bool) or not isinstance(seed, int):
        errors.append(ReplayError("config", None, "ReplayConfigError", "seed must be an integer"))
    supplied_events = tuple(parsed_events)
    ordered = order_events(supplied_events)
    lineage = replay_config.lineage()
    as_of_ms = replay_config.as_of_ms if replay_config.as_of_ms is not None else max(
        (event.source_time_ms for event in ordered), default=0)
    structural_errors = _structural_errors(ordered)
    errors.extend(structural_errors)
    invalid_event_ids = {
        error.event_id for error in structural_errors if error.event_id is not None
    }
    blocking_structure_error = any(
        error.event_id is None
        or error.error_type
        in {
            "DuplicateEventError",
            "DuplicateExternalIdError",
            "MalformedHypothesisError",
        }
        for error in structural_errors
    )
    processable = tuple(event for event in ordered if event.event_id not in invalid_event_ids)
    observations: list[ReplayObservation] = []
    for event in processable:
        try:
            parsed = parse_observation(event)
        except KernelInputError as exc:
            errors.append(ReplayError("observation", exc.event_id, type(exc).__name__, str(exc)))
            continue
        if parsed is not None:
            observations.append(parsed)
    try:
        outputs = [] if blocking_structure_error else _build_outputs(
            processable, observations, as_of_ms, lineage
        )
    except StateInputError as exc:
        errors.append(ReplayError("state", None, type(exc).__name__, str(exc)))
        outputs = []
    input_payload: list[JSONValue] = [event.model_dump(mode="json") for event in ordered]
    input_hash = f"sha256:{sha256_hex(canonical_json_bytes(input_payload))}"
    decision_hash = f"sha256:{sha256_hex(canonical_json_bytes([output.decision_hash for output in outputs]))}"
    output_hash = f"sha256:{sha256_hex(canonical_json_bytes([output.as_dict() for output in outputs]))}"
    normalized_seed = seed if isinstance(seed, int) and not isinstance(seed, bool) else 0
    return ReplayResult(lineage, normalized_seed, as_of_ms,
                        tuple(event.event_id for event in ordered), ordered, input_hash,
                        tuple(outputs), tuple(errors), decision_hash, output_hash)


__all__ = ["ReplayConfig", "ReplayError", "ReplayInputError", "ReplayObservation",
           "ReplayOutput", "ReplayResult", "event_from_mapping", "replay_events"]
