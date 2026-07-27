"""Cascading infrastructure dependency DAG — BFS cascade simulation.

Models infrastructure dependencies as a DAG. When a node fails, the cascade
propagates to dependent nodes via BFS:

- POWERED_BY (A POWERED_BY B): when B (target) fails, A (source) loses power.
- DEPENDS_ON (A DEPENDS_ON B): when B (target) fails, A (source) is affected.
- PROVIDES_ACCESS_TO (A PROVIDES_ACCESS_TO B): when A (source) fails,
  B (target) loses access.

Tracks cascade depth (1-indexed hops from failed node) and blast radius
(count of affected nodes including the failed node).

Example chains from SOTA spec §7.2:
1. Flooding -> substation failure -> tower power loss -> comms outage.
2. Flooding -> road closure -> hospital travel-time increase.
3. Shelter congestion -> sanitation/medical pressure.
"""

from __future__ import annotations

from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.relationships import GraphEdge
from app.twin.cascading_types import (
    ENTITY_TYPE_MAP,
    CascadeEdge,
    CascadeNode,
    CascadeResult,
    EdgeType,
    NodeType,
)


class CascadeSimulator:
    """Builds and simulates cascading failures over an infrastructure DAG.

    The simulator maintains an in-memory DAG of infrastructure nodes and their
    dependency edges. ``simulate_failure`` performs a BFS from the failed node
    to find all transitively-affected nodes.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, CascadeNode] = {}
        self._edges: list[CascadeEdge] = []
        # Reverse adjacency: target_id -> [source_ids] for POWERED_BY/DEPENDS_ON.
        self._dependents: dict[str, list[str]] = defaultdict(list)
        # Forward adjacency: source_id -> [target_ids] for PROVIDES_ACCESS_TO.
        self._provided_access: dict[str, list[str]] = defaultdict(list)

    def add_node(
        self,
        node_id: str,
        node_type: NodeType,
        name: str | None = None,
        properties: dict | None = None,
    ) -> None:
        """Add a node to the DAG. Re-adding with the same id updates it."""
        self._nodes[node_id] = CascadeNode(
            node_id=node_id,
            node_type=node_type,
            name=name,
            properties=properties,
        )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        properties: dict | None = None,
    ) -> None:
        """Add a directed dependency edge to the DAG.

        Both source and target nodes must already exist in the graph.
        """
        if source_id not in self._nodes:
            raise ValueError(f"Source node {source_id} not in graph")
        if target_id not in self._nodes:
            raise ValueError(f"Target node {target_id} not in graph")
        edge = CascadeEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            properties=properties,
        )
        self._edges.append(edge)
        if edge_type in (EdgeType.POWERED_BY, EdgeType.DEPENDS_ON):
            # When target fails, source is affected.
            self._dependents[target_id].append(source_id)
        elif edge_type == EdgeType.PROVIDES_ACCESS_TO:
            # When source fails, target is affected.
            self._provided_access[source_id].append(target_id)

    def build_from_graph_edges(
        self,
        db: Session,
        node_ids: set[str] | None = None,
    ) -> None:
        """Build the DAG from active GraphEdge rows in the database.

        Only edges with ``edge_type`` in {POWERED_BY, PROVIDES_ACCESS_TO,
        DEPENDS_ON} and ``valid_until IS NULL`` are loaded. If ``node_ids``
        is provided, only edges where both endpoints are in the set are
        loaded (incident-scoped filtering).
        """
        stmt = select(GraphEdge).where(
            GraphEdge.edge_type.in_([e.value for e in EdgeType]),
            GraphEdge.valid_until.is_(None),
        )
        edges = db.execute(stmt).scalars().all()
        for edge in edges:
            source_type = ENTITY_TYPE_MAP.get(edge.source_type)
            target_type = ENTITY_TYPE_MAP.get(edge.target_type)
            if source_type is None or target_type is None:
                continue
            if node_ids is not None:
                if (
                    edge.source_id not in node_ids
                    or edge.target_id not in node_ids
                ):
                    continue
            self.add_node(edge.source_id, source_type)
            self.add_node(edge.target_id, target_type)
            self.add_edge(
                edge.source_id,
                edge.target_id,
                EdgeType(edge.edge_type),
                edge.properties,
            )

    def simulate_failure(self, node_id: str) -> CascadeResult:
        """Simulate the failure of a single node via BFS cascade.

        Returns a :class:`CascadeResult` with affected nodes (the failed
        node at depth 1), max depth, and blast radius. Raises
        ``ValueError`` if the node is not in the graph.
        """
        if node_id not in self._nodes:
            raise ValueError(f"Node {node_id} not in graph")

        # 1-indexed depth: failed node is depth 1.
        affected: dict[str, int] = {node_id: 1}
        queue: deque[str] = deque([node_id])

        while queue:
            current = queue.popleft()
            current_depth = affected[current]
            for neighbor in self._affected_neighbors(current):
                if neighbor not in affected:
                    affected[neighbor] = current_depth + 1
                    queue.append(neighbor)

        return CascadeResult(
            failed_node_id=node_id,
            affected_nodes=affected,
            max_depth=max(affected.values()),
            blast_radius=len(affected),
        )

    def _affected_neighbors(self, node_id: str) -> list[str]:
        """Find nodes affected when this node fails.

        For POWERED_BY and DEPENDS_ON edges (A -> B): when B fails, A is
        affected (reverse traversal via ``_dependents``).

        For PROVIDES_ACCESS_TO edges (A -> B): when A fails, B is affected
        (forward traversal via ``_provided_access``).
        """
        return (
            self._dependents.get(node_id, [])
            + self._provided_access.get(node_id, [])
        )

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def get_node(self, node_id: str) -> CascadeNode | None:
        return self._nodes.get(node_id)


__all__ = ["CascadeSimulator"]
