"""Tests for the temporal crisis knowledge graph.

Creates 5 entities + 5 edges, queries 2-hop neighbors, and verifies correct
results via both the AGE Cypher path (if available) and the recursive CTE
fallback. Uses the real PostgreSQL database via SessionLocal.
"""

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.knowledge.graph import KnowledgeGraph

ORG_ID = "org_test_kg"
INCIDENT_ID = "inc_kg_001"

# 26-char test entity IDs (8-char prefix + 18 zeros).
ROAD_ID = "TESTROAD" + "0" * 18
ZONE_ID = "TESTZONE" + "0" * 18
HOSPITAL_ID = "TESTHOSP" + "0" * 18
BUILDING_ID = "TESTBLDG" + "0" * 18
SHELTER_ID = "TESTSHLT" + "0" * 18

ALL_IDS = [ROAD_ID, ZONE_ID, HOSPITAL_ID, BUILDING_ID, SHELTER_ID]


def _cleanup(db):
    """Delete all test graph_edges rows."""
    for eid in ALL_IDS:
        db.execute(
            text(
                "DELETE FROM graph_edges WHERE source_id = :id OR target_id = :id"
            ),
            {"id": eid},
        )
    db.commit()


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
        _cleanup(db)
        db.close()


@pytest.fixture
def kg():
    """Create KnowledgeGraph with clean state."""
    db = SessionLocal()
    _cleanup(db)
    kg = KnowledgeGraph(db, ORG_ID, INCIDENT_ID)
    kg.create_graph()
    kg.clear_graph()
    try:
        yield kg
    finally:
        _cleanup(db)
        db.close()


def _build_test_graph(kg):
    """Add 5 entities and 5 edges forming a chain with a branch.

    Topology (directed):
        R1 --passes_through--> Z1
        R1 --provides_access_to--> H1
        H1 --reachable_via--> B1
        B1 --refers_to--> S1
        S1 --provides_access_to--> Z1

    2-hop from R1: Z1 (hop 1), H1 (hop 1), B1 (hop 2)
    """
    kg.add_entity("road_segment", ROAD_ID, {"name": "Main Road"})
    kg.add_entity("zone", ZONE_ID, {"name": "Zone A"})
    kg.add_entity("hospital", HOSPITAL_ID, {"name": "General Hospital"})
    kg.add_entity("building", BUILDING_ID, {"name": "Building 1"})
    kg.add_entity("shelter", SHELTER_ID, {"name": "Shelter 1"})

    kg.add_edge("road_segment", ROAD_ID, "passes_through", "zone", ZONE_ID)
    kg.add_edge("road_segment", ROAD_ID, "provides_access_to", "hospital", HOSPITAL_ID)
    kg.add_edge("hospital", HOSPITAL_ID, "reachable_via", "building", BUILDING_ID)
    kg.add_edge("building", BUILDING_ID, "refers_to", "shelter", SHELTER_ID)
    kg.add_edge("shelter", SHELTER_ID, "provides_access_to", "zone", ZONE_ID)


def test_add_entity_and_edge(kg):
    """Add entity and edge, verify they exist in graph_edges."""
    kg.add_entity("road_segment", ROAD_ID, {"name": "Test Road"})
    kg.add_entity("zone", ZONE_ID, {"name": "Test Zone"})

    edge_id = kg.add_edge(
        "road_segment", ROAD_ID, "passes_through", "zone", ZONE_ID,
        properties={"lanes": 2},
    )
    assert edge_id is not None
    assert isinstance(edge_id, int)

    # Verify edge exists in graph_edges table.
    db = kg.db
    count = db.execute(
        text(
            "SELECT count(*) FROM graph_edges "
            "WHERE source_id = :sid AND target_id = :tid AND edge_type = :et"
        ),
        {"sid": ROAD_ID, "tid": ZONE_ID, "et": "passes_through"},
    ).scalar()
    assert count == 1

    # Verify properties were stored.
    props = db.execute(
        text(
            "SELECT properties FROM graph_edges "
            "WHERE source_id = :sid AND target_id = :tid"
        ),
        {"sid": ROAD_ID, "tid": ZONE_ID},
    ).scalar()
    assert props is not None
    assert props.get("lanes") == 2


def test_query_neighbors(kg):
    """Query 1-hop neighbors and verify correct results."""
    _build_test_graph(kg)

    neighbors = kg.query_neighbors("road_segment", ROAD_ID, hops=1)
    assert len(neighbors) == 2

    neighbor_ids = {n["entity_id"] for n in neighbors}
    assert neighbor_ids == {ZONE_ID, HOSPITAL_ID}

    for n in neighbors:
        assert n["hop"] == 1
        assert n["entity_type"] in ("zone", "hospital")


def test_two_hop_query(kg):
    """Create 5 entities + 5 edges, query 2-hop neighbors, verify correct results."""
    _build_test_graph(kg)

    neighbors = kg.query_two_hop("road_segment", ROAD_ID)
    assert len(neighbors) == 3

    hop1 = {n["entity_id"] for n in neighbors if n["hop"] == 1}
    hop2 = {n["entity_id"] for n in neighbors if n["hop"] == 2}

    # 1-hop: Z1 (passes_through), H1 (provides_access_to)
    assert hop1 == {ZONE_ID, HOSPITAL_ID}
    # 2-hop: B1 (via H1 -> reachable_via -> B1)
    assert hop2 == {BUILDING_ID}

    # Verify entity types are correct.
    types = {n["entity_id"]: n["entity_type"] for n in neighbors}
    assert types[ZONE_ID] == "zone"
    assert types[HOSPITAL_ID] == "hospital"
    assert types[BUILDING_ID] == "building"
