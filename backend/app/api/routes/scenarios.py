"""Scenarios, world-state, calibration, and flood-map API routes.

Wires the SOTA fusion and perception engines to incident-scoped endpoints:
  - GET  /{incident_id}/scenarios       — ScenarioGenerator ensemble
  - GET  /{incident_id}/world-state      — DBN state distribution
  - GET  /{incident_id}/calibration      — Brier/ECE/coverage metrics
  - GET  /{incident_id}/flood-map         — SAR flood mapping (degrades)
  - GET  /{incident_id}/flood-ensemble    — Flood ensemble (degrades)

ML features expose explicit contract states when artifacts or inputs are unavailable.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.deps import get_current_user, get_db
from app.lib.time import now_ms
from app.models.incident import Incident
from app.models.user import User
from app.perception.serving import (
    ContractResolution,
    ContractState,
    ContractVersions,
    InferenceContractError,
    ModelServing,
    RasterInputMetadata,
    prepare_raster_input,
    resolve_contract,
)

logger = logging.getLogger("app.api.routes.scenarios")

router = APIRouter(prefix="/incidents", tags=["scenarios"])

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
_SERVING = ModelServing(SessionLocal, cache_dir=_DATA_DIR)


def _data_path(filename: str) -> str:
    return os.path.normpath(os.path.join(_DATA_DIR, filename))


def _load_json(filename: str) -> dict[str, Any]:
    path = _data_path(filename)
    with open(path) as f:
        return json.load(f)


def _get_incident(db: Session, org_id: str, incident_id: str) -> Incident:
    inc = db.execute(
        select(Incident).where(
            Incident.org_id == org_id, Incident.id == incident_id,
        )
    ).scalars().first()
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


class ContractRequest(BaseModel):
    """Optional exact contract versions supplied by an inference client."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str | None = None
    model_version: str | None = None
    feature_schema_version: str | None = None
    preprocessing_version: str | None = None
    calibration_version: str | None = None
    output_schema_version: str | None = None

    def versions(self) -> ContractVersions | None:
        contract_version = self.contract_version
        model_version = self.model_version
        feature_schema_version = self.feature_schema_version
        preprocessing_version = self.preprocessing_version
        calibration_version = self.calibration_version
        output_schema_version = self.output_schema_version
        values = (
            contract_version,
            model_version,
            feature_schema_version,
            preprocessing_version,
            calibration_version,
            output_schema_version,
        )
        if all(value is None for value in values):
            return None
        if any(value is None for value in values):
            raise HTTPException(status_code=422, detail="all contract versions are required")
        if contract_version is None:
            raise HTTPException(status_code=422, detail="contract_version is required")
        if model_version is None:
            raise HTTPException(status_code=422, detail="model_version is required")
        if feature_schema_version is None:
            raise HTTPException(status_code=422, detail="feature_schema_version is required")
        if preprocessing_version is None:
            raise HTTPException(status_code=422, detail="preprocessing_version is required")
        if calibration_version is None:
            raise HTTPException(status_code=422, detail="calibration_version is required")
        if output_schema_version is None:
            raise HTTPException(status_code=422, detail="output_schema_version is required")
        return ContractVersions(
            contract_version=contract_version,
            model_version=model_version,
            feature_schema_version=feature_schema_version,
            preprocessing_version=preprocessing_version,
            calibration_version=calibration_version,
            output_schema_version=output_schema_version,
        )


class RasterQualityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_fraction: StrictFloat = Field(ge=0.0, le=1.0)
    nodata_fraction: StrictFloat = Field(ge=0.0, le=1.0)
    snr_db: StrictFloat


class RasterRequest(ContractRequest):
    crs: StrictStr | None = None
    resolution_m: StrictFloat | None = None
    quality: RasterQualityRequest | None = None


class FloodMapRequest(RasterRequest):
    """Real SAR tensor input for flood mapping."""

    input_data: list[list[list[list[StrictFloat]]]] | None = None


def _route_resolution(
    model_id: str,
    requested: ContractVersions | None = None,
) -> ContractResolution:
    resolution = resolve_contract(model_id, requested)
    if resolution.contract is not None and not _SERVING.artifact_available(model_id):
        return ContractResolution(ContractState.unavailable, resolution.contract, "weights_unavailable")
    return resolution


def _contract_response(feature: str, resolution: ContractResolution) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": resolution.state.value,
        "feature": feature,
        "reason": resolution.reason,
        "review_status": "draft",
    }
    if resolution.contract is not None:
        response["provenance"] = _SERVING._provenance(
            resolution.contract, state=resolution.state,
        )
    return response


# ── Scenarios ──────────────────────────────────────────────────────────────


@router.get("/{incident_id}/scenarios")
def get_scenarios(
    incident_id: str,
    request: Request,
    n: int = Query(20, ge=10, le=50),
    seed: int = Query(42),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return best/expected/worst scenario ensemble from ScenarioGenerator."""
    from app.twin.scenario_types import WorldStateSnapshot
    from app.twin.scenarios import ScenarioGenerator

    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    ws_data = _load_json("world_state.json")
    ws = WorldStateSnapshot(
        flood_severity_dist=ws_data["flood_severity_dist"],
        flood_extent_pct=ws_data["flood_extent_pct"],
        flood_uncertainty=ws_data["flood_uncertainty"],
        road_ids=tuple(ws_data["road_ids"]),
        current_time_ms=ws_data["current_time_ms"],
    )
    gen = ScenarioGenerator(ws, seed=seed)
    scenarios = gen.generate(n=n)

    by_label: dict[str, list[dict]] = {}
    for sc in scenarios:
        by_label.setdefault(sc.label.value, []).append({
            "id": sc.id,
            "label": sc.label.value,
            "probability": sc.probability,
            "params": sc.to_params_dict(),
        })

    return {
        "incident_id": incident_id,
        "generated_at": now_ms(),
        "n": len(scenarios),
        "seed": seed,
        "best": by_label.get("best", []),
        "expected": by_label.get("expected", []),
        "worst": by_label.get("worst", []),
    }


# ── World state (DBN) ───────────────────────────────────────────────────────


@router.get("/{incident_id}/world-state")
def get_world_state(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return DBN state distribution from WorldStateEstimator."""
    from app.fusion.world_state import WorldStateEstimator

    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    ev_data = _load_json("dbn_evidence.json")
    estimator = WorldStateEstimator(
        hazard_types=(ev_data["hazard_type"],),
        prior=ev_data.get("prior"),
    )
    evidence: dict[tuple[str, int] | str, str | int] = {}
    for entry in ev_data["evidence"]:
        evidence[entry["node"]] = entry["value"]
    estimator.add_evidence(evidence)

    dist = estimator.filter_state(ev_data["hazard_type"])
    return {
        "incident_id": incident_id,
        "hazard_type": ev_data["hazard_type"],
        "state_distribution": dist,
        "current_slice": estimator.current_slice,
        "generated_at": now_ms(),
    }


# ── Calibration ─────────────────────────────────────────────────────────────


@router.get("/{incident_id}/calibration")
def get_calibration(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return Brier score, ECE, and conformal coverage from fixture data."""
    import numpy as np

    from app.fusion.calibration import ConformalCalibrator

    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    cal_data = _load_json("calibration.json")
    y_true = np.array(cal_data["y_true"], dtype=float)
    y_prob = np.array(cal_data["y_prob"], dtype=float)
    y_lower = np.array(cal_data["y_pred_lower"], dtype=float)
    y_upper = np.array(cal_data["y_pred_upper"], dtype=float)

    cal = ConformalCalibrator()
    metrics = cal.store_metrics(y_true, y_prob, y_lower, y_upper)
    reliability = metrics.get("reliability", {})

    return {
        "incident_id": incident_id,
        "generated_at": now_ms(),
        "alpha": cal_data["alpha"],
        "brier_score": metrics.get("brier_score"),
        "ece": metrics.get("ece"),
        "nll": metrics.get("nll"),
        "false_confidence_rate": metrics.get("false_confidence_rate"),
        "conformal_coverage": metrics.get("conformal_coverage"),
        "interval_width": metrics.get("interval_width"),
        "reliability": reliability,
        "n_samples": len(y_true),
    }


@router.get("/{incident_id}/flood-map")
def get_flood_map(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)
    resolution = _route_resolution("sar-flood-mapping")
    if resolution.state is not ContractState.available:
        return _contract_response("flood_mapping", resolution)
    response = _contract_response(
        "flood_mapping",
        ContractResolution(ContractState.abstain, resolution.contract, "input_required"),
    )
    response["incident_id"] = incident_id
    response["generated_at"] = now_ms()
    return response


@router.post("/{incident_id}/flood-map")
def post_flood_map(
    incident_id: str,
    request: Request,
    payload: FloodMapRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)
    if payload.input_data is None:
        versions = payload.versions()
        resolution = _route_resolution("sar-flood-mapping", versions)
        return _contract_response(
            "flood_mapping",
            ContractResolution(ContractState.abstain, resolution.contract, "input_required"),
        )
    if payload.crs is None or payload.resolution_m is None or payload.quality is None:
        raise HTTPException(status_code=422, detail="raster metadata is required")
    try:
        tensor = np.asarray(payload.input_data, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="malformed inference input") from exc
    prepared = prepare_raster_input(
        tensor,
        RasterInputMetadata(
            crs=payload.crs,
            resolution_m=payload.resolution_m,
            valid_fraction=payload.quality.valid_fraction,
            nodata_fraction=payload.quality.nodata_fraction,
            snr_db=payload.quality.snr_db,
        ),
        (1, 2, 512, 512),
    )
    if prepared.state is ContractState.incompatible:
        raise HTTPException(status_code=422, detail=prepared.reason)
    versions = payload.versions()
    resolution = _route_resolution("sar-flood-mapping", versions)
    if prepared.state is ContractState.abstain:
        return _contract_response(
            "flood_mapping",
            ContractResolution(ContractState.abstain, resolution.contract, prepared.reason),
        )
    if resolution.state is ContractState.incompatible:
        raise HTTPException(status_code=422, detail=resolution.reason)
    if resolution.state is not ContractState.available:
        return _contract_response("flood_mapping", resolution)
    if prepared.tensor is None:
        raise HTTPException(status_code=422, detail="validated raster tensor is required")
    try:
        result = _SERVING.run_registered_inference(
            "sar-flood-mapping",
            {"input": prepared.tensor},
            versions,
        )
    except InferenceContractError as exc:
        if exc.resolution.state is ContractState.incompatible:
            raise HTTPException(status_code=422, detail=exc.resolution.reason) from exc
        return _contract_response("flood_mapping", exc.resolution)
    output_name, output = next(iter(result["outputs"].items()))
    logits = np.asarray(output, dtype=np.float32)
    logits -= logits.max(axis=1, keepdims=True)
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    flood_probability = probabilities[:, 1, ...]
    return {
        "incident_id": incident_id,
        "status": result["state"],
        "feature": "flood_mapping",
        "prediction": {
            "output_name": output_name,
            "shape": list(output.shape),
            "class_index": 1,
            "probability_mean": float(flood_probability.mean()),
            "probability_min": float(flood_probability.min()),
            "probability_max": float(flood_probability.max()),
        },
        "provenance": result["provenance"],
        "review_status": "draft",
        "generated_at": now_ms(),
    }


@router.get("/{incident_id}/flood-ensemble")
def get_flood_ensemble(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)
    resolution = _route_resolution("sar-flood-mapping")
    if resolution.state is ContractState.unavailable:
        return _contract_response("ensemble", resolution)
    return _contract_response(
        "ensemble",
        ContractResolution(ContractState.abstain, resolution.contract, "ensemble_input_required"),
    )
