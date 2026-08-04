"""Pure confidence-kernel operations used by deterministic replay."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from app.fusion.lineage import ReplayLineage
from app.lib.audit import JSONValue, canonical_json_bytes, sha256_hex
from app.models.events import RawEvent

TAU_MS: Final[dict[str, int]] = {
    "water_level": 300_000,
    "flood_depth": 600_000,
    "flood_extent": 600_000,
    "road_passability": 600_000,
}
GEO_PRECISION: Final[dict[str, float]] = {
    "sensor": 1.0, "satellite": 0.9, "drone": 0.8,
    "official_feed": 0.7, "model": 0.5, "social_media": 0.3,
    "citizen_report": 0.3, "other": 0.1,
}
STATES: Final[tuple[str, ...]] = ("none", "minor", "moderate", "severe", "extreme")
PRIOR: Final[tuple[float, ...]] = (0.4, 0.25, 0.15, 0.1, 0.1)
FLOOD_PHENOMENA: Final[frozenset[str]] = frozenset(
    {"water_level", "flood_depth", "flood_extent", "flood_report", "severity"}
)


@dataclass(frozen=True, slots=True)
class KernelInputError(Exception):
    """A canonical event cannot be interpreted by the pinned kernel."""

    event_id: str
    reason: str

    def __str__(self) -> str:
        return f"event {self.event_id}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ReplayObservation:
    event: RawEvent
    phenomenon: str
    value: float | None
    source_type: str
    model_uncertainty: float | None


@dataclass(frozen=True, slots=True)
class ReplayOutput:
    """One canonical fusion output with lineage-bound hashes."""

    output_type: str
    output_key: str
    payload: dict[str, JSONValue]
    lineage_hash: str
    decision_hash: str
    output_hash: str

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            "output_type": self.output_type, "output_key": self.output_key,
            "payload": self.payload, "lineage_hash": self.lineage_hash,
            "decision_hash": self.decision_hash,
            "output_hash": self.output_hash,
        }


def _number(value: JSONValue, event_id: str, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int, str)):
        raise KernelInputError(event_id, f"{field} must be numeric")
    try:
        result = float(value)
    except ValueError as exc:
        raise KernelInputError(event_id, f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise KernelInputError(event_id, f"{field} must be finite")
    return result


def parse_observation(event: RawEvent) -> ReplayObservation | None:
    payload = event.payload
    phenomenon = payload.get("phenomenon")
    if "observation" not in event.event_type.lower() and "value" not in payload:
        return None
    if not isinstance(phenomenon, str) or not phenomenon:
        raise KernelInputError(event.event_id, "phenomenon must be a non-empty string")
    raw_value = payload.get("value")
    value = None if raw_value is None else _number(raw_value, event.event_id, "value")
    source_type = payload.get("source_type", "other")
    if not isinstance(source_type, str) or not source_type:
        raise KernelInputError(event.event_id, "source_type must be a non-empty string")
    uncertainty = payload.get("model_uncertainty")
    return ReplayObservation(
        event=event,
        phenomenon=phenomenon,
        value=value,
        source_type=source_type,
        model_uncertainty=None if uncertainty is None else _number(uncertainty, event.event_id, "model_uncertainty"),
    )


def _bounded(payload: Mapping[str, JSONValue], key: str, default: float) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return min(1.0, max(0.0, float(value)))


def confidence(observation: ReplayObservation, observations: Sequence[ReplayObservation], as_of_ms: int) -> dict[str, JSONValue]:
    tau = TAU_MS.get(observation.phenomenon, 600_000)
    nearby = [candidate for candidate in observations if (
        candidate.event.event_id != observation.event.event_id
        and candidate.phenomenon == observation.phenomenon
        and abs(candidate.event.source_time_ms - observation.event.source_time_ms) <= 2 * tau
    )]
    conflicts = sum(1 for candidate in nearby if (
        observation.value is not None and candidate.value is not None
        and abs(observation.value - candidate.value) / max(abs(observation.value), abs(candidate.value), 1.0) >= 0.2
    ))
    corroborating = len(nearby) - conflicts
    age_ms = max(0, as_of_ms - observation.event.source_time_ms)
    source_reliability = _bounded(observation.event.payload, "source_reliability", 0.5)
    corroboration = 1.0 - math.exp(-corroborating)
    freshness = math.exp(-(age_ms / 1000.0) / (tau / 1000.0))
    geographic_precision = GEO_PRECISION.get(observation.source_type, 0.1)
    model_uncertainty = observation.model_uncertainty or 0.0
    conflict_score = 1.0 - math.exp(-conflicts)
    vector: dict[str, JSONValue] = {
        "s": source_reliability,
        "c": corroboration,
        "f": freshness,
        "g": geographic_precision,
        "m": observation.model_uncertainty,
        "k": conflict_score,
    }
    display = 0.25 * source_reliability + 0.20 * corroboration
    display += 0.20 * freshness + 0.10 * geographic_precision
    display -= 0.10 * model_uncertainty + 0.15 * conflict_score
    return {"event_id": observation.event.event_id, "phenomenon": observation.phenomenon,
            "confidence_vector": vector, "display_confidence": display}


def _normalize_float(value: float, tolerance: float) -> float:
    """Quantize a finite numeric value for tolerance-aware decision identity."""
    normalized = round(value / tolerance) * tolerance
    return 0.0 if normalized == 0 else normalized


def _normalize_payload(value: JSONValue, tolerance: float) -> JSONValue:
    if isinstance(value, float):
        return _normalize_float(value, tolerance)
    if isinstance(value, list):
        return [_normalize_payload(item, tolerance) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_payload(item, tolerance) for key, item in value.items()}
    return value


def make_output(output_type: str, output_key: str, payload: dict[str, JSONValue], lineage: ReplayLineage) -> ReplayOutput:
    normalized_payload = _normalize_payload(payload, lineage.float_tolerance)
    if not isinstance(normalized_payload, dict):
        raise TypeError("normalized output payload must remain a mapping")
    identity: dict[str, JSONValue] = {
        "lineage_hash": lineage.lineage_hash,
        "output_type": output_type,
        "output_key": output_key,
        "payload": normalized_payload,
    }
    decision_hash = f"sha256:{sha256_hex(canonical_json_bytes(identity))}"
    output_hash = f"sha256:{sha256_hex(canonical_json_bytes({**identity, 'decision_hash': decision_hash}))}"
    return ReplayOutput(
        output_type,
        output_key,
        payload,
        lineage.lineage_hash,
        decision_hash,
        output_hash,
    )


__all__ = [
    "FLOOD_PHENOMENA",
    "PRIOR",
    "STATES",
    "KernelInputError",
    "ReplayObservation",
    "ReplayOutput",
    "confidence",
    "make_output",
    "parse_observation",
]
