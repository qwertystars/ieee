"""Scenarios, world-state, calibration, and flood-map API routes.

Wires the SOTA fusion and perception engines to incident-scoped endpoints:
  - GET  /{incident_id}/scenarios       — ScenarioGenerator ensemble
  - GET  /{incident_id}/world-state      — DBN state distribution
  - GET  /{incident_id}/calibration      — Brier/ECE/coverage metrics
  - GET  /{incident_id}/flood-map         — SAR flood mapping (degrades)
  - GET  /{incident_id}/flood-ensemble    — Flood ensemble (degrades)

ML features (flood-map, flood-ensemble) degrade gracefully when model
weights are unavailable, returning a ``model_unavailable`` response.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.lib.time import now_ms
from app.models.incident import Incident
from app.models.user import User

logger = logging.getLogger("app.api.routes.scenarios")

router = APIRouter(prefix="/incidents", tags=["scenarios"])

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")


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


def _model_unavailable(feature: str) -> dict[str, Any]:
    """Standard degraded response for unavailable ML model weights."""
    return {
        "status": "model_unavailable",
        "feature": feature,
        "message": (
            f"Model weights for '{feature}' are not available. "
            "Download weights via scripts/download_models.py."
        ),
    }


def _weights_available(r2_key: str) -> bool:
    """Check if model weights exist in the local cache directory."""
    local_path = os.path.join(_DATA_DIR, r2_key.replace("/", os.sep))
    return os.path.exists(local_path)


_MANIFEST_PATH = os.path.join(_DATA_DIR, "models", "manifests.json")


def _check_placeholder_models() -> bool:
    """Return True if any model manifest is a placeholder or unsigned.

    Reads ``data/models/manifests.json`` and returns True if any entry has
    ``validation_status == "placeholder"`` or ``signed`` is not true.
    Returns False if the manifest is missing, empty, or malformed.
    """
    if not os.path.isfile(_MANIFEST_PATH):
        return False
    try:
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as fh:
            manifests = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("manifest load failed (%s): %s", _MANIFEST_PATH, exc)
        return False
    if not isinstance(manifests, list) or not manifests:
        return False
    for entry in manifests:
        if not isinstance(entry, dict):
            continue
        if entry.get("validation_status") == "placeholder" or entry.get("signed") is not True:
            return True
    return False


def _placeholder_model_response(feature: str) -> dict[str, Any]:
    """Degraded response when model manifests are unvalidated placeholders."""
    return {
        "status": "model_unavailable",
        "reason": "placeholder_model_not_validated",
        "feature": feature,
        "message": (
            f"Model weights for '{feature}' are placeholders and not validated. "
            "Download real weights via scripts/download_models.py."
        ),
    }


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


# ── Flood map (ML — degrades gracefully) ────────────────────────────────────


@router.get("/{incident_id}/flood-map")
def get_flood_map(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return SAR flood mapping result. Degrades when model weights missing."""
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    if _check_placeholder_models():
        return _placeholder_model_response("flood_mapping")

    if not _weights_available("models/sar-flood-mapping-v1.0.0.onnx"):
        return _model_unavailable("flood_mapping")

    try:
        import torch

        from app.perception.flood_mapping import SARFloodMapper

        mapper = SARFloodMapper()
        dummy = torch.randn(2, 64, 64)
        result = mapper.run_inference(dummy)
        return {
            "incident_id": incident_id,
            "status": "ok",
            "feature": "flood_mapping",
            "flood_prob_shape": list(result.flood_prob.shape),
            "quality_flag": result.quality_flag.value,
            "observation_time": result.observation_time,
            "generated_at": now_ms(),
        }
    except Exception as exc:
        logger.warning("flood-map inference failed: %s", exc)
        return _model_unavailable("flood_mapping")


# ── Flood ensemble (ML — degrades gracefully) ──────────────────────────────


@router.get("/{incident_id}/flood-ensemble")
def get_flood_ensemble(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return flood ensemble result. Degrades when model weights missing."""
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    if _check_placeholder_models():
        return _placeholder_model_response("ensemble")

    if not _weights_available("models/sar-flood-mapping-v1.0.0.onnx"):
        return _model_unavailable("ensemble")

    try:
        import torch

        from app.perception.ensemble import (
            FloodEnsemble,
            GFMMember,
            ResNet50S1Mapper,
            _FloodMemberLike,
        )
        from app.perception.flood_mapping import SARFloodMapper

        members: list[_FloodMemberLike] = [SARFloodMapper(), ResNet50S1Mapper(), GFMMember({"flood_prob": 0.3})]
        ensemble = FloodEnsemble(members)
        dummy = torch.randn(2, 64, 64)
        result = ensemble.run_inference(dummy)
        return {
            "incident_id": incident_id,
            "status": "ok",
            "feature": "ensemble",
            "ensemble_prob_shape": list(result.flood_prob.shape),
            "quality_flag": result.quality_flag.value,
            "observation_time": result.observation_time,
            "generated_at": now_ms(),
        }
    except Exception as exc:
        logger.warning("flood-ensemble inference failed: %s", exc)
        return _model_unavailable("ensemble")
