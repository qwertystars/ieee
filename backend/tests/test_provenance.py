"""Tests for provenance & auditability (T49).

Test cases:
  1. test_full_chain — optimizer produces recommendation, provenance chain has all 10 fields
  2. test_tamper_detection — tampering a field breaks hash-chain verification
  3. test_get_provenance_returns_full_chain — get_provenance returns all entries in order
  4. test_hash_chain_verifies — verify_chain returns True for intact chain
  5. test_missing_field_rejected — ProvenanceInput rejects None fields

Verification command:
    docker compose run --rm -e PYTHONPATH=/app backend sh -c \
        "pip install pytest -q && python -m pytest tests/test_provenance.py -q"
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.audit.provenance import ProvenanceChain
from app.audit.provenance_types import (
    REQUIRED_FIELDS,
    DecisionProvenance,
    ProvenanceInput,
)
from app.db import SessionLocal
from app.optimizer.engine import EmergencyResponseOptimizer
from app.optimizer.optimizer_types import (
    OptimizerInput,
    Responder,
    RoadArc,
    ScenarioLoss,
    Shelter,
    Task,
    Zone,
)

ORG_ID = "org_test_prov"
REC_ID = "rec_test_001"


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Yield a session backed by the real Postgres DB and clean up after."""
    session = SessionLocal()
    session.execute(
        delete(DecisionProvenance).where(DecisionProvenance.org_id == ORG_ID)
    )
    session.commit()
    try:
        yield session
    finally:
        session.execute(
            delete(DecisionProvenance).where(DecisionProvenance.org_id == ORG_ID)
        )
        session.commit()
        session.close()


def _optimizer_input() -> OptimizerInput:
    """Standard 3-zone, 4-responder, 3-scenario optimizer input (from T26 tests)."""
    return OptimizerInput(
        zones=(
            Zone(id="z0", demand=1, vulnerable=True, c_min=1),
            Zone(id="z1", demand=1, vulnerable=False),
            Zone(id="z2", demand=1, vulnerable=False),
        ),
        responders=(
            Responder(id="r0", skills=frozenset({"medical", "search"}), vehicle_class="ambulance"),
            Responder(id="r1", skills=frozenset({"medical"}), vehicle_class="ambulance"),
            Responder(id="r2", skills=frozenset({"search", "evacuation"}), vehicle_class="boat"),
            Responder(id="r3", skills=frozenset({"evacuation"}), vehicle_class="high_clearance"),
        ),
        tasks=(
            Task(id="t0", zone_id="z0", required_skill="medical", harm_if_unserved=100.0),
            Task(id="t1", zone_id="z1", required_skill="search", harm_if_unserved=50.0),
            Task(id="t2", zone_id="z2", required_skill="evacuation", harm_if_unserved=75.0),
        ),
        scenarios=(
            ScenarioLoss(probability=0.3, harm_multiplier=1.0),
            ScenarioLoss(probability=0.4, harm_multiplier=1.5),
            ScenarioLoss(probability=0.3, harm_multiplier=0.8),
        ),
        road_arcs=(
            RoadArc(from_node=0, to_node=1, vehicle_classes=frozenset({"ambulance", "boat", "high_clearance"})),
            RoadArc(from_node=0, to_node=2, vehicle_classes=frozenset({"ambulance", "boat", "high_clearance"})),
            RoadArc(from_node=0, to_node=3, vehicle_classes=frozenset({"boat"})),
        ),
        shelters=(Shelter(id="z2", capacity=10, initial_occupancy=0),),
        alpha=0.95,
        lambda_risk=1.0,
        max_solve_seconds=30.0,
    )


def _build_provenance_from_optimizer(inp: OptimizerInput, result) -> ProvenanceInput:
    """Construct a ProvenanceInput from optimizer input + result."""
    return ProvenanceInput(
        input_observation_ids=["obs_001", "obs_002", "obs_003"],
        data_versions={"observations": "v1", "entities": "v1", "zones": "v1"},
        model_versions={"optimizer": "v1.0", "risk_model": "v2.1"},
        optimization_parameters={
            "alpha": inp.alpha,
            "lambda_risk": inp.lambda_risk,
            "max_solve_seconds": inp.max_solve_seconds,
            "objective_value": result.objective_value,
            "expected_harm": result.expected_harm,
            "cvar": result.cvar,
            "operational_cost": result.operational_cost,
        },
        scenario_set=[
            {"probability": s.probability, "harm_multiplier": s.harm_multiplier}
            for s in inp.scenarios
        ],
        constraints={
            "skill": True,
            "availability": True,
            "routing": True,
            "capacity": True,
            "shift": True,
            "fairness": True,
            "precedence": True,
        },
        generated_alternatives=[
            {"responder_id": a.responder_id, "task_id": a.task_id, "start_time": a.start_time}
            for a in result.assignments
        ],
        operator_decision={},
        override_reason="",
        execution_outcome={},
    )


# ── Tests ───────────────────────────────────────────────────────────────────


def test_full_chain(db):
    """Optimizer produces recommendation; provenance chain has all 10 fields."""
    inp = _optimizer_input()
    result = EmergencyResponseOptimizer(inp).solve()
    assert result.status in ("optimal", "feasible"), f"expected feasible, got {result.status}"

    provenance = _build_provenance_from_optimizer(inp, result)
    entry = ProvenanceChain.record_decision(db, ORG_ID, REC_ID, provenance)

    # Entry has all 10 provenance fields populated.
    for field_name in REQUIRED_FIELDS:
        assert hasattr(entry, field_name), f"missing field: {field_name}"
        assert getattr(entry, field_name) is not None, f"field is None: {field_name}"

    # Hash-chain fields are populated.
    assert entry.prev_hash == ""  # first entry has empty prev_hash
    assert entry.hash  # non-empty hash
    assert len(entry.id) == 26  # ULID

    # Chain verifies.
    assert ProvenanceChain.verify_chain(db, ORG_ID, REC_ID) is True


def test_tamper_detection(db):
    """Tampering a provenance field breaks hash-chain verification."""
    inp = _optimizer_input()
    result = EmergencyResponseOptimizer(inp).solve()
    provenance = _build_provenance_from_optimizer(inp, result)

    ProvenanceChain.record_decision(db, ORG_ID, REC_ID, provenance)
    assert ProvenanceChain.verify_chain(db, ORG_ID, REC_ID) is True

    # Tamper: change override_reason without updating the hash.
    entry = (
        db.query(DecisionProvenance)
        .filter(DecisionProvenance.org_id == ORG_ID)
        .one()
    )
    entry.override_reason = "tampered"  # was ""
    db.commit()

    result_verify = ProvenanceChain.verify_chain(db, ORG_ID, REC_ID)
    assert result_verify is not True, "tamper should break chain"
    assert result_verify == 0, f"expected index 0, got {result_verify}"


def test_get_provenance_returns_full_chain(db):
    """get_provenance returns all entries in chronological order."""
    rec_id = "rec_chain_002"

    # Record two entries for the same recommendation.
    prov1 = ProvenanceInput(
        input_observation_ids=["obs_a"],
        data_versions={"v": "1"},
        model_versions={"opt": "v1"},
        optimization_parameters={"alpha": 0.95},
        scenario_set=[{"probability": 0.5}],
        constraints={"skill": True},
        generated_alternatives=[{"r": "r0", "t": "t0"}],
        operator_decision={},
        override_reason="",
        execution_outcome={},
    )
    entry1 = ProvenanceChain.record_decision(db, ORG_ID, rec_id, prov1)

    prov2 = ProvenanceInput(
        input_observation_ids=["obs_a"],
        data_versions={"v": "1"},
        model_versions={"opt": "v1"},
        optimization_parameters={"alpha": 0.95},
        scenario_set=[{"probability": 0.5}],
        constraints={"skill": True},
        generated_alternatives=[{"r": "r0", "t": "t0"}],
        operator_decision={"action": "approved"},
        override_reason="operator approved initial plan",
        execution_outcome={"status": "executed"},
    )
    entry2 = ProvenanceChain.record_decision(db, ORG_ID, rec_id, prov2)

    chain = ProvenanceChain.get_provenance(db, ORG_ID, rec_id)
    assert len(chain) == 2, f"expected 2 entries, got {len(chain)}"
    assert chain[0].id == entry1.id, "first entry should be oldest"
    assert chain[1].id == entry2.id, "second entry should be newest"

    # Chain links: entry2.prev_hash == entry1.hash
    assert chain[1].prev_hash == chain[0].hash, "chain link broken"
    assert chain[0].prev_hash == "", "first entry should have empty prev_hash"

    # Both entries have all 10 fields.
    for entry in chain:
        for field_name in REQUIRED_FIELDS:
            assert getattr(entry, field_name) is not None, f"field is None: {field_name}"


def test_hash_chain_verifies(db):
    """verify_chain returns True for an intact multi-entry chain."""
    rec_id = "rec_verify_003"

    for i in range(3):
        prov = ProvenanceInput(
            input_observation_ids=[f"obs_{i}"],
            data_versions={"v": str(i)},
            model_versions={"opt": "v1"},
            optimization_parameters={"alpha": 0.95},
            scenario_set=[{"probability": 0.5}],
            constraints={"skill": True},
            generated_alternatives=[],
            operator_decision={},
            override_reason="",
            execution_outcome={},
        )
        ProvenanceChain.record_decision(db, ORG_ID, rec_id, prov)

    chain = ProvenanceChain.get_provenance(db, ORG_ID, rec_id)
    assert len(chain) == 3, f"expected 3 entries, got {len(chain)}"

    # Chain links are correct.
    assert chain[0].prev_hash == ""
    assert chain[1].prev_hash == chain[0].hash
    assert chain[2].prev_hash == chain[1].hash

    # Full chain verifies.
    assert ProvenanceChain.verify_chain(db, ORG_ID, rec_id) is True


def test_missing_field_rejected(db):
    """ProvenanceInput rejects None fields (missing field rejected)."""
    # Building a ProvenanceInput with a None field raises ValueError.
    with pytest.raises(ValueError, match="provenance field 'override_reason'"):
        ProvenanceInput(
            input_observation_ids=["obs"],
            data_versions={"v": "1"},
            model_versions={"opt": "v1"},
            optimization_parameters={"alpha": 0.95},
            scenario_set=[{"probability": 0.5}],
            constraints={"skill": True},
            generated_alternatives=[],
            operator_decision={},
            override_reason=None,  # missing
            execution_outcome={},
        )

    # A second field rejection check.
    with pytest.raises(ValueError, match="provenance field 'input_observation_ids'"):
        ProvenanceInput(
            input_observation_ids=None,  # missing
            data_versions={"v": "1"},
            model_versions={"opt": "v1"},
            optimization_parameters={"alpha": 0.95},
            scenario_set=[{"probability": 0.5}],
            constraints={"skill": True},
            generated_alternatives=[],
            operator_decision={},
            override_reason="",
            execution_outcome={},
        )

    # Nothing was written to the DB.
    chain = ProvenanceChain.get_provenance(db, ORG_ID, "rec_reject_004")
    assert chain == [], "no entries should exist for rejected inputs"
