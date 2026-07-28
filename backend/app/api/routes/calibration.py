"""Calibration API — store calibration samples and fit conformal intervals.

Exposes the ConformalCalibrator through two routes scoped to an incident:
  - POST /api/incidents/{id}/calibration/data — store calibration samples
  - POST /api/incidents/{id}/calibration/fit  — fit calibrator, return
    prediction intervals + Brier/ECE/coverage metrics

Both routes require authentication and enforce org_id tenancy via the
OrgContextMiddleware (org_id is resolved from the JWT, never the client).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.fusion.calibration import ConformalCalibrator
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.user import User

logger = logging.getLogger("app.api.routes.calibration")

router = APIRouter(
    prefix="/incidents/{incident_id}/calibration", tags=["calibration"]
)

_DEFAULT_ALPHA = 0.1
_FIT_FRACTION = 0.7


@router.post("/data", status_code=status.HTTP_201_CREATED)
def store_calibration_data(
    incident_id: str,
    request: Request,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Store calibration samples for an incident.

    Accepts a JSON body with:
      - model_id (str, required)
      - h3_zone (str, optional)
      - samples (list of {X: [floats], y: float}, required)

    Each sample is stored as a row in the calibration_data table. Returns
    201 with the count of samples stored.
    """
    org_id = request.state.org_id or ""
    model_id = payload.get("model_id")
    if not model_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="model_id is required",
        )
    samples = payload.get("samples")
    if not samples or not isinstance(samples, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="samples (non-empty list) is required",
        )
    h3_zone = payload.get("h3_zone")
    ts = now_ms()
    rows: list[tuple[str, str, str, str, str | None, Any, Any, int]] = []
    for sample in samples:
        x_val = sample.get("X")
        y_val = sample.get("y")
        if x_val is None or y_val is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="each sample must have X and y",
            )
        row_id = generate_ulid()
        rows.append(
            (row_id, org_id, incident_id, model_id, h3_zone, x_val, y_val, ts)
        )
    db.execute(
        text(
            'INSERT INTO calibration_data '
            '(id, org_id, incident_id, model_id, h3_zone, "X", y, created_at) '
            "VALUES (:id, :org_id, :incident_id, :model_id, :h3_zone, "
            "CAST(:X AS jsonb), CAST(:y AS jsonb), :created_at)"
        ),
        [
            {
                "id": r[0],
                "org_id": r[1],
                "incident_id": r[2],
                "model_id": r[3],
                "h3_zone": r[4],
                "X": json.dumps(r[5]),
                "y": json.dumps(r[6]),
                "created_at": r[7],
            }
            for r in rows
        ],
    )
    db.commit()
    return {"stored": len(rows), "incident_id": incident_id, "model_id": model_id}


@router.post("/fit")
def fit_calibration(
    incident_id: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Fit a ConformalCalibrator on stored samples and return intervals + metrics.

    Reads all calibration_data rows for the incident, stacks X and y into
    numpy arrays, fits on the first 70% and predicts on the remaining 30%.
    Returns prediction intervals plus Brier, ECE, and conformal coverage
    metrics computed on the held-out prediction set.
    """
    org_id = request.state.org_id or ""
    alpha = float((payload or {}).get("alpha", _DEFAULT_ALPHA))
    model_id = (payload or {}).get("model_id")

    params: dict[str, Any] = {"org_id": org_id, "incident_id": incident_id}
    sql = (
        'SELECT "X", y FROM calibration_data '
        "WHERE org_id = :org_id AND incident_id = :incident_id"
    )
    if model_id is not None:
        sql += " AND model_id = :model_id"
        params["model_id"] = model_id
    sql += " ORDER BY created_at"
    result = db.execute(text(sql), params)
    rows = result.fetchall()
    if len(rows) < 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"need at least 10 calibration samples, found {len(rows)}",
        )
    X = np.array([row[0] for row in rows], dtype=float)
    y = np.array([row[1] for row in rows], dtype=float)
    split = max(1, int(len(y) * _FIT_FRACTION))
    fit_X, fit_y = X[:split], y[:split]
    pred_X, pred_y = X[split:], y[split:]
    cal = ConformalCalibrator(alpha=alpha, mode="static")
    cal.fit(fit_X, fit_y, alpha=alpha)
    pred_result = cal.predict(pred_X)
    lower = np.array(pred_result["interval_lower"])
    upper = np.array(pred_result["interval_upper"])
    coverage = ConformalCalibrator.compute_coverage(pred_y, lower, upper)
    interval_width = float(np.mean(upper - lower))
    y_prob = np.clip(
        (pred_y - lower) / (upper - lower + 1e-12), 0.0, 1.0
    )
    y_binary = (pred_y > np.median(pred_y)).astype(float)
    brier = ConformalCalibrator.compute_brier_score(y_binary, y_prob)
    ece = ConformalCalibrator.compute_ece(y_binary, y_prob)
    return {
        "incident_id": incident_id,
        "model_id": model_id,
        "alpha": alpha,
        "n_samples": len(rows),
        "n_fit": split,
        "n_predict": len(pred_y),
        "intervals": {
            "prediction": pred_result["prediction"],
            "interval_lower": pred_result["interval_lower"],
            "interval_upper": pred_result["interval_upper"],
            "interval_width": pred_result["interval_width"],
        },
        "metrics": {
            "conformal_coverage": coverage,
            "interval_width": interval_width,
            "brier_score": brier,
            "ece": ece,
        },
    }
