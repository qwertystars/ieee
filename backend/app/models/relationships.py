"""Graph edges table for Apache AGE-backed entity relationships.

This table stores typed edges between any two entities (identified by
source_type/source_id -> target_type/target_id). Apache AGE graph
creation happens at runtime; this table is the relational mirror.
"""

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GraphEdge(Base):
    """A typed, time-bounded edge between two entities."""

    __tablename__ = "graph_edges"
    __table_args__ = (
        Index("ix_graph_edges_source", "source_type", "source_id"),
        Index("ix_graph_edges_target", "target_type", "target_id"),
        Index("ix_graph_edges_edge_type", "edge_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String(26))
    edge_type: Mapped[str] = mapped_column(String)
    target_type: Mapped[str] = mapped_column(String)
    target_id: Mapped[str] = mapped_column(String(26))
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    valid_from: Mapped[int] = mapped_column(BigInteger)
    valid_until: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
