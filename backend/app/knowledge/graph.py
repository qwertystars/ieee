"""Temporal crisis knowledge graph — entities, relationships, contradictory hypotheses.

Uses Apache AGE for Cypher queries when available, with a recursive CTE fallback
over the graph_edges table. AGE runs inside PostgreSQL — no separate graph DB.
"""

import logging
import re

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import HypothesisStatus
from app.models.hypotheses import Hypothesis
from app.models.relationships import GraphEdge

logger = logging.getLogger(__name__)


def _parse_agtype(val):
    """Parse an AGE agtype value to a Python value."""
    if val is None:
        return None
    s = str(val)
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith('[') and s.endswith(']'):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"') for item in inner.split(',')]
    return s


class KnowledgeGraph:
    """Manages a temporal crisis knowledge graph for one incident.

    Edges are always persisted to graph_edges (relational mirror). If AGE is
    available, vertices/edges are also mirrored into an AGE graph for Cypher
    querying. Queries prefer AGE Cypher, falling back to a recursive CTE.
    """

    def __init__(self, db: Session, org_id: str, incident_id: str):
        self.db = db
        self.org_id = org_id
        self.incident_id = incident_id
        safe = re.sub(r"[^a-z0-9_]", "_", incident_id.lower())
        self.graph_name = f"g_{safe}"
        self.age_available = False

    def create_graph(self) -> bool:
        """Create AGE graph for this incident. Returns True if AGE available."""
        try:
            self.db.execute(text("SET search_path = ag_catalog, public"))
            exists = self.db.execute(
                text("SELECT 1 FROM ag_catalog.ag_graph WHERE name = :n"),
                {"n": self.graph_name},
            ).scalar()
            if not exists:
                self.db.execute(
                    text("SELECT * FROM ag_catalog.create_graph(:n)"),
                    {"n": self.graph_name},
                )
            self.db.commit()
            self.age_available = True
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.debug("AGE unavailable, using graph_edges CTE: %s", exc)
            self.age_available = False
        return self.age_available

    def drop_graph(self) -> None:
        """Drop the AGE graph for this incident (cleanup)."""
        try:
            self.db.execute(text("SET search_path = ag_catalog, public"))
            self.db.execute(
                text("SELECT * FROM ag_catalog.drop_graph(:n, true)"),
                {"n": self.graph_name},
            )
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
        self.age_available = False

    def clear_graph(self) -> None:
        """Remove all vertices and edges from the AGE graph (keep the graph)."""
        if self.age_available:
            self._cypher("MATCH (n) DETACH DELETE n", "r agtype")

    def add_entity(self, entity_type: str, entity_id: str, properties: dict = None) -> None:
        """Add vertex to AGE graph (no-op if AGE unavailable)."""
        if not self.age_available:
            return
        props = dict(properties or {})
        props["id"] = entity_id
        prop_str = ", ".join(f"{k}: '{v}'" for k, v in props.items())
        cypher = f"CREATE (n:{entity_type} {{{prop_str}}}) RETURN n"
        self._cypher(cypher, "n agtype")

    def add_edge(
        self, source_type: str, source_id: str, edge_type: str,
        target_type: str, target_id: str,
        properties: dict = None, valid_from: int = None, valid_until: int = None,
    ) -> int:
        """Add edge to graph_edges table (and AGE if available)."""
        edge = GraphEdge(
            source_type=source_type, source_id=source_id, edge_type=edge_type,
            target_type=target_type, target_id=target_id,
            properties=properties, valid_from=valid_from or now_ms(),
            valid_until=valid_until,
        )
        self.db.add(edge)
        self.db.commit()
        self.db.refresh(edge)
        if self.age_available:
            cypher = (
                f"MATCH (a:{source_type} {{id: '{source_id}'}}), "
                f"(b:{target_type} {{id: '{target_id}'}}) "
                f"CREATE (a)-[:{edge_type}]->(b) RETURN 'ok'"
            )
            self._cypher(cypher, "r agtype")
        return edge.id

    def query_neighbors(self, entity_type: str, entity_id: str, hops: int = 1) -> list[dict]:
        """Query N-hop neighbors via outgoing edges."""
        if self.age_available:
            try:
                return self._query_cypher(entity_id, hops)
            except SQLAlchemyError:
                self.db.rollback()
        return self._query_cte(entity_type, entity_id, hops)

    def query_two_hop(self, entity_type: str, entity_id: str) -> list[dict]:
        """Convenience method for 2-hop query."""
        return self.query_neighbors(entity_type, entity_id, hops=2)

    def add_hypothesis(
        self, entity_type: str, entity_id: str, claim: str,
        probability: float = 0.5, supporting_evidence: dict = None,
        contradicting_evidence: dict = None,
    ) -> str:
        """Create a Hypothesis. Contradictory hypotheses are both preserved."""
        hid = generate_ulid()
        ts = now_ms()
        h = Hypothesis(
            id=hid, org_id=self.org_id, incident_id=self.incident_id,
            entity_type=entity_type, entity_id=entity_id, claim=claim,
            probability=probability, supporting_evidence=supporting_evidence,
            contradicting_evidence=contradicting_evidence,
            status=HypothesisStatus.active, created_at=ts, updated_at=ts,
        )
        self.db.add(h)
        self.db.commit()
        return hid

    def link_observation(
        self, observation_id: str, hypothesis_id: str, relationship: str,
        properties: dict = None,
    ) -> int:
        """Link an observation to a hypothesis (supports/contradicts)."""
        return self.add_edge(
            source_type="observation", source_id=observation_id,
            edge_type=relationship, target_type="hypothesis",
            target_id=hypothesis_id, properties=properties,
        )

    def get_hypotheses(self, entity_type: str, entity_id: str) -> list[Hypothesis]:
        """Get all hypotheses for an entity (including contradictory ones)."""
        from sqlalchemy import select
        result = self.db.execute(
            select(Hypothesis).where(
                Hypothesis.org_id == self.org_id,
                Hypothesis.entity_type == entity_type,
                Hypothesis.entity_id == entity_id,
            )
        )
        return list(result.scalars().all())

    def update_hypothesis_status(self, hypothesis_id: str, status: HypothesisStatus) -> None:
        """Update hypothesis status (active -> resolved/superseded)."""
        h = self.db.get(Hypothesis, hypothesis_id)
        if h is None:
            raise ValueError(f"Hypothesis {hypothesis_id} not found")
        h.status = status
        h.updated_at = now_ms()
        self.db.commit()

    def _cypher(self, cypher_stmt: str, col_def: str) -> None:
        """Execute a Cypher statement (swallows errors for resilience).

        Uses exec_driver_sql to bypass SQLAlchemy's ':' parameter parsing,
        which conflicts with Cypher's :Label and :relationship syntax.
        """
        try:
            conn = self.db.connection()
            conn.exec_driver_sql("SET search_path = ag_catalog, public")
            conn.exec_driver_sql(
                f"SELECT * FROM cypher('{self.graph_name}', "
                f"$$ {cypher_stmt} $$) AS ({col_def})"
            )
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()

    def _query_cypher(self, entity_id: str, hops: int) -> list[dict]:
        """Query using AGE Cypher variable-length path."""
        cypher = (
            f"MATCH p=(start {{id: '{entity_id}'}})-[*1..{hops}]->(neighbor) "
            f"RETURN neighbor.id, labels(neighbor), min(length(p)) AS hop "
            f"ORDER BY hop, neighbor.id"
        )
        conn = self.db.connection()
        conn.exec_driver_sql("SET search_path = ag_catalog, public")
        result = conn.exec_driver_sql(
            f"SELECT * FROM cypher('{self.graph_name}', "
            f"$$ {cypher} $$) AS (id agtype, labels agtype, hop agtype)"
        )
        neighbors = []
        for row in result:
            nid = _parse_agtype(row[0])
            nlabels = _parse_agtype(row[1])
            ntype = nlabels[0] if nlabels else "unknown"
            hop = int(_parse_agtype(row[2]) or 1)
            neighbors.append({"entity_type": ntype, "entity_id": nid, "hop": hop})
        return neighbors

    def _query_cte(self, entity_type: str, entity_id: str, hops: int) -> list[dict]:
        """Query using recursive CTE on graph_edges table."""
        sql = text("""
            WITH RECURSIVE neighbor_chain AS (
                SELECT target_type, target_id, edge_type, properties, 1 AS hop
                FROM graph_edges
                WHERE source_type = :et AND source_id = :ei
                  AND valid_until IS NULL
                UNION ALL
                SELECT ge.target_type, ge.target_id, ge.edge_type,
                       ge.properties, nc.hop + 1
                FROM graph_edges ge
                JOIN neighbor_chain nc
                  ON ge.source_type = nc.target_type
                 AND ge.source_id = nc.target_id
                WHERE nc.hop < :hops AND ge.valid_until IS NULL
            )
            SELECT DISTINCT ON (target_type, target_id)
                   target_type, target_id, edge_type, properties, hop
            FROM neighbor_chain
            ORDER BY target_type, target_id, hop
        """)
        result = self.db.execute(sql, {"et": entity_type, "ei": entity_id, "hops": hops})
        return [
            {
                "entity_type": row.target_type, "entity_id": row.target_id,
                "edge_type": row.edge_type, "properties": row.properties,
                "hop": row.hop,
            }
            for row in result
        ]
