"""Manifest contract parsing and fail-closed model resolution."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONTRACT_FIELDS = (
    "contract_version",
    "model_version",
    "feature_schema_version",
    "preprocessing_version",
    "calibration_version",
    "output_schema_version",
)


class ContractState(StrEnum):
    """The only states exposed by inference contract resolution."""

    available = "available"
    abstain = "abstain"
    unavailable = "unavailable"
    incompatible = "incompatible"


@dataclass(frozen=True, slots=True)
class ContractVersions:
    """Pinned versions that identify one inference contract."""

    contract_version: str
    model_version: str
    feature_schema_version: str
    preprocessing_version: str
    calibration_version: str
    output_schema_version: str


@dataclass(frozen=True, slots=True)
class InferenceContract:
    """Parsed manifest contract and its immutable artifact provenance."""

    model_id: str
    model_type: str
    versions: ContractVersions
    artifact_key: str
    artifact_sha256: str
    source_url: str
    features: tuple[str, ...]
    input_schema: dict[str, dict[str, Any]]
    output_schema: dict[str, dict[str, Any]]
    calibration_available: bool


@dataclass(frozen=True, slots=True)
class ContractResolution:
    """Result of resolving a requested contract against the manifest."""

    state: ContractState
    contract: InferenceContract | None
    reason: str


class InferenceContractError(RuntimeError):
    """Raised when a serving request cannot use its resolved contract."""

    def __init__(self, resolution: ContractResolution) -> None:
        self.resolution = resolution
        super().__init__(resolution.reason)


def parse_contract(raw: Mapping[str, Any]) -> InferenceContract:
    artifact = raw["artifact"]
    versions_raw = raw["contract"]
    versions = ContractVersions(
        **{field: versions_raw[field] for field in CONTRACT_FIELDS},
    )
    if raw["version"] != versions.model_version:
        raise ValueError("manifest version and contract model version differ")
    if Path(artifact["r2_key"]).name != artifact["filename"]:
        raise ValueError("artifact filename and key differ")
    input_schema = raw["input_schema"]["onnx_inputs"]
    output_schema = raw["output_schema"]
    if not isinstance(artifact["sha256"], str) or len(artifact["sha256"]) != 64:
        raise ValueError("invalid artifact sha256")
    if artifact["sha256"] != raw["checksum"]:
        raise ValueError("artifact checksum mismatch")
    calibration = raw.get("calibration")
    calibration_available = versions.calibration_version != "unavailable"
    if isinstance(calibration, Mapping):
        calibration_available = calibration_available and calibration.get("status") == "available"
    return InferenceContract(
        model_id=raw["model_id"],
        model_type=raw["model_type"],
        versions=versions,
        artifact_key=artifact["r2_key"],
        artifact_sha256=artifact["sha256"],
        source_url=artifact["source_url"],
        features=tuple(raw["input_schema"].get("bands", [])),
        input_schema=input_schema,
        output_schema=output_schema,
        calibration_available=calibration_available,
    )


def load_contracts(manifest_path: Path) -> tuple[InferenceContract, ...]:
    with manifest_path.open(encoding="utf-8") as manifest_file:
        raw_entries = json.load(manifest_file)
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("model manifest must be a non-empty array")
    return tuple(parse_contract(entry) for entry in raw_entries)


def catalog_from_contracts(contracts: tuple[InferenceContract, ...]) -> list[dict[str, Any]]:
    tasks = {
        "sar_flood_mapping": "flood_mapping",
        "building_damage": "damage",
        "incident_nlp": "nlp",
    }
    catalog: list[dict[str, Any]] = []
    for contract in contracts:
        input_shapes = {
            name: value["shape"] for name, value in contract.input_schema.items()
        }
        catalog_input_schema: dict[str, Any]
        if len(input_shapes) == 1:
            first_schema = next(iter(contract.input_schema.values()))
            catalog_input_schema = {
                "bands": list(contract.features),
                "shape": next(iter(input_shapes.values())),
                "dtype": first_schema["dtype"],
            }
        else:
            catalog_input_schema = input_shapes
        catalog.append({
            "name": contract.model_id,
            "version": contract.versions.model_version,
            "framework": "onnx",
            "task": tasks[contract.model_type],
            "r2_key": contract.artifact_key,
            "source_url": contract.source_url,
            "input_schema": catalog_input_schema,
            "output_schema": {
                name: value["shape"]
                for name, value in contract.output_schema.items()
            },
            "calibration_metrics": {},
            "contract": contract,
        })
    return catalog


def resolve_contract(
    model_id: str,
    manifest_path: Path,
    requested: ContractVersions | None = None,
) -> ContractResolution:
    """Resolve one model against a manifest and optional requested versions."""
    try:
        contract = next(
            contract
            for contract in load_contracts(manifest_path)
            if contract.model_id == model_id
        )
    except StopIteration:
        return ContractResolution(ContractState.unavailable, None, "model_not_registered")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("model manifest resolution failed: %s", exc)
        return ContractResolution(ContractState.unavailable, None, "registry_unavailable")

    if requested is not None:
        mismatches = [
            field for field in CONTRACT_FIELDS
            if getattr(requested, field) != getattr(contract.versions, field)
        ]
        if mismatches:
            return ContractResolution(
                ContractState.incompatible,
                contract,
                "incompatible_versions:" + ",".join(mismatches),
            )
    if not contract.calibration_available:
        return ContractResolution(ContractState.abstain, contract, "calibration_unavailable")
    return ContractResolution(ContractState.available, contract, "")


__all__ = [
    "CONTRACT_FIELDS",
    "ContractResolution",
    "ContractState",
    "ContractVersions",
    "InferenceContract",
    "InferenceContractError",
    "catalog_from_contracts",
    "load_contracts",
    "parse_contract",
    "resolve_contract",
]
