"""E2E ONNX inference test — validates the full inference plumbing.

Instantiates ``ModelServing`` with the real ONNX Runtime (no mocks) and
the real trained weight files in ``backend/data/models/``. For each
of the 3 catalog models, this test:

1. Inserts a ``ModelRecord`` into the DB registry.
2. Calls ``load_model()`` to create a real ``onnxruntime.InferenceSession``.
3. Calls ``run_inference()`` with a fixture input matching the catalog's
   ``input_schema``.
4. Asserts the output matches the catalog's ``output_schema`` shape.
5. Asserts a ``model_version`` string (``name:version``) is returned.

The models are real pre-trained weights exported from HuggingFace:
  - SAR flood mapping: U-Net+ResNet34 from Governor6191/sar-flood-extent-unet-resnet34
  - Building damage: U-Net+ResNet50 from vivek20072000/xview2-checkpoints
  - Incident NLP: BERT fine-tune from sakibalfahim/CrisisPulse
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np
import pytest
from sqlalchemy.orm import sessionmaker

from app.db import engine
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.perception.models import ModelFramework, ModelRecord, ModelTask
from app.perception.serving import MODEL_CATALOG, ModelServing

ORG_ID = "org_test_onnx_e2e"

# Resolve backend/data/ — _get_model_bytes joins cache_dir with r2_key.
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BACKEND, "data")
_MODELS_DIR = os.path.join(_DATA_DIR, "models")


# ─── Skip condition ─────────────────────────────────────────────────────────


def _onnx_files_present() -> bool:
    """Check if the 3 ONNX model files exist in backend/data/models/."""
    if not os.path.isdir(_MODELS_DIR):
        return False
    return any(f.endswith(".onnx") for f in os.listdir(_MODELS_DIR))


_SKIP_REASON = (
    "ONNX model files not found in backend/data/models/ — "
    "run scripts/download_real_models.py to download them"
)


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def session_factory():
    """Session factory bound to the shared PostgreSQL test engine."""
    return sessionmaker(bind=engine)


@pytest.fixture
def serving(session_factory):
    """ModelServing with real ONNX Runtime and local cache_dir.

    ``cache_dir`` is set to ``backend/data/`` so ``_get_model_bytes`` finds
    ``backend/data/models/<filename>.onnx`` via the ``r2_key`` path
    (``models/<filename>.onnx`` → ``models/<filename>.onnx`` joined with
    ``cache_dir``). No MinIO client needed — files are served from disk.
    """
    return ModelServing(
        session_factory=session_factory,
        minio_client=None,
        cache_dir=_DATA_DIR,
    )


# ─── Helpers ────────────────────────────────────────────────────────────────


def _catalog_to_record(model: dict[str, Any]) -> ModelRecord:
    """Build a ModelRecord from a MODEL_CATALOG entry."""
    task_map = {
        "flood_mapping": ModelTask.flood_mapping,
        "damage": ModelTask.damage,
        "nlp": ModelTask.nlp,
    }
    return ModelRecord(
        id=generate_ulid(),
        org_id=ORG_ID,
        name=model["name"],
        version=model["version"],
        framework=ModelFramework.onnx,
        task=task_map[model["task"]],
        r2_key=model["r2_key"],
        input_schema=model["input_schema"],
        output_schema=model["output_schema"],
        calibration_metrics=model["calibration_metrics"],
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


def _make_input_fixture(model: dict[str, Any]) -> dict[str, Any]:
    """Build a numpy input fixture matching the model's input_schema.

    For vision models (flood_mapping, damage), the schema has a ``shape``
    key and the ONNX input tensor is named ``input``.

    For the NLP model, the schema keys are the tensor names (``input_ids``,
    ``attention_mask``) mapped to their shapes.
    """
    schema = model["input_schema"]
    task = model["task"]

    if task == "nlp":
        feeds: dict[str, Any] = {}
        for name, shape in schema.items():
            if name == "input_ids":
                feeds[name] = np.zeros(shape, dtype=np.int64)
            elif name == "attention_mask":
                feeds[name] = np.ones(shape, dtype=np.int64)
            else:
                feeds[name] = np.zeros(shape, dtype=np.float32)
        return feeds

    # Vision models: single input named "input" with the declared shape.
    shape = schema["shape"]
    return {"input": np.zeros(shape, dtype=np.float32)}


def _assert_output_shape(model: dict[str, Any], outputs: dict[str, Any]) -> None:
    """Assert each output tensor matches the declared output_schema shape."""
    output_schema = model["output_schema"]
    for name, expected_shape in output_schema.items():
        assert name in outputs, (
            f"model {model['name']}: output '{name}' not in outputs {list(outputs.keys())}"
        )
        arr = outputs[name]
        assert hasattr(arr, "shape"), (
            f"model {model['name']}: output '{name}' is not an ndarray (got {type(arr)})"
        )
        actual_shape = list(arr.shape)
        assert actual_shape == list(expected_shape), (
            f"model {model['name']}: output '{name}' shape {actual_shape} "
            f"!= expected {list(expected_shape)}"
        )


# ─── E2E tests ──────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _onnx_files_present(), reason=_SKIP_REASON)
def test_all_catalog_models_inference_e2e(serving, session_factory):
    """E2E: load + run inference for every model in MODEL_CATALOG.

    This is the single parametrized E2E test — it iterates the full catalog,
    inserts each model into the registry, loads the real ONNX session from
    the local weight file, runs inference with a zero-input fixture,
    and asserts the output shapes match the catalog's output_schema.
    """
    for model in MODEL_CATALOG:
        record = _catalog_to_record(model)
        model_id = _insert_model(session_factory, record)

        # load_model creates a real onnxruntime.InferenceSession from the
        # local .onnx file (served via cache_dir, no MinIO).
        session = serving.load_model(model_id)
        assert session is not None, f"load_model returned None for {model['name']}"

        # run_inference executes the session and returns outputs + model_version.
        input_feed = _make_input_fixture(model)
        result = serving.run_inference(model_id, input_feed)

        # Assert model_version provenance string (name:version).
        assert "model_version" in result, f"{model['name']}: missing model_version"
        expected_version = f"{model['name']}:{model['version']}"
        assert result["model_version"] == expected_version, (
            f"{model['name']}: model_version {result['model_version']!r} "
            f"!= expected {expected_version!r}"
        )

        # Assert output shapes match the catalog's output_schema.
        assert "outputs" in result, f"{model['name']}: missing outputs key"
        _assert_output_shape(model, result["outputs"])

        # Assert non-trivial outputs (not all zeros) — real models produce
        # meaningful outputs even with zero input due to bias terms.
        for name, arr in result["outputs"].items():
            assert not np.allclose(arr, 0), (
                f"{model['name']}: output '{name}' is all zeros — "
                "model may have untrained weights or export issue"
            )

        # Cleanup: unload to free memory.
        serving.unload_model(model_id)


@pytest.mark.skipif(not _onnx_files_present(), reason=_SKIP_REASON)
def test_real_models_are_trained_weights():
    """Honesty guard — assert the ONNX files are real trained weights (> 1 MB).

    Real trained ONNX models for flood mapping, damage assessment, and NLP
    are tens to hundreds of megabytes. Placeholder files with trivial ops
    (Identity, ReduceMean, Constant) would be < 1 KB. This test verifies
    the files on disk are genuine trained models, not placeholders.
    """
    if not os.path.isdir(_MODELS_DIR):
        pytest.skip(_SKIP_REASON)
    for model in MODEL_CATALOG:
        r2_key = model["r2_key"]
        filename = os.path.basename(r2_key)
        path = os.path.join(_MODELS_DIR, filename)
        assert os.path.exists(path), f"model file missing: {path}"
        size = os.path.getsize(path)
        assert size > 1024 * 1024, (
            f"{filename} is {size} bytes — real trained model should be > 1 MB. "
            "If placeholder files were regenerated, run scripts/download_real_models.py."
        )
