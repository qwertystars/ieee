"""Sensing actions, damage assessment, and NLP report API routes.

Wires the SOTA sensing and perception engines to incident-scoped endpoints:
  - GET  /{incident_id}/sensing-actions               — EVI-ranked catalog
  - POST /{incident_id}/sensing-actions/{action_id}/dispatch — pending task
  - POST /{incident_id}/damage-assessment               — building damage (degrades)
  - POST /{incident_id}/nlp-report                       — citizen NLP (degrades)

ML features (damage, nlp) degrade gracefully when model weights are
unavailable, returning a ``model_unavailable`` response.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.lib.time import now_ms
from app.models.incident import Incident
from app.models.user import User

logger = logging.getLogger("app.api.routes.sensing")

router = APIRouter(prefix="/incidents", tags=["sensing"])

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")


def _weights_available(r2_key: str) -> bool:
    """Check if model weights exist in the local cache directory."""
    local_path = os.path.join(_DATA_DIR, r2_key.replace("/", os.sep))
    return os.path.exists(local_path)


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


def _get_incident(db: Session, org_id: str, incident_id: str) -> Incident:
    inc = db.execute(
        select(Incident).where(
            Incident.org_id == org_id, Incident.id == incident_id,
        )
    ).scalars().first()
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


# ── Sensing actions ─────────────────────────────────────────────────────────


@router.get("/{incident_id}/sensing-actions")
def list_sensing_actions(
    incident_id: str,
    request: Request,
    top: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return EVI-ranked sensing actions from the SensingActionCatalog."""
    from app.sensing.catalog import SensingActionCatalog

    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    catalog = SensingActionCatalog()
    if top is not None:
        recs = catalog.get_top_actions(incident_id, n=top)
        actions: list[dict[str, Any]] = [
            {
                "action": {
                    "id": r.action.id,
                    "action_type": r.action.action_type.value,
                    "description": r.action.description,
                    "target": r.action.target,
                    "cost": {
                        "time_minutes": r.action.cost.time_minutes,
                        "resource": r.action.cost.resource,
                        "risk_level": r.action.cost.risk_level.value,
                    },
                    "expected_information_gain": r.action.expected_information_gain,
                    "potential_impact_on_plan": r.action.potential_impact_on_plan,
                },
                "display_text": r.display_text,
            }
            for r in recs
        ]
    else:
        catalog_actions = catalog.get_actions()
        actions = [
            {
                "id": a.id,
                "action_type": a.action_type.value,
                "description": a.description,
                "target": a.target,
                "cost": {
                    "time_minutes": a.cost.time_minutes,
                    "resource": a.cost.resource,
                    "risk_level": a.cost.risk_level.value,
                },
                "expected_information_gain": a.expected_information_gain,
                "potential_impact_on_plan": a.potential_impact_on_plan,
            }
            for a in catalog_actions
        ]

    return {
        "incident_id": incident_id,
        "actions": actions,
        "count": len(actions),
        "generated_at": now_ms(),
    }


@router.post("/{incident_id}/sensing-actions/{action_id}/dispatch")
def dispatch_sensing_action(
    incident_id: str,
    action_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Dispatch a sensing action — creates a pending task for human approval."""
    from app.sensing.catalog import SensingActionCatalog

    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    catalog = SensingActionCatalog()
    if catalog.get_action(action_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown sensing action: {action_id}",
        )

    result = catalog.dispatch_action(
        incident_id=incident_id,
        action_id=action_id,
        db=db,
        org_id=org_id,
    )
    return {
        "task_id": result.task_id,
        "action_id": result.action_id,
        "incident_id": result.incident_id,
        "status": result.status,
        "dispatched_by": user.email,
        "dispatched_at": now_ms(),
    }


# ── Damage assessment (ML — degrades gracefully) ────────────────────────────


class DamageRequest(BaseModel):
    """Request body for damage assessment."""

    image_data: list[list[list[float]]] | None = None
    flood_prob: float = 0.5
    damage_prob: float = 0.3
    road_class: str = "residential"


@router.post("/{incident_id}/damage-assessment")
def assess_damage(
    incident_id: str,
    request: Request,
    payload: DamageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Assess building damage and road passability. Degrades when weights missing."""
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    if _check_placeholder_models():
        return _placeholder_model_response("damage")

    if not _weights_available("models/building-damage-v1.0.0.onnx"):
        return _model_unavailable("damage")

    try:
        import numpy as np

        from app.perception.damage import DamageAssessor

        assessor = DamageAssessor()
        image = np.array(payload.image_data or [[[0.0]]], dtype=np.float32)
        damage_result = assessor.assess_building_damage(image)

        road_segment = {
            "id": "road_segment_1",
            "properties": {"road_class": payload.road_class},
        }
        road_result = assessor.assess_road_passability(
            road_segment, payload.flood_prob, payload.damage_prob,
        )

        return {
            "incident_id": incident_id,
            "status": "ok",
            "feature": "damage",
            "building_damage": {
                "damage_class": damage_result.damage_class.value,
                "probability": damage_result.probability,
                "uncertainty": damage_result.uncertainty,
                "class_probabilities": damage_result.class_probabilities,
                "model_version": damage_result.model_version,
            },
            "road_passability": {
                "vehicle_class_passabilities": road_result.vehicle_class_passabilities,
                "traversal_speed": road_result.traversal_speed,
                "failure_time": road_result.failure_time,
                "uncertainty": road_result.uncertainty,
            },
            "generated_at": now_ms(),
        }
    except Exception as exc:
        logger.warning("damage assessment failed: %s", exc)
        return _model_unavailable("damage")


# ── NLP report (ML — degrades gracefully) ──────────────────────────────────


class NLPRequest(BaseModel):
    """Request body for citizen report NLP processing."""

    text: str | None = None
    audio_base64: str | None = None
    image_base64: str | None = None


@router.post("/{incident_id}/nlp-report")
def process_nlp_report(
    incident_id: str,
    request: Request,
    payload: NLPRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Process a citizen report through the NLP pipeline. Degrades when weights missing."""
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    if _check_placeholder_models():
        return _placeholder_model_response("nlp")

    if not _weights_available("models/incident-nlp-v1.0.0.onnx"):
        return _model_unavailable("nlp")

    try:
        from app.perception.nlp import CitizenReportProcessor

        processor = CitizenReportProcessor(org_id=org_id)
        report = processor.process_report(text=payload.text)

        return {
            "incident_id": incident_id,
            "status": "ok",
            "feature": "nlp",
            "report_id": report.report_id,
            "language": report.language,
            "urgency": report.urgency.value,
            "category": report.category.value,
            "credibility": report.credibility,
            "needs_human_review": report.needs_human_review,
            "geolocation": {
                "type": report.geolocation.type.value,
                "place_names": report.geolocation.place_names,
                "uncertainty_m": report.geolocation.uncertainty_m,
                "confidence": report.geolocation.confidence,
            },
            "pii_spans_count": len(report.pii_spans),
            "generated_at": now_ms(),
        }
    except Exception as exc:
        logger.warning("nlp report processing failed: %s", exc)
        return _model_unavailable("nlp")
