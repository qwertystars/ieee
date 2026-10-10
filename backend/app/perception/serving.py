"""Compatibility facade for manifest-bound ONNX model serving."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.perception.serving_contracts import (
    CONTRACT_FIELDS,
    ContractResolution,
    ContractState,
    ContractVersions,
    InferenceContract,
    InferenceContractError,
    catalog_from_contracts,
    load_contracts,
)
from app.perception.serving_contracts import resolve_contract as _resolve_contract
from app.perception.serving_inputs import (
    PreparedRasterInput,
    RasterInputMetadata,
    prepare_raster_input,
)
from app.perception.serving_runtime import DEFAULT_IDLE_TIMEOUT_S
from app.perception.serving_runtime import ModelServing as _ModelServing

_MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models"
_MANIFEST_PATH = _MODEL_DIR / "manifests.json"
_CONTRACT_FIELDS = CONTRACT_FIELDS
MODEL_CATALOG: list[dict[str, Any]] = []

try:
    MODEL_CATALOG = catalog_from_contracts(load_contracts(_MANIFEST_PATH))
except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
    MODEL_CATALOG = []


def resolve_contract(
    model_id: str,
    requested: ContractVersions | None = None,
) -> ContractResolution:
    """Resolve a model using the facade's monkeypatchable manifest path."""
    return _resolve_contract(model_id, _MANIFEST_PATH, requested)


def format_catalog() -> str:
    """Format the manifest-backed catalog as a human-readable table."""
    lines = [
        f"{'Name':<25} {'Version':<10} {'Framework':<10} {'Task':<15} {'R2 Key'}",
        "-" * 90,
    ]
    for model in MODEL_CATALOG:
        lines.append(
            f"{model['name']:<25} {model['version']:<10} {model['framework']:<10} "
            f"{model['task']:<15} {model['r2_key']}"
        )
    return "\n".join(lines)


class ModelServing(_ModelServing):
    """Public serving class bound to the facade manifest path."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        minio_client: Any | None = None,
        cache_dir: str | None = None,
    ) -> None:
        super().__init__(
            session_factory=session_factory,
            minio_client=minio_client,
            cache_dir=cache_dir,
            manifest_path=_MANIFEST_PATH,
        )


__all__ = [
    "DEFAULT_IDLE_TIMEOUT_S",
    "MODEL_CATALOG",
    "ContractResolution",
    "ContractState",
    "ContractVersions",
    "InferenceContract",
    "InferenceContractError",
    "ModelServing",
    "PreparedRasterInput",
    "RasterInputMetadata",
    "format_catalog",
    "prepare_raster_input",
    "resolve_contract",
]
