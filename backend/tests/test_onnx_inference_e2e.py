"""Real-artifact inference tests for the canonical model registry."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.enums import Resampling
from sqlalchemy.orm import sessionmaker

from app.db import engine
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.perception.models import ModelFramework, ModelRecord, ModelTask
from app.perception.serving import MODEL_CATALOG, ContractState, ModelServing

ORG_ID = "org_test_onnx_e2e"
_BACKEND = Path(__file__).resolve().parents[1]
_DATA_DIR = _BACKEND / "data"
_MODELS_DIR = _DATA_DIR / "models"
_SAR_FIXTURE = _DATA_DIR / "sample-sar" / "sample.tif"
_SAR_FIXTURE_SHA256 = "d7cbe932c7ed74a627706a9e9df99f706df3e5abc7d45a49e9d00677a6b09eb4"


def _onnx_files_present() -> bool:
    return _MODELS_DIR.is_dir() and any(_MODELS_DIR.glob("*.onnx"))


_SKIP_REASON = "v2 ONNX artifacts are unavailable; external model evidence is deferred"


@pytest.fixture
def session_factory():
    return sessionmaker(bind=engine)


@pytest.fixture
def serving(session_factory):
    return ModelServing(session_factory=session_factory, cache_dir=str(_DATA_DIR))


def _catalog_to_record(model: dict[str, Any]) -> ModelRecord:
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
    db = session_factory()
    try:
        db.add(record)
        db.commit()
        return record.id
    finally:
        db.close()


def _real_sar_input() -> dict[str, np.ndarray]:
    assert hashlib.sha256(_SAR_FIXTURE.read_bytes()).hexdigest() == _SAR_FIXTURE_SHA256
    with rasterio.open(_SAR_FIXTURE) as source:
        bands = source.read(
            indexes=(1, 2),
            out_shape=(2, 512, 512),
            resampling=Resampling.bilinear,
        )
    tensor = np.asarray(bands, dtype=np.float32)[np.newaxis, ...]
    assert float(np.ptp(tensor)) > 0.0
    return {"input": tensor}


def _assert_output_schema(model: dict[str, Any], outputs: dict[str, Any]) -> None:
    for name, expected_shape in model["output_schema"].items():
        assert name in outputs
        output = outputs[name]
        assert isinstance(output, np.ndarray)
        assert list(output.shape) == list(expected_shape)
        assert str(output.dtype) == "float32"


@pytest.mark.skipif(not _onnx_files_present(), reason=_SKIP_REASON)
@pytest.mark.parametrize("model", MODEL_CATALOG, ids=lambda model: model["name"])
def test_catalog_model_inference_e2e(model, serving, session_factory):
    if model["task"] != "flood_mapping":
        pytest.skip("DEFERRED_EXTERNAL: no committed real damage/NLP input fixture")
    from app.perception.serving_contracts import InferenceContractError

    model_id = _insert_model(session_factory, _catalog_to_record(model))
    # The real artifact resolves from the manifest, then safety output
    # abstains until a hashed calibration artifact is registered.
    with pytest.raises(InferenceContractError) as exc_info:
        serving.run_inference(model_id, _real_sar_input())
    resolution = exc_info.value.resolution
    assert resolution.state == ContractState.abstain
    assert resolution.reason == "calibration_unavailable"
    assert resolution.contract is not None
    assert resolution.contract.artifact_sha256 == model["contract"].artifact_sha256
    serving.unload_model(model_id)


@pytest.mark.skipif(not _onnx_files_present(), reason=_SKIP_REASON)
def test_real_models_are_trained_weights() -> None:
    for model in MODEL_CATALOG:
        artifact = _MODELS_DIR / Path(model["r2_key"]).name
        assert artifact.is_file()
        assert artifact.stat().st_size > 1024 * 1024
