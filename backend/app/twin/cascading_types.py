"""Cascading infrastructure dependency types — enums and dataclasses.

Models infrastructure dependencies as a DAG. Nodes: substations, cell towers,
hospitals, shelters, roads, bridges, water supply, sewage. Edges: POWERED_BY,
PROVIDES_ACCESS_TO, DEPENDS_ON. Used by CascadeSimulator for BFS cascade
simulation when a node fails.

Edge direction semantics:
- POWERED_BY (A POWERED_BY B): A is powered by B. When B fails, A is affected.
- DEPENDS_ON (A DEPENDS_ON B): A depends on B. When B fails, A is affected.
- PROVIDES_ACCESS_TO (A PROVIDES_ACCESS_TO B): A provides access to B.
  When A fails, B loses access.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class NodeType(str, enum.Enum):
    """Infrastructure node types in the cascade DAG."""

    SUBSTATION = "substation"
    CELL_TOWER = "cell_tower"
    HOSPITAL = "hospital"
    SHELTER = "shelter"
    ROAD = "road"
    BRIDGE = "bridge"
    WATER_SUPPLY = "water_supply"
    SEWAGE = "sewage"


class EdgeType(str, enum.Enum):
    """Directed dependency edge types between infrastructure nodes."""

    POWERED_BY = "POWERED_BY"
    PROVIDES_ACCESS_TO = "PROVIDES_ACCESS_TO"
    DEPENDS_ON = "DEPENDS_ON"


@dataclass(frozen=True, slots=True)
class CascadeNode:
    """A node in the infrastructure cascade DAG."""

    node_id: str
    node_type: NodeType
    name: str | None = None
    properties: dict | None = None


@dataclass(frozen=True, slots=True)
class CascadeEdge:
    """A directed dependency edge between two infrastructure nodes."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict | None = None


@dataclass(frozen=True, slots=True)
class CascadeResult:
    """Result of a cascade simulation from a single node failure.

    Depths are 1-indexed: the failed node is at depth 1, direct dependents
    at depth 2, and so on. Blast radius includes the failed node itself.
    """

    failed_node_id: str
    affected_nodes: dict[str, int]
    max_depth: int
    blast_radius: int


# Maps GraphEdge.source_type/target_type strings to NodeType enum values.
ENTITY_TYPE_MAP: dict[str, NodeType] = {
    "power_substation": NodeType.SUBSTATION,
    "cell_tower": NodeType.CELL_TOWER,
    "hospital": NodeType.HOSPITAL,
    "shelter": NodeType.SHELTER,
    "road_segment": NodeType.ROAD,
    "bridge": NodeType.BRIDGE,
    "water_supply": NodeType.WATER_SUPPLY,
    "sewage": NodeType.SEWAGE,
}


__all__ = [
    "ENTITY_TYPE_MAP",
    "CascadeEdge",
    "CascadeNode",
    "CascadeResult",
    "EdgeType",
    "NodeType",
]
