"""Tests for the cascading infrastructure dependency DAG (T24).

Builds a 10-node, 15-edge DAG and verifies BFS cascade simulation:
- Substation failure -> cell tower (depth 2) -> hospital (depth 3),
  blast radius = 4.
- Road closure cascade via PROVIDES_ACCESS_TO.
- Shelter congestion cascade via DEPENDS_ON.
- No cascade when no dependents.
- DB-backed build_from_graph_edges.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.lib.time import now_ms
from app.models.relationships import GraphEdge
from app.twin.cascading import CascadeSimulator
from app.twin.cascading_types import EdgeType, NodeType

# Test node IDs (26-char ULID-like for DB compatibility: 8-char prefix + 18 zeros).
SUBSTATION_1 = "SUBSTA01" + "0" * 18
CELL_TOWER_1 = "CELLT001" + "0" * 18
CELL_TOWER_2 = "CELLT002" + "0" * 18
HOSPITAL_1 = "HOSPT001" + "0" * 18
HOSPITAL_2 = "HOSPT002" + "0" * 18
SHELTER_1 = "SHELT001" + "0" * 18
ROAD_1 = "ROAD0001" + "0" * 18
BRIDGE_1 = "BRIDG001" + "0" * 18
WATER_SUPPLY_1 = "WATER001" + "0" * 18
SEWAGE_1 = "SEWAG001" + "0" * 18

ALL_NODE_IDS = {
    SUBSTATION_1, CELL_TOWER_1, CELL_TOWER_2, HOSPITAL_1, HOSPITAL_2,
    SHELTER_1, ROAD_1, BRIDGE_1, WATER_SUPPLY_1, SEWAGE_1,
}


def _build_test_graph(sim: CascadeSimulator) -> None:
    """Build a 10-node, 15-edge infrastructure DAG.

    Topology (directed dependency edges):
        cell_tower_1 POWERED_BY substation_1
        hospital_1 DEPENDS_ON cell_tower_1
        shelter_1 DEPENDS_ON cell_tower_1
        road_1 PROVIDES_ACCESS_TO hospital_1
        road_1 PROVIDES_ACCESS_TO shelter_1
        bridge_1 PROVIDES_ACCESS_TO hospital_1
        hospital_1 DEPENDS_ON water_supply_1
        hospital_1 DEPENDS_ON sewage_1
        shelter_1 DEPENDS_ON water_supply_1
        shelter_1 DEPENDS_ON sewage_1
        hospital_2 DEPENDS_ON cell_tower_2
        hospital_2 DEPENDS_ON water_supply_1
        bridge_1 DEPENDS_ON road_1
        hospital_1 DEPENDS_ON shelter_1
        road_1 PROVIDES_ACCESS_TO hospital_2
    """
    sim.add_node(SUBSTATION_1, NodeType.SUBSTATION, name="Substation 1")
    sim.add_node(CELL_TOWER_1, NodeType.CELL_TOWER, name="Cell Tower 1")
    sim.add_node(CELL_TOWER_2, NodeType.CELL_TOWER, name="Cell Tower 2")
    sim.add_node(HOSPITAL_1, NodeType.HOSPITAL, name="Hospital 1")
    sim.add_node(HOSPITAL_2, NodeType.HOSPITAL, name="Hospital 2")
    sim.add_node(SHELTER_1, NodeType.SHELTER, name="Shelter 1")
    sim.add_node(ROAD_1, NodeType.ROAD, name="Road 1")
    sim.add_node(BRIDGE_1, NodeType.BRIDGE, name="Bridge 1")
    sim.add_node(WATER_SUPPLY_1, NodeType.WATER_SUPPLY, name="Water Supply 1")
    sim.add_node(SEWAGE_1, NodeType.SEWAGE, name="Sewage 1")

    # Chain 1: substation -> cell_tower -> hospital/shelter (power + comms).
    sim.add_edge(CELL_TOWER_1, SUBSTATION_1, EdgeType.POWERED_BY)
    sim.add_edge(HOSPITAL_1, CELL_TOWER_1, EdgeType.DEPENDS_ON)
    sim.add_edge(SHELTER_1, CELL_TOWER_1, EdgeType.DEPENDS_ON)
    sim.add_edge(HOSPITAL_1, SHELTER_1, EdgeType.DEPENDS_ON)

    # Chain 2: road -> hospital/shelter/hospital_2 (access).
    sim.add_edge(ROAD_1, HOSPITAL_1, EdgeType.PROVIDES_ACCESS_TO)
    sim.add_edge(ROAD_1, SHELTER_1, EdgeType.PROVIDES_ACCESS_TO)
    sim.add_edge(ROAD_1, HOSPITAL_2, EdgeType.PROVIDES_ACCESS_TO)
    sim.add_edge(BRIDGE_1, HOSPITAL_1, EdgeType.PROVIDES_ACCESS_TO)
    sim.add_edge(BRIDGE_1, ROAD_1, EdgeType.DEPENDS_ON)

    # Chain 3: hospital/shelter -> water_supply/sewage (sanitation).
    sim.add_edge(HOSPITAL_1, WATER_SUPPLY_1, EdgeType.DEPENDS_ON)
    sim.add_edge(HOSPITAL_1, SEWAGE_1, EdgeType.DEPENDS_ON)
    sim.add_edge(SHELTER_1, WATER_SUPPLY_1, EdgeType.DEPENDS_ON)
    sim.add_edge(SHELTER_1, SEWAGE_1, EdgeType.DEPENDS_ON)
    sim.add_edge(HOSPITAL_2, CELL_TOWER_2, EdgeType.DEPENDS_ON)
    sim.add_edge(HOSPITAL_2, WATER_SUPPLY_1, EdgeType.DEPENDS_ON)


@pytest.fixture
def sim() -> CascadeSimulator:
    """Build the test DAG."""
    s = CascadeSimulator()
    _build_test_graph(s)
    return s


def test_graph_has_10_nodes_15_edges(sim: CascadeSimulator) -> None:
    """DAG has exactly 10 nodes and 15 edges."""
    assert sim.node_count == 10
    assert sim.edge_count == 15


def test_substation_cascade(sim: CascadeSimulator) -> None:
    """Substation failure cascades to cell tower (depth 2) + hospital (depth 3).

    Blast radius = 4 affected nodes. Verifies SOTA spec §7.2 chain 1:
    flooding -> substation failure -> tower power loss -> comms outage.
    """
    result = sim.simulate_failure(SUBSTATION_1)

    assert result.failed_node_id == SUBSTATION_1
    assert result.blast_radius == 4
    assert result.max_depth == 3

    # Substation at depth 1 (failed node).
    assert result.affected_nodes[SUBSTATION_1] == 1
    # Cell tower at depth 2 (1 hop via POWERED_BY).
    assert result.affected_nodes[CELL_TOWER_1] == 2
    # Hospital at depth 3 (2 hops via DEPENDS_ON cell_tower_1).
    assert result.affected_nodes[HOSPITAL_1] == 3
    # Shelter at depth 3 (2 hops via DEPENDS_ON cell_tower_1).
    assert result.affected_nodes[SHELTER_1] == 3

    # Unrelated nodes are NOT affected.
    for unaffected in (
        CELL_TOWER_2, HOSPITAL_2, ROAD_1, BRIDGE_1,
        WATER_SUPPLY_1, SEWAGE_1,
    ):
        assert unaffected not in result.affected_nodes


def test_road_closure_cascade(sim: CascadeSimulator) -> None:
    """Road closure cascades to hospitals and shelter via PROVIDES_ACCESS_TO.

    Verifies SOTA spec §7.2 chain 2: flooding -> road closure ->
    hospital travel-time increase.
    """
    result = sim.simulate_failure(ROAD_1)

    assert result.failed_node_id == ROAD_1
    # road_1 + hospital_1 + shelter_1 + hospital_2 + bridge_1.
    assert result.blast_radius == 5
    assert result.max_depth == 2

    assert result.affected_nodes[ROAD_1] == 1
    # PROVIDES_ACCESS_TO: hospital_1, shelter_1, hospital_2 at depth 2.
    assert result.affected_nodes[HOSPITAL_1] == 2
    assert result.affected_nodes[SHELTER_1] == 2
    assert result.affected_nodes[HOSPITAL_2] == 2
    # bridge_1 DEPENDS_ON road_1: affected at depth 2.
    assert result.affected_nodes[BRIDGE_1] == 2

    # Unrelated nodes are NOT affected.
    for unaffected in (
        SUBSTATION_1, CELL_TOWER_1, CELL_TOWER_2,
        WATER_SUPPLY_1, SEWAGE_1,
    ):
        assert unaffected not in result.affected_nodes


def test_shelter_congestion_cascade(sim: CascadeSimulator) -> None:
    """Shelter congestion cascades to hospital via DEPENDS_ON.

    Verifies SOTA spec §7.2 chain 3: shelter congestion -> sanitation/medical
    pressure -> secondary evacuation demand. hospital_1 depends on shelter_1
    for patient overflow, so shelter failure cascades to hospital.
    """
    result = sim.simulate_failure(SHELTER_1)

    assert result.failed_node_id == SHELTER_1
    assert result.blast_radius == 2
    assert result.max_depth == 2

    assert result.affected_nodes[SHELTER_1] == 1
    # hospital_1 DEPENDS_ON shelter_1: affected at depth 2.
    assert result.affected_nodes[HOSPITAL_1] == 2

    # No further cascade: nothing depends on hospital_1.
    for unaffected in (
        SUBSTATION_1, CELL_TOWER_1, CELL_TOWER_2, HOSPITAL_2,
        ROAD_1, BRIDGE_1, WATER_SUPPLY_1, SEWAGE_1,
    ):
        assert unaffected not in result.affected_nodes


def test_no_cascade_when_no_dependents(sim: CascadeSimulator) -> None:
    """Hospital failure has no cascade: nothing depends on hospital_1.

    hospital_1 is the target of PROVIDES_ACCESS_TO edges (road/bridge provide
    access to it), but PROVIDES_ACCESS_TO cascades source -> target, not
    target -> source. No DEPENDS_ON or POWERED_BY edges point to hospital_1,
    so its failure affects only itself.
    """
    result = sim.simulate_failure(HOSPITAL_1)

    assert result.failed_node_id == HOSPITAL_1
    assert result.blast_radius == 1
    assert result.max_depth == 1
    assert result.affected_nodes == {HOSPITAL_1: 1}


def test_simulate_failure_unknown_node_raises(sim: CascadeSimulator) -> None:
    """Simulating failure of a node not in the graph raises ValueError."""
    with pytest.raises(ValueError, match="not in graph"):
        sim.simulate_failure("nonexistent_node_id")


def test_add_edge_unknown_source_raises() -> None:
    """Adding an edge with an unknown source node raises ValueError."""
    s = CascadeSimulator()
    s.add_node("target_node", NodeType.HOSPITAL)
    with pytest.raises(ValueError, match="Source node"):
        s.add_edge("unknown_source", "target_node", EdgeType.DEPENDS_ON)


# ---------------------------------------------------------------------------
# DB-backed tests (use real PostgreSQL via SessionLocal).
# ---------------------------------------------------------------------------


def _cleanup_db(db) -> None:
    """Delete all test graph_edges rows."""
    for eid in ALL_NODE_IDS:
        db.execute(
            text(
                "DELETE FROM graph_edges WHERE source_id = :id OR target_id = :id"
            ),
            {"id": eid},
        )
    db.commit()


@pytest.fixture
def db():
    """Yield a DB session and clean up test rows after each test."""
    session = SessionLocal()
    _cleanup_db(session)
    try:
        yield session
    finally:
        _cleanup_db(session)
        session.close()


def test_build_from_graph_edges(db) -> None:
    """Build DAG from GraphEdge table and verify cascade simulation.

    Inserts 3 edges (substation -> cell_tower -> hospital/shelter) into
    graph_edges, builds the DAG via build_from_graph_edges, and verifies
    the substation cascade reaches the expected nodes.
    """
    ts = now_ms()
    db_edges = [
        GraphEdge(
            source_type="cell_tower", source_id=CELL_TOWER_1,
            edge_type="POWERED_BY", target_type="power_substation",
            target_id=SUBSTATION_1, valid_from=ts,
        ),
        GraphEdge(
            source_type="hospital", source_id=HOSPITAL_1,
            edge_type="DEPENDS_ON", target_type="cell_tower",
            target_id=CELL_TOWER_1, valid_from=ts,
        ),
        GraphEdge(
            source_type="shelter", source_id=SHELTER_1,
            edge_type="DEPENDS_ON", target_type="cell_tower",
            target_id=CELL_TOWER_1, valid_from=ts,
        ),
    ]
    for edge in db_edges:
        db.add(edge)
    db.commit()

    sim = CascadeSimulator()
    sim.build_from_graph_edges(
        db, node_ids={SUBSTATION_1, CELL_TOWER_1, HOSPITAL_1, SHELTER_1}
    )

    assert sim.node_count == 4
    assert sim.edge_count == 3

    result = sim.simulate_failure(SUBSTATION_1)
    assert result.blast_radius == 4
    assert result.max_depth == 3
    assert result.affected_nodes[SUBSTATION_1] == 1
    assert result.affected_nodes[CELL_TOWER_1] == 2
    assert result.affected_nodes[HOSPITAL_1] == 3
    assert result.affected_nodes[SHELTER_1] == 3
