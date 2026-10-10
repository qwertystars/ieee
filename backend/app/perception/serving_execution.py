"""ONNX session execution, tensor checks, and inference provenance."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import numpy as np

from app.lib.time import now_ms
from app.perception.serving_contracts import (
    CONTRACT_FIELDS,
    ContractResolution,
    ContractState,
    InferenceContract,
    InferenceContractError,
)

if TYPE_CHECKING:
    import onnxruntime as ort


def input_sha256(input_data: Mapping[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for name in sorted(input_data):
        value = np.ascontiguousarray(input_data[name])
        digest.update(name.encode("utf-8"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(str(tuple(value.shape)).encode("ascii"))
        digest.update(value.tobytes(order="C"))
    return digest.hexdigest()


def validate_inputs(
    input_data: Mapping[str, np.ndarray],
    contract: InferenceContract,
) -> None:
    expected_names = set(contract.input_schema)
    if set(input_data) != expected_names:
        raise InferenceContractError(ContractResolution(
            ContractState.incompatible, contract, "input_schema_mismatch",
        ))
    for name, schema in contract.input_schema.items():
        value = input_data[name]
        if not isinstance(value, np.ndarray) or list(value.shape) != schema["shape"]:
            raise InferenceContractError(ContractResolution(
                ContractState.incompatible, contract, f"input_shape_mismatch:{name}",
            ))
        if str(value.dtype) != schema["dtype"]:
            raise InferenceContractError(ContractResolution(
                ContractState.incompatible, contract, f"input_dtype_mismatch:{name}",
            ))


def run_session(
    session: ort.InferenceSession,
    input_data: Mapping[str, Any],
    contract: InferenceContract | None,
) -> dict[str, Any]:
    input_names = [item.name for item in session.get_inputs()]
    if contract is not None:
        expected_names = set(contract.input_schema)
        if set(input_data) != expected_names or set(input_names) != expected_names:
            raise InferenceContractError(ContractResolution(
                ContractState.incompatible, contract, "input_schema_mismatch",
            ))
        validate_inputs(input_data, contract)
    results = session.run(None, dict(input_data))
    output_names = [item.name for item in session.get_outputs()]
    outputs = dict(zip(output_names, results, strict=True))
    if contract is not None:
        expected_outputs = set(contract.output_schema)
        if set(outputs) != expected_outputs:
            raise InferenceContractError(ContractResolution(
                ContractState.incompatible, contract, "output_schema_mismatch",
            ))
        for name, schema in contract.output_schema.items():
            if not isinstance(outputs[name], np.ndarray):
                raise InferenceContractError(ContractResolution(
                    ContractState.incompatible, contract, f"output_dtype_mismatch:{name}",
                ))
            if list(outputs[name].shape) != schema["shape"]:
                raise InferenceContractError(ContractResolution(
                    ContractState.incompatible, contract, f"output_shape_mismatch:{name}",
                ))
            if str(outputs[name].dtype) != schema["dtype"]:
                raise InferenceContractError(ContractResolution(
                    ContractState.incompatible, contract, f"output_dtype_mismatch:{name}",
                ))
    return outputs


def build_provenance(
    contract: InferenceContract,
    *,
    state: ContractState = ContractState.available,
    input_data: Mapping[str, np.ndarray] | None = None,
) -> dict[str, str | int]:
    provenance: dict[str, str | int] = {
        "model_id": contract.model_id,
        **{field: getattr(contract.versions, field) for field in CONTRACT_FIELDS},
        "artifact_key": contract.artifact_key,
        "artifact_sha256": contract.artifact_sha256,
        "source_url": contract.source_url,
        "state": state.value,
    }
    if input_data is not None:
        provenance["input_sha256"] = input_sha256(input_data)
        provenance["inference_timestamp_ms"] = now_ms()
    return provenance


__all__ = ["build_provenance", "input_sha256", "run_session", "validate_inputs"]
