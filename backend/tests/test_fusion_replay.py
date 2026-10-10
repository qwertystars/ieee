from __future__ import annotations

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.fusion.persistence import persist_replay
from app.fusion.replay import (
    ReplayConfig,
    event_from_mapping,
    replay_events,
)
from app.models.events import RawEvent
from app.models.fusion_replay import (
    FusionReplayErrorRecord,
    FusionReplayInputRecord,
    FusionReplayOutputRecord,
    FusionReplayRun,
)

ORG_ID = "org_replay_contract"
INCIDENT_ID = "incident_replay_contract"


def _event(event_id: str, source_time_ms: int, payload: dict) -> RawEvent:
    return RawEvent(
        event_id=event_id,
        org_id=ORG_ID,
        incident_id=INCIDENT_ID,
        source_id="sensor-1",
        external_id=event_id,
        event_type="sensor.observation",
        source_time_ms=source_time_ms,
        receipt_time_ms=source_time_ms + 10,
        sequence=source_time_ms,
        payload=payload,
    )


def test_replay_is_independent_of_input_order_and_database_order() -> None:
    events = [
        _event(
            "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            1_756_000_000_200,
            {"phenomenon": "water_level", "value": 1.5, "unit": "m"},
        ),
        _event(
            "01ARZ3NDEKTSV4RRFFQ69G5FAW",
            1_756_000_000_100,
            {"phenomenon": "water_level", "value": 1.2, "unit": "m"},
        ),
    ]
    config = ReplayConfig(as_of_ms=1_756_000_001_000)

    first = replay_events(events, seed=1, config=config)
    second = replay_events(list(reversed(events)), seed=3, config=config)

    assert first.input_hash == second.input_hash
    assert first.decision_hash == second.decision_hash
    assert [output.output_hash for output in first.outputs] == [
        output.output_hash for output in second.outputs
    ]


def test_timezone_variants_normalize_to_the_same_canonical_event() -> None:
    common = {
        "event_id": "01ARZ3NDEKTSV4RRFFQ69G5FAX",
        "org_id": ORG_ID,
        "incident_id": INCIDENT_ID,
        "source_id": "sensor-1",
        "external_id": "timezone-event",
        "event_type": "sensor.observation",
        "receipt_time_ms": 1_756_000_000_010,
        "sequence": 1,
        "payload": {"phenomenon": "water_level", "value": 1.2},
    }
    utc = event_from_mapping({**common, "source_time": "2025-08-23T00:00:00Z"})
    offset = event_from_mapping(
        {**common, "source_time": "2025-08-22T20:00:00-04:00"}
    )

    assert utc.source_time_ms == offset.source_time_ms
    assert utc.canonical_bytes() == offset.canonical_bytes()


def test_changed_algorithm_version_creates_distinct_lineage() -> None:
    event = _event(
        "01ARZ3NDEKTSV4RRFFQ69G5FAY",
        1_756_000_000_100,
        {"phenomenon": "water_level", "value": 1.2},
    )
    first = replay_events(event, seed=1, config=ReplayConfig(as_of_ms=1_756_000_001_000))
    changed = replay_events(
        event,
        seed=1,
        config=ReplayConfig(
            algorithm_version="fusion-replay-v2",
            as_of_ms=1_756_000_001_000,
        ),
    )

    assert first.lineage.lineage_hash != changed.lineage.lineage_hash
    assert first.decision_hash != changed.decision_hash


def test_float_tolerance_preserves_equivalent_decision_identity() -> None:
    first = replay_events(
        _event("01ARZ3NDEKTSV4RRFFQ69G5FBE", 1_756_000_000_100, {"phenomenon": "water_level", "value": 1.2}),
        config=ReplayConfig(as_of_ms=1_756_000_001_000, float_tolerance=1e-6),
    )
    second = replay_events(
        _event("01ARZ3NDEKTSV4RRFFQ69G5FBE", 1_756_000_000_100, {"phenomenon": "water_level", "value": 1.2000004}),
        config=ReplayConfig(as_of_ms=1_756_000_001_000, float_tolerance=1e-6),
    )

    assert first.input_hash != second.input_hash
    assert first.decision_hash == second.decision_hash


def test_mixed_scope_replay_abstains_without_outputs() -> None:
    first = _event("01ARZ3NDEKTSV4RRFFQ69G5FBG", 1_756_000_000_100, {"phenomenon": "water_level", "value": 1.2})
    second = RawEvent(
        **{**first.model_dump(), "event_id": "01ARZ3NDEKTSV4RRFFQ69G5FBH", "org_id": "other-org"}
    )
    result = replay_events([first, second], config=ReplayConfig(as_of_ms=1_756_000_001_000))

    assert result.outputs == ()
    assert any(error.error_type == "ReplayScopeError" for error in result.errors)


def test_malformed_mapping_is_retained_as_structured_error() -> None:
    result = replay_events({"event_id": "bad-event", "source_time_ms": -1})

    assert result.outputs == ()
    assert result.errors
    assert result.errors[0].stage == "input"


def test_hypothesis_evidence_is_bound_to_entity() -> None:
    hypothesis = _event(
        "01ARZ3NDEKTSV4RRFFQ69G5FBM",
        1_756_000_000_100,
        {"hypothesis_id": "01ARZ3NDEKTSV4RRFFQ69G5FBJ", "entity_type": "road_passability", "entity_id": "ROAD-1", "claim": "passable", "probability": 0.5},
    )
    observation = _event(
        "01ARZ3NDEKTSV4RRFFQ69G5FBN",
        1_756_000_000_200,
        {"phenomenon": "road_passability", "entity_id": "ROAD-2", "value": 0.9},
    )
    result = replay_events([hypothesis, observation], config=ReplayConfig(as_of_ms=1_756_000_001_000))
    output = next(item for item in result.outputs if item.output_type == "hypothesis")

    assert output.payload["supporting_event_ids"] == []
    assert output.payload["contradicting_event_ids"] == []


def test_conflicting_hypotheses_emit_an_explicit_abstention() -> None:
    events = [
        _event(
            "01ARZ3NDEKTSV4RRFFQ69G5FAZ",
            1_756_000_000_100,
            {
                "hypothesis_id": "01ARZ3NDEKTSV4RRFFQ69G5FBA",
                "entity_type": "road_passability",
                "entity_id": "ROAD-1",
                "claim": "passable",
                "probability": 0.7,
                "phenomenon": "road_passability",
            },
        ),
        _event(
            "01ARZ3NDEKTSV4RRFFQ69G5FBB",
            1_756_000_000_200,
            {
                "hypothesis_id": "01ARZ3NDEKTSV4RRFFQ69G5FBC",
                "entity_type": "road_passability",
                "entity_id": "ROAD-1",
                "claim": "impassable",
                "probability": 0.6,
                "phenomenon": "road_passability",
            },
        ),
    ]
    result = replay_events(events, seed=1, config=ReplayConfig(as_of_ms=1_756_000_001_000))
    conflicts = [output for output in result.outputs if output.output_type == "conflict"]

    assert conflicts
    assert all(output.payload["resolution"] in {"abstain", "declared_merge"} for output in conflicts)


def test_replay_persists_inputs_outputs_errors_and_lineage() -> None:
    event = _event(
        "01ARZ3NDEKTSV4RRFFQ69G5FBD",
        1_756_000_000_100,
        {"phenomenon": "water_level", "value": {"invalid": True}},
    )
    result = replay_events(event, seed=7, config=ReplayConfig(as_of_ms=1_756_000_001_000))
    changed_result = replay_events(
        event,
        seed=7,
        config=ReplayConfig(
            algorithm_version="fusion-replay-v2",
            as_of_ms=1_756_000_001_000,
        ),
    )
    db = SessionLocal()
    run = None
    changed_run = None
    try:
        run = persist_replay(db, result, org_id=ORG_ID, incident_id=INCIDENT_ID)
        changed_run = persist_replay(
            db,
            changed_result,
            org_id=ORG_ID,
            incident_id=INCIDENT_ID,
        )
        assert changed_run.id != run.id
        assert changed_run.lineage_hash != run.lineage_hash
        assert run.lineage_hash == result.lineage.lineage_hash
        assert run.float_tolerance == result.lineage.float_tolerance
        assert run.lineage == result.lineage.as_dict()
        assert db.execute(
            select(FusionReplayInputRecord).where(FusionReplayInputRecord.run_id == run.id)
        ).scalars().all()
        assert db.execute(
            select(FusionReplayOutputRecord).where(FusionReplayOutputRecord.run_id == run.id)
        ).scalars().all() == []
        assert db.execute(
            select(FusionReplayErrorRecord).where(FusionReplayErrorRecord.run_id == run.id)
        ).scalars().all()
    finally:
        run_ids = [item.id for item in (run, changed_run) if item is not None]
        db.execute(delete(FusionReplayErrorRecord).where(FusionReplayErrorRecord.run_id.in_(run_ids)))
        db.execute(delete(FusionReplayOutputRecord).where(FusionReplayOutputRecord.run_id.in_(run_ids)))
        db.execute(delete(FusionReplayInputRecord).where(FusionReplayInputRecord.run_id.in_(run_ids)))
        db.execute(delete(FusionReplayRun).where(FusionReplayRun.id.in_(run_ids)))
        db.commit()
        db.close()
