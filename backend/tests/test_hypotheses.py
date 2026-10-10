"""Tests for contradictory hypotheses in the knowledge graph.

Creates 2 contradictory hypotheses for the same entity (H1: road passable,
H2: road impassable), both with supporting/contradicting evidence, and
verifies both are preserved. Also tests hypothesis status transitions.
"""

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.knowledge.graph import KnowledgeGraph
from app.models.enums import HypothesisStatus
from app.models.hypotheses import Hypothesis

ORG_ID = "org_test_hyp"
INCIDENT_ID = "inc_hyp_001"
ROAD_ID = "TESTROAD" + "0" * 18  # 26-char entity ID


@pytest.fixture(scope="module", autouse=True)
def _drop_age_graph():
    """Drop AGE graph after all tests in this module."""
    yield
    db = SessionLocal()
    try:
        db.execute(text("SET search_path = ag_catalog, public"))
        db.execute(
            text("SELECT * FROM ag_catalog.drop_graph(:n, true)"),
            {"n": f"g_{INCIDENT_ID.lower()}"},
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.execute(
            text("DELETE FROM hypotheses WHERE org_id = :oid"),
            {"oid": ORG_ID},
        )
        db.execute(
            text(
                "DELETE FROM graph_edges WHERE source_id = :id OR target_id = :id"
            ),
            {"id": ROAD_ID},
        )
        db.commit()
        db.close()


@pytest.fixture
def kg():
    """Create KnowledgeGraph with clean state."""
    db = SessionLocal()
    # Clean up any leftover data.
    db.execute(
        text("DELETE FROM hypotheses WHERE org_id = :oid"), {"oid": ORG_ID}
    )
    db.execute(
        text("DELETE FROM graph_edges WHERE source_id = :id OR target_id = :id"),
        {"id": ROAD_ID},
    )
    db.commit()

    kg = KnowledgeGraph(db, ORG_ID, INCIDENT_ID)
    kg.create_graph()
    try:
        yield kg
    finally:
        db.execute(
            text("DELETE FROM hypotheses WHERE org_id = :oid"), {"oid": ORG_ID}
        )
        db.execute(
            text("DELETE FROM graph_edges WHERE source_id = :id OR target_id = :id"),
            {"id": ROAD_ID},
        )
        db.commit()
        db.close()


def test_contradictory_hypotheses_preserved(kg):
    """Create 2 contradictory hypotheses for same entity, verify both exist.

    H1: "Road R1 is passable" (supported by satellite observation)
    H2: "Road R1 is impassable" (supported by citizen report of flooding)

    Both must be preserved — the system must NOT silently choose one.
    """
    h1_id = kg.add_hypothesis(
        entity_type="road_segment",
        entity_id=ROAD_ID,
        claim="Road R1 is passable for emergency vehicles",
        probability=0.7,
        supporting_evidence={
            "source": "satellite",
            "observation_id": "OBS001",
            "note": "Satellite imagery shows clear road surface",
        },
        contradicting_evidence={
            "source": "citizen_report",
            "note": "Unverified report of flooding",
        },
    )
    h2_id = kg.add_hypothesis(
        entity_type="road_segment",
        entity_id=ROAD_ID,
        claim="Road R1 is impassable due to flooding",
        probability=0.6,
        supporting_evidence={
            "source": "citizen_report",
            "observation_id": "OBS002",
            "note": "Multiple reports of water on road",
        },
        contradicting_evidence={
            "source": "satellite",
            "note": "Satellite imagery shows clear surface",
        },
    )

    assert h1_id != h2_id
    assert len(h1_id) == 26
    assert len(h2_id) == 26

    # Both hypotheses exist in the database.
    h1 = kg.db.get(Hypothesis, h1_id)
    h2 = kg.db.get(Hypothesis, h2_id)
    assert h1 is not None
    assert h2 is not None

    # Both are for the same entity.
    assert h1.entity_id == ROAD_ID
    assert h2.entity_id == ROAD_ID
    assert h1.entity_type == "road_segment"
    assert h2.entity_type == "road_segment"

    # Claims are contradictory.
    assert "passable" in h1.claim
    assert "impassable" in h2.claim

    # Both have supporting and contradicting evidence.
    assert h1.supporting_evidence is not None
    assert h1.contradicting_evidence is not None
    assert h2.supporting_evidence is not None
    assert h2.contradicting_evidence is not None

    # Both are active (neither was discarded).
    assert h1.status == HypothesisStatus.active
    assert h2.status == HypothesisStatus.active

    # get_hypotheses returns both.
    all_hyps = kg.get_hypotheses("road_segment", ROAD_ID)
    assert len(all_hyps) == 2
    hyp_ids = {h.id for h in all_hyps}
    assert hyp_ids == {h1_id, h2_id}

    # Link observations to hypotheses via graph edges.
    obs1_id = "TESTOBS1" + "0" * 18  # 26 chars
    obs2_id = "TESTOBS2" + "0" * 18
    edge1 = kg.link_observation(obs1_id, h1_id, "supports")
    edge2 = kg.link_observation(obs2_id, h2_id, "supports")
    assert edge1 is not None
    assert edge2 is not None

    # Verify edges exist.
    edge_count = kg.db.execute(
        text(
            "SELECT count(*) FROM graph_edges "
            "WHERE target_id = :h1 OR target_id = :h2"
        ),
        {"h1": h1_id, "h2": h2_id},
    ).scalar()
    assert edge_count == 2


def test_hypothesis_status_transitions(kg):
    """Create hypothesis, update status to resolved, verify transition."""
    hid = kg.add_hypothesis(
        entity_type="road_segment",
        entity_id=ROAD_ID,
        claim="Road R1 status is being verified",
        probability=0.5,
    )

    h = kg.db.get(Hypothesis, hid)
    assert h is not None
    assert h.status == HypothesisStatus.active

    # Transition: active -> resolved
    kg.update_hypothesis_status(hid, HypothesisStatus.resolved)

    h = kg.db.get(Hypothesis, hid)
    assert h is not None
    assert h.status == HypothesisStatus.resolved
    assert h.updated_at >= h.created_at

    # Transition: resolved -> superseded (another hypothesis supersedes it)
    kg.update_hypothesis_status(hid, HypothesisStatus.superseded)
    h = kg.db.get(Hypothesis, hid)
    assert h.status == HypothesisStatus.superseded
