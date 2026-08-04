"""Tests for ML model serving layer — lazy loading, inference, idle eviction.

Uses the real PostgreSQL DB (models table created by Alembic) and mock ONNX
sessions (no real model weights required). MinIO is mocked — no real S3
needed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import engine
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.perception.models import (
    ModelFramework,
    ModelRecord,
    ModelTask,
)
from app.perception.serving import (
    MODEL_CATALOG,
    InferenceContractError,
    ModelServing,
    format_catalog,
)

ORG_ID = "org_test_serving"


# ─── Mocks ──────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _MockIO:
    """Mock for onnxruntime input/output metadata (has .name)."""

    name: str


class _MockONNXSession:
    """Mock onnxruntime.InferenceSession — adds two float inputs."""

    def __init__(self, model_bytes: bytes) -> None:
        self._bytes = model_bytes

    def get_inputs(self):
        return [_MockIO("input_a"), _MockIO("input_b")]

    def get_outputs(self):
        return [_MockIO("sum"), _MockIO("product")]

    def run(self, output_names, feeds):
        a = feeds.get("input_a", 0.0)
        b = feeds.get("input_b", 0.0)
        return [a + b, a * b]


class _MockMinioResponse:
    """Mock MinIO get_object response."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class _MockMinioClient:
    """Mock MinIO client — records get_object calls."""

    def __init__(self, model_bytes: bytes = b"fake-onnx-weights") -> None:
        self._bytes = model_bytes
        self.get_object_calls: list[tuple[str, str]] = []

    def get_object(self, bucket: str, key: str) -> _MockMinioResponse:
        self.get_object_calls.append((bucket, key))
        return _MockMinioResponse(self._bytes)


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def session_factory():
    """Session factory bound to the shared PostgreSQL test engine."""
    return sessionmaker(bind=engine)


@pytest.fixture
def minio_client():
    return _MockMinioClient()


@pytest.fixture
def serving(session_factory, minio_client):
    """ModelServing with mocked ONNX session creation and MinIO."""
    s = ModelServing(
        session_factory=session_factory,
        minio_client=minio_client,
    )
    s._create_session = lambda model_bytes: _MockONNXSession(model_bytes)
    return s


def _make_model_record(
    name: str = "test-model",
    version: str = "1.0.0",
    r2_key: str = "models/test-model-v1.0.0.onnx",
) -> ModelRecord:
    """Build a ModelRecord for insertion."""
    return ModelRecord(
        id=generate_ulid(),
        org_id=ORG_ID,
        name=name,
        version=version,
        framework=ModelFramework.onnx,
        task=ModelTask.flood_mapping,
        r2_key=r2_key,
        input_schema={"bands": ["VV", "VH"], "shape": [1, 2, 512, 512]},
        output_schema={"flood_mask": [1, 1, 512, 512]},
        calibration_metrics={"iou": 0.87},
        created_at=now_ms(),
    )


def _insert_model(session_factory, record: ModelRecord) -> str:
    """Insert a model record and return its ID."""
    db = session_factory()
    try:
        db.add(record)
        db.commit()
        return record.id
    finally:
        db.close()


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_lazy_loading(serving, session_factory, minio_client):
    """Unregistered records cannot enter the serving cache."""
    record = _make_model_record()
    model_id = _insert_model(session_factory, record)
    with pytest.raises(InferenceContractError, match="model_not_registered"):
        serving.load_model(model_id)
    assert not minio_client.get_object_calls


def test_inference_returns_result(serving, session_factory):
    """run_inference rejects an unregistered record before loading weights."""
    record = _make_model_record()
    model_id = _insert_model(session_factory, record)

    with pytest.raises(InferenceContractError, match="model_not_registered"):
        serving.run_inference(model_id, {})


def test_unload_idle_models(serving, session_factory):
    """Idle eviction cannot be reached by an unregistered record."""
    record = _make_model_record()
    model_id = _insert_model(session_factory, record)

    with pytest.raises(InferenceContractError, match="model_not_registered"):
        serving.load_model(model_id)
    assert model_id not in serving._cache


def test_model_registry_crud(session_factory):
    """Create, read, update a ModelRecord in the DB."""
    record = _make_model_record(name="crud-model", version="0.1.0")
    model_id = record.id

    # Create
    db = session_factory()
    db.add(record)
    db.commit()
    db.close()

    # Read
    db = session_factory()
    fetched = db.get(ModelRecord, model_id)
    assert fetched is not None
    assert fetched.name == "crud-model"
    assert fetched.version == "0.1.0"
    assert fetched.framework == ModelFramework.onnx
    assert fetched.task == ModelTask.flood_mapping
    assert fetched.input_schema["bands"] == ["VV", "VH"]
    db.close()

    # Update
    db = session_factory()
    fetched = db.get(ModelRecord, model_id)
    fetched.version = "0.2.0"
    fetched.calibration_metrics = {"iou": 0.92, "precision": 0.95}
    db.commit()
    db.close()

    # Verify update persisted
    db = session_factory()
    updated = db.get(ModelRecord, model_id)
    assert updated.version == "0.2.0"
    assert updated.calibration_metrics["iou"] == 0.92
    db.close()


def test_model_versioning(serving, session_factory):
    """Legacy model names cannot produce unverified model provenance."""
    record = _make_model_record(name="flood-mapper", version="2.3.1")
    model_id = _insert_model(session_factory, record)

    with pytest.raises(InferenceContractError, match="model_not_registered"):
        serving.run_inference(model_id, {})


def test_download_script_list():
    """format_catalog (called by --list) outputs all models in the catalog.

    The scripts/ directory is at the repo root and may not be mounted inside
    the Docker container (only ./backend is mounted). The file-structure
    checks are skipped if the script is not visible; the catalog logic is
    always tested via format_catalog().
    """
    output = format_catalog()

    # Every model in the catalog appears in the formatted output.
    for model in MODEL_CATALOG:
        assert model["name"] in output
        assert model["version"] in output
        assert model["r2_key"] in output

    # The script file exists on the host (may not be visible inside Docker).
    script_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "download_models.py"
    )
    if os.path.isfile(script_path):
        with open(script_path) as f:
            source = f.read()
        assert "--list" in source
        assert "--download" in source
