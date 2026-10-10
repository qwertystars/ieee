"""Sensing actions, damage assessment, and NLP report API routes.

Wires the SOTA sensing and perception engines to incident-scoped endpoints:
  - GET  /{incident_id}/sensing-actions               — EVI-ranked catalog
  - POST /{incident_id}/sensing-actions/{action_id}/dispatch — pending task
  - POST /{incident_id}/damage-assessment               — building damage (degrades)
  - POST /{incident_id}/nlp-report                       — citizen NLP (degrades)

ML features expose explicit contract states when artifacts or calibration are unavailable.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import StrictFloat, StrictStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.scenarios import RasterRequest
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

logger = logging.getLogger("app.api.routes.sensing")

router = APIRouter(prefix="/incidents", tags=["sensing"])

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
_SERVING = ModelServing(SessionLocal, cache_dir=_DATA_DIR)


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


class DamageRequest(RasterRequest):
    image_data: list[list[list[list[StrictFloat]]]] | None = None
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
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)
    versions = payload.versions()
    base_resolution = resolve_contract("building-damage", versions)
    if payload.image_data is not None:
        if payload.crs is None or payload.resolution_m is None or payload.quality is None:
            raise HTTPException(status_code=422, detail="raster metadata is required")
        try:
            tensor = np.asarray(payload.image_data, dtype=np.float32)
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
            (1, 4, 256, 256),
        )
        if prepared.state is ContractState.incompatible:
            raise HTTPException(status_code=422, detail=prepared.reason)
        if prepared.state is ContractState.abstain:
            response = _contract_response(
                "damage",
                ContractResolution(
                    ContractState.abstain,
                    base_resolution.contract,
                    prepared.reason,
                ),
            )
            response["incident_id"] = incident_id
            return response
    else:
        prepared = None
    resolution = _route_resolution("building-damage", versions)
    if resolution.state is ContractState.incompatible:
        raise HTTPException(status_code=422, detail=resolution.reason)
    if resolution.state is not ContractState.available:
        response = _contract_response("damage", resolution)
        response["incident_id"] = incident_id
        return response
    if payload.image_data is None:
        response = _contract_response(
            "damage",
            ContractResolution(ContractState.abstain, resolution.contract, "input_required"),
        )
        response["incident_id"] = incident_id
        return response
    if prepared is None or prepared.tensor is None:
        raise HTTPException(status_code=422, detail="validated raster tensor is required")
    try:
        result = _SERVING.run_registered_inference(
            "building-damage",
            {"input": prepared.tensor},
            versions,
        )
    except InferenceContractError as exc:
        if exc.resolution.state is ContractState.incompatible:
            raise HTTPException(status_code=422, detail=exc.resolution.reason) from exc
        return _contract_response("damage", exc.resolution)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="malformed inference input") from exc
    except (OSError, RuntimeError, ImportError) as exc:
        logger.warning("damage inference failed: %s", exc)
        return _contract_response("damage", ContractResolution(
            ContractState.unavailable, resolution.contract, "inference_unavailable",
        ))
    output_name, output = next(iter(result["outputs"].items()))
    logits = np.asarray(output, dtype=np.float32)
    logits -= logits.max(axis=1, keepdims=True)
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    class_probabilities = probabilities.mean(axis=(0, 2, 3))
    return {
        "incident_id": incident_id,
        "status": result["state"],
        "feature": "damage",
        "prediction": {
            "output_name": output_name,
            "shape": list(output.shape),
            "class_index": int(np.argmax(class_probabilities)),
            "class_probabilities": class_probabilities.tolist(),
        },
        "provenance": result["provenance"],
        "review_status": "draft",
        "generated_at": now_ms(),
    }


# ── NLP report (ML — degrades gracefully) ──────────────────────────────────


class NLPRequest(RasterRequest):
    text: StrictStr | None = None
    audio_base64: StrictStr | None = None
    image_base64: StrictStr | None = None


@router.post("/{incident_id}/nlp-report")
def process_nlp_report(
    incident_id: str,
    request: Request,
    payload: NLPRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)
    versions = payload.versions()
    resolution = _route_resolution("incident-nlp", versions)
    if resolution.state is ContractState.incompatible:
        raise HTTPException(status_code=422, detail=resolution.reason)
    if payload.text is not None and not payload.text.strip():
        raise HTTPException(status_code=422, detail="text input is empty")
    if payload.text is None and (payload.audio_base64 is not None or payload.image_base64 is not None):
        raise HTTPException(status_code=422, detail="unsupported NLP input modality")
    if resolution.state is not ContractState.available:
        response = _contract_response("nlp", resolution)
        response["incident_id"] = incident_id
        return response
    if not payload.text:
        response = _contract_response(
            "nlp",
            ContractResolution(ContractState.abstain, resolution.contract, "input_required"),
        )
        response["incident_id"] = incident_id
        return response
    try:
        from transformers import AutoTokenizer

        from app.perception.nlp import prepare_text_for_model

        tokenizer = AutoTokenizer.from_pretrained(
            os.path.join(_DATA_DIR, "models", "incident-nlp-tokenizer"),
            local_files_only=True,
        )
        encoded = tokenizer(
            prepare_text_for_model(payload.text),
            padding="max_length",
            truncation=True,
            max_length=128,
            return_tensors="np",
        )
        result = _SERVING.run_registered_inference(
            "incident-nlp",
            {
                "input_ids": np.asarray(encoded["input_ids"], dtype="int64"),
                "attention_mask": np.asarray(encoded["attention_mask"], dtype="int64"),
            },
            versions,
        )
    except InferenceContractError as exc:
        if exc.resolution.state is ContractState.incompatible:
            raise HTTPException(status_code=422, detail=exc.resolution.reason) from exc
        return _contract_response("nlp", exc.resolution)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        logger.warning("nlp inference unavailable: %s", exc)
        return _contract_response("nlp", ContractResolution(
            ContractState.unavailable, resolution.contract, "inference_unavailable",
        ))
    output_name, output = next(iter(result["outputs"].items()))
    logits = np.asarray(output, dtype=np.float32)
    logits -= logits.max(axis=1, keepdims=True)
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    return {
        "incident_id": incident_id,
        "status": result["state"],
        "feature": "nlp",
        "prediction": {
            "output_name": output_name,
            "shape": list(output.shape),
            "class_index": int(np.argmax(probabilities[0])),
            "class_probabilities": probabilities[0].tolist(),
        },
        "provenance": result["provenance"],
        "review_status": "draft",
        "generated_at": now_ms(),
    }
