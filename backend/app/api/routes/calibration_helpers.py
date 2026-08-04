from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import numpy as np
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.fusion.calibration import (
    CALIBRATION_POLICIES,
    ConformalCalibrator,
    policy_for_output_type,
    release_gate,
)
from app.fusion.calibration_policy import OutputType
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.perception.serving import ContractState, resolve_contract

DEFAULT_ALPHA = 0.1
FIT_FRACTION = 0.7
MODEL_OUTPUT_TYPES = {
    "sar-flood-mapping": OutputType.SAR_SEGMENTATION,
    "building-damage": OutputType.DAMAGE_PROBABILITY,
    "incident-nlp": OutputType.NLP_PROBABILITY,
}


def store_samples(db: Session, incident_id: str, org_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    model_id = payload.get("model_id")
    if not model_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="model_id is required")
    samples = payload.get("samples")
    if not samples or not isinstance(samples, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="samples (non-empty list) is required")
    h3_zone = payload.get("h3_zone")
    timestamp = now_ms()
    rows: list[tuple[str, str, str, str, str | None, Any, Any, int]] = []
    for sample in samples:
        x_val = sample.get("X")
        y_val = sample.get("y")
        if x_val is None or y_val is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="each sample must have X and y")
        rows.append((generate_ulid(), org_id, incident_id, model_id, h3_zone, x_val, y_val, timestamp))
    db.execute(
        text('INSERT INTO calibration_data (id, org_id, incident_id, model_id, h3_zone, "X", y, created_at) '
             "VALUES (:id, :org_id, :incident_id, :model_id, :h3_zone, CAST(:X AS jsonb), CAST(:y AS jsonb), :created_at)"),
        [{"id": row[0], "org_id": row[1], "incident_id": row[2], "model_id": row[3], "h3_zone": row[4],
          "X": json.dumps(row[5]), "y": json.dumps(row[6]), "created_at": row[7]} for row in rows],
    )
    db.commit()
    return {"stored": len(rows), "incident_id": incident_id, "model_id": model_id}


def fit_samples(db: Session, incident_id: str, org_id: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    body = payload or {}
    alpha = float(body.get("alpha", DEFAULT_ALPHA))
    model_id = body.get("model_id")
    if isinstance(model_id, str) and model_id in MODEL_OUTPUT_TYPES:
        policy = policy_for_output_type(MODEL_OUTPUT_TYPES[model_id])
        resolution = resolve_contract(model_id)
        gate = release_gate(policy, resolution.state is ContractState.available, None, None)
        if not gate.allowed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"status": gate.status, "reason": gate.reason,
                "model_id": model_id, "output_type": policy.output_type.value})
    params: dict[str, Any] = {"org_id": org_id, "incident_id": incident_id}
    sql = 'SELECT "X", y FROM calibration_data WHERE org_id = :org_id AND incident_id = :incident_id'
    if model_id is not None:
        sql += " AND model_id = :model_id"
        params["model_id"] = model_id
    result = db.execute(text(sql + " ORDER BY created_at"), params)
    rows = result.fetchall()
    if len(rows) < 10:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"need at least 10 calibration samples, found {len(rows)}")
    X = np.array([row[0] for row in rows], dtype=float)
    y = np.array([row[1] for row in rows], dtype=float)
    split = max(1, int(len(y) * FIT_FRACTION))
    fit_y = y[:split]
    pred_y = y[split:]
    cal = ConformalCalibrator(alpha=alpha, mode="static")
    cal.fit(X[:split], fit_y, alpha=alpha)
    pred_result = cal.predict(X[split:])
    lower = np.array(pred_result["interval_lower"])
    upper = np.array(pred_result["interval_upper"])
    coverage = ConformalCalibrator.compute_coverage(pred_y, lower, upper)
    interval_width = float(np.mean(upper - lower))
    y_prob = np.clip((pred_y - lower) / (upper - lower + 1e-12), 0.0, 1.0)
    y_binary = (pred_y > np.median(pred_y)).astype(float)
    return {"incident_id": incident_id, "model_id": model_id, "alpha": alpha, "n_samples": len(rows), "n_fit": split,
        "n_predict": len(pred_y), "intervals": {"prediction": pred_result["prediction"],
        "interval_lower": pred_result["interval_lower"], "interval_upper": pred_result["interval_upper"],
        "interval_width": pred_result["interval_width"]}, "metrics": {
        "conformal_coverage": coverage, "interval_width": interval_width,
        "brier_score": ConformalCalibrator.compute_brier_score(y_binary, y_prob),
        "ece": ConformalCalibrator.compute_ece(y_binary, y_prob)}}


def get_incident_for_calibration(db: Session, org_id: str, incident_id: str) -> None:
    found = db.execute(text("SELECT 1 FROM incidents WHERE org_id = :org_id AND id = :incident_id"),
                       {"org_id": org_id, "incident_id": incident_id}).first()
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="incident not found")


def list_contracts(db: Session, org_id: str, incident_id: str) -> dict[str, Any]:
    get_incident_for_calibration(db, org_id, incident_id)
    contracts: list[dict[str, Any]] = []
    for policy in CALIBRATION_POLICIES:
        model_id = next((candidate for candidate, output_type in MODEL_OUTPUT_TYPES.items() if output_type is policy.output_type), None)
        resolution = resolve_contract(model_id) if model_id is not None else None
        available = resolution is not None and resolution.state is ContractState.available
        gate = release_gate(policy, available, None, None)
        contracts.append({"output_type": policy.output_type.value, "method": policy.method,
            "confidence_level": policy.confidence_level, "minimum_samples": policy.minimum_samples,
            "subgroup_minimum_samples": policy.subgroup_minimum_samples,
            "hazard_minimum_samples": policy.hazard_minimum_samples, "required_metrics": list(policy.required_metrics),
            "thresholds": asdict(policy.thresholds), "shift_trigger": policy.shift_trigger,
            "recalibration_cadence_days": policy.recalibration_cadence_days,
            "release": {"status": gate.status, "reason": gate.reason}})
    return {"incident_id": incident_id, "contracts": contracts}
