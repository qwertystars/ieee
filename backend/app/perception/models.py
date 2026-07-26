"""Model registry — SQLAlchemy model for the ``models`` table.

The ``models`` table is a registry of ML models available for inference.
It stores metadata (name, version, framework, task, schemas) — NOT the model
weights themselves. Weights live in MinIO (S3-compatible) at ``r2_key``.

``JSONBCompat`` renders as ``JSONB`` on PostgreSQL (matching the codebase
convention) and falls back to ``JSON`` on SQLite, enabling in-memory SQLite
tests without a PostgreSQL dependency.
"""

from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Enum as SAEnum, String, TypeDecorator
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeEngine

from app.db import Base


class JSONBCompat(TypeDecorator):
    """JSONB on PostgreSQL, JSON on other dialects (e.g. SQLite tests)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class ModelFramework(str, enum.Enum):
    """Framework the model was trained/exported with."""

    pytorch = "pytorch"
    onnx = "onnx"


class ModelTask(str, enum.Enum):
    """Inference task the model performs."""

    flood_mapping = "flood_mapping"
    damage = "damage"
    nlp = "nlp"


class ModelRecord(Base):
    """A registered ML model in the model registry.

    The ``models`` table is metadata-only — weights are stored in MinIO
    at ``r2_key``. Every inference records ``name:version`` as
    ``model_version`` on the observation for provenance tracking.
    """

    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String)
    framework: Mapped[ModelFramework] = mapped_column(
        SAEnum(ModelFramework, native_enum=False)
    )
    task: Mapped[ModelTask] = mapped_column(
        SAEnum(ModelTask, native_enum=False)
    )
    r2_key: Mapped[str] = mapped_column(String)
    input_schema: Mapped[dict] = mapped_column(JSONBCompat)
    output_schema: Mapped[dict] = mapped_column(JSONBCompat)
    calibration_metrics: Mapped[dict] = mapped_column(JSONBCompat)
    created_at: Mapped[int] = mapped_column(BigInteger)


__all__ = [
    "JSONBCompat",
    "ModelFramework",
    "ModelTask",
    "ModelRecord",
]
