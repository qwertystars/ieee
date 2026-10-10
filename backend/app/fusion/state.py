"""Pure hypothesis, conflict, and world-state replay kernels."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from app.fusion.kernel import FLOOD_PHENOMENA, PRIOR, STATES, ReplayObservation
from app.lib.audit import JSONValue
from app.models.events import RawEvent


class StateInputError(ValueError):
    """A hypothesis input cannot produce a unique deterministic state."""


def hypothesis_outputs(events: Sequence[RawEvent], observations: Sequence[ReplayObservation]) -> tuple[list[tuple[str, dict[str, JSONValue]]], list[dict[str, JSONValue]]]:
    hypotheses: list[tuple[str, dict[str, JSONValue]]] = []
    by_entity: dict[str, list[str]] = defaultdict(list)
    for event in events:
        payload, claim, entity_id = event.payload, event.payload.get("claim"), event.payload.get("entity_id")
        if not isinstance(claim, str) or not isinstance(entity_id, str):
            continue
        if "hypothesis" not in event.event_type.lower() and "hypothesis_id" not in payload:
            continue
        hypothesis_id = payload.get("hypothesis_id", event.external_id)
        entity_type = payload.get("entity_type", payload.get("phenomenon", "unknown"))
        key = hypothesis_id if isinstance(hypothesis_id, str) else event.external_id
        entity = entity_type if isinstance(entity_type, str) else "unknown"
        if any(existing_key == key for existing_key, _ in hypotheses):
            raise StateInputError(f"duplicate hypothesis_id: {key}")
        probability = _bounded(payload, "probability", 0.5)
        row: dict[str, JSONValue] = {"hypothesis_id": key, "entity_type": entity,
            "entity_id": entity_id, "claim": claim, "probability": probability,
            "supporting_event_ids": [], "contradicting_event_ids": []}
        hypotheses.append((key, row))
        by_entity[entity_id].append(key)
    for _, row in hypotheses:
        support, contradict = row["supporting_event_ids"], row["contradicting_event_ids"]
        assert isinstance(support, list) and isinstance(contradict, list)
        for observation in observations:
            observation_entity = observation.event.payload.get("entity_id")
            if (
                observation.phenomenon != row["entity_type"]
                or observation_entity != row["entity_id"]
                or observation.value is None
            ):
                continue
            claim = str(row["claim"]).lower()
            if "impassable" in claim:
                supports = observation.value < 0.5
            elif "passable" in claim:
                supports = observation.value >= 0.5
            else:
                continue
            (support if supports else contradict).append(observation.event.event_id)
            probability = min(1.0, max(0.0, probability + (0.1 if supports else -0.1)))
            row["probability"] = probability
    conflicts: list[dict[str, JSONValue]] = []
    for entity_id, ids in sorted(by_entity.items()):
        claims = {
            str(row["claim"]).strip().lower()
            for key, row in hypotheses
            if key in ids
        }
        if len(claims) > 1:
            hypothesis_ids: list[JSONValue] = []
            hypothesis_ids.extend(ids)
            conflicts.append({
                "conflict_key": f"hypothesis:{entity_id}",
                "entity_id": entity_id,
                "hypothesis_ids": hypothesis_ids,
                "resolution": "abstain",
            })
    return hypotheses, conflicts


def _bounded(payload: dict[str, JSONValue], key: str, default: float) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return min(1.0, max(0.0, float(value)))


def _state_index(observation: ReplayObservation) -> int | None:
    severity = observation.event.payload.get("severity")
    if isinstance(severity, str) and severity in STATES:
        return STATES.index(severity)
    if observation.value is None or observation.phenomenon not in FLOOD_PHENOMENA:
        return None
    bins = (0.0, 5.0, 15.0, 30.0, 50.0) if observation.phenomenon == "flood_extent" else (0.0, 0.5, 1.5, 3.0, 5.0)
    return next((i for i, bound in enumerate(bins) if observation.value < bound), 4)


def world_state_outputs(observations: Sequence[ReplayObservation], as_of_ms: int) -> list[tuple[str, dict[str, JSONValue]]]:
    by_hazard: dict[str, list[ReplayObservation]] = defaultdict(list)
    for observation in observations:
        if observation.phenomenon in FLOOD_PHENOMENA:
            hazard = observation.event.payload.get("hazard_type", "flood")
            by_hazard[str(hazard)].append(observation)
    outputs: list[tuple[str, dict[str, JSONValue]]] = []
    for hazard, hazard_observations in sorted(by_hazard.items()):
        distribution = list(PRIOR)
        event_ids: list[JSONValue] = []
        for observation in hazard_observations:
            index = _state_index(observation)
            if index is None:
                continue
            likelihood = [0.15 / 4.0] * len(STATES)
            likelihood[index] = 0.85
            distribution = [prior * probability for prior, probability in zip(distribution, likelihood, strict=True)]
            total = sum(distribution)
            distribution = [value / total for value in distribution]
            event_ids.append(observation.event.event_id)
        state_distribution: dict[str, JSONValue] = dict(zip(STATES, distribution, strict=True))
        outputs.append((hazard, {"hazard_type": hazard, "state_distribution": state_distribution,
                                "evidence_event_ids": event_ids, "as_of_ms": as_of_ms}))
    return outputs


__all__ = ["hypothesis_outputs", "world_state_outputs"]
