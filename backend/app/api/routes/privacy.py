"""Privacy + ABAC + fairness API routes.

Wires the ABACEngine and FairnessEngine to incident-scoped endpoints:
  - GET /api/incidents/{id}/access-check?action=X&resource=Y
  - GET /api/incidents/{id}/fairness-report

The access-check endpoint evaluates the current user's ABAC policy against
a subject derived from the resource query param, returning allowed/denied
with jurisdiction, sensitivity, and override reasoning.

The fairness-report endpoint builds FairnessZone tuples from the incident's
Zone rows, constructs original (unconstrained) and fair (constrained) plans,
and returns the EquityReport from FairnessEngine.compute_equity_report().
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.abac import ABACEngine, ELEVATED_ROLES
from app.auth.abac_types import Actor, Context, Subject
from app.deps import get_current_user, get_db
from app.lib.privacy import ProgressivePrecision
from app.models.entities import Zone as ZoneModel
from app.models.incident import Incident
from app.models.user import User
from app.optimizer.fairness import FairnessEngine
from app.optimizer.fairness_types import FairnessZone, Plan

logger = logging.getLogger("app.api.routes.privacy")

router = APIRouter(prefix="/incidents", tags=["privacy"])

# Role -> coordinate decimal places for progressive precision.
# viewer ~1km (2 dp), field_responder ~100m (3 dp), admin exact.
_ROLE_COORD_DECIMALS: dict[str, int | None] = {
    "viewer": 2,
    "field_responder": 3,
    "responder_coordinator": 3,
    "emergency_manager": None,
    "shelter_manager": 4,
    "admin": None,
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


def _build_actor(user: User, incident_id: str) -> Actor:
    """Build an ABAC Actor from the authenticated user."""
    return Actor(
        user_id=user.id,
        role=user.role,
        org_id=user.org_id,
        incident_assignments=(incident_id,),
        jurisdiction="all" if user.role in ELEVATED_ROLES else "zone_default",
    )


def _build_subject(resource: str, org_id: str, incident_id: str) -> Subject:
    """Build an ABAC Subject from the resource query param.

    The resource format is ``type:id`` (e.g. ``observation:01HTEST``).
    If no type prefix is given, defaults to ``observation``.
    """
    parts = resource.split(":", 1)
    subject_type = parts[0] if len(parts) > 1 else "observation"
    return Subject(
        type=subject_type,
        sensitivity="internal",
        org_id=org_id,
        incident_id=incident_id,
        jurisdiction="zone_default",
    )


@router.get("/{incident_id}/access-check")
def access_check(
    incident_id: str,
    request: Request,
    action: str = Query(..., description="ABAC action: read, write, delete, approve, dispatch, override"),
    resource: str = Query(..., description="Resource type:id (e.g. observation:01HTEST)"),
    sensitivity: str = Query("internal", description="Data sensitivity: public, internal, sensitive"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """GET /api/incidents/{id}/access-check — ABAC enforcement.

    Evaluates whether the current user can perform ``action`` on ``resource``
    in the context of this incident. Returns allowed/denied with reasoning
    covering jurisdiction, sensitivity, and emergency override status.
    """
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    actor = _build_actor(user, incident_id)
    subject = _build_subject(resource, org_id, incident_id)
    # Override sensitivity from query param if provided.
    subject = Subject(
        type=subject.type,
        sensitivity=sensitivity,
        org_id=subject.org_id,
        incident_id=subject.incident_id,
        jurisdiction=subject.jurisdiction,
        task_id=subject.task_id,
    )
    context = Context(
        current_org_id=org_id,
        current_incident_id=incident_id,
        emergency_mode=False,
    )

    engine = ABACEngine()
    override = engine.get_override(user.id)
    allowed = engine.can(actor, action, subject, context)

    # Build reasoning for the decision.
    reasons: list[str] = []
    if actor.org_id != subject.org_id:
        reasons.append("org mismatch: actor and subject belong to different orgs")
    if actor.role not in ELEVATED_ROLES and actor.jurisdiction != "all":
        if actor.jurisdiction != subject.jurisdiction:
            reasons.append(f"jurisdiction mismatch: actor='{actor.jurisdiction}', subject='{subject.jurisdiction}'")
    if subject.sensitivity == "sensitive" and actor.role not in ELEVATED_ROLES:
        if override is None:
            reasons.append("sensitive data requires elevated role or emergency override")
    if action not in ("read", "write", "delete", "approve", "dispatch", "override"):
        reasons.append(f"unknown action '{action}'")
    if override is not None:
        reasons.append(f"emergency override active (reason: {override.reason})")
    if not reasons and allowed:
        reasons.append("all ABAC checks passed (role, jurisdiction, sensitivity, override)")

    return {
        "incident_id": incident_id,
        "allowed": allowed,
        "action": action,
        "resource": resource,
        "subject_type": subject.type,
        "sensitivity": subject.sensitivity,
        "actor_role": actor.role,
        "actor_user_id": actor.user_id,
        "emergency_override_active": override is not None,
        "reasons": reasons,
    }


@router.get("/{incident_id}/fairness-report")
def get_fairness_report(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """GET /api/incidents/{id}/fairness-report — equity report.

    Builds FairnessZone tuples from the incident's Zone rows, constructs
    original (unconstrained) and fair (constrained) plans, and returns
    the EquityReport from FairnessEngine.compute_equity_report().
    """
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    zones = db.execute(
        select(ZoneModel).where(
            ZoneModel.org_id == org_id, ZoneModel.incident_id == incident_id,
        )
    ).scalars().all()

    if not zones:
        return {
            "incident_id": incident_id,
            "status": "no_zones",
            "message": "No zones found for this incident. Seed zones to generate a fairness report.",
            "equity_report": None,
        }

    fairness_zones: list[FairnessZone] = []
    for z in zones:
        props = z.properties or {}
        fairness_zones.append(FairnessZone(
            id=z.id,
            vulnerable=bool(props.get("vulnerable", False)),
            c_min=int(props.get("c_min", 0)),
            smartphone_ownership=float(props.get("smartphone_ownership", 1.0)),
            network_coverage=float(props.get("network_coverage", 1.0)),
            social_media_usage=float(props.get("social_media_usage", 1.0)),
        ))

    fz_tuple = tuple(fairness_zones)

    # Build two plans: original (unconstrained) and fair (constrained).
    # The original plan allocates all coverage to the first zone (highest
    # throughput without fairness). The fair plan respects c_min for
    # vulnerable zones.
    original_coverage: dict[str, int] = {z.id: 0 for z in fz_tuple}
    fair_coverage: dict[str, int] = {z.id: 0 for z in fz_tuple}

    n_responders = max(sum(z.c_min for z in fz_tuple), len(fz_tuple))
    remaining = n_responders

    # Fair plan: satisfy c_min for vulnerable zones first, then distribute.
    for z in fz_tuple:
        if z.vulnerable and z.c_min > 0:
            alloc = min(z.c_min, remaining)
            fair_coverage[z.id] = alloc
            remaining -= alloc
    for z in fz_tuple:
        if remaining <= 0:
            break
        if fair_coverage[z.id] == 0:
            fair_coverage[z.id] = 1
            remaining -= 1

    # Original plan: all responders to the first zone (max throughput, no fairness).
    original_coverage[fz_tuple[0].id] = n_responders

    original_tp = sum(original_coverage.values())
    fair_tp = sum(fair_coverage.values())

    original_plan = Plan(
        coverage=original_coverage,
        response_delays={z.id: 0 for z in fz_tuple},
        throughput=original_tp,
    )
    fair_plan = Plan(
        coverage=fair_coverage,
        response_delays={z.id: 0 for z in fz_tuple},
        throughput=fair_tp,
    )

    engine = FairnessEngine()
    report = engine.compute_equity_report(original_plan, fair_plan, fz_tuple)

    return {
        "incident_id": incident_id,
        "equity_applied": report.equity_applied,
        "throughput_tradeoff_pct": report.throughput_tradeoff_pct,
        "vulnerable_zones_protected": list(report.vulnerable_zones_protected),
        "low_connectivity_zones_protected": list(report.low_connectivity_zones_protected),
        "disparity_seconds": report.disparity_seconds,
        "message": report.message,
        "zones": [
            {
                "id": z.id,
                "vulnerable": z.vulnerable,
                "c_min": z.c_min,
                "is_low_connectivity": z.is_low_connectivity,
                "original_coverage": original_coverage[z.id],
                "fair_coverage": fair_coverage[z.id],
            }
            for z in fz_tuple
        ],
    }


def round_coords_by_role(location: dict | list | None, role: str) -> dict | list | None:
    """Round coordinates based on viewer role (progressive precision).

    viewer → 2 decimals (~1km), field_responder → 3 decimals (~100m),
    admin → exact. Uses the COORD_DECIMALS concept from app.lib.privacy.
    """
    if location is None:
        return None
    decimals = _ROLE_COORD_DECIMALS.get(role, 2)  # default to ~1km
    if decimals is None:
        return location
    if isinstance(location, dict):
        out = dict(location)
        for key in ("lat", "lon", "latitude", "longitude"):
            if key in out and isinstance(out[key], (int, float)):
                out[key] = round(float(out[key]), decimals)
        return out
    if isinstance(location, (list, tuple)) and len(location) >= 2:
        return [round(float(location[0]), decimals), round(float(location[1]), decimals)]
    return location


def redact_pii(entity: dict, role: str) -> dict:
    """Apply ProgressivePrecision PII redaction based on viewer role."""
    serializer = ProgressivePrecision()
    return serializer.serialize(entity, viewer_role=role)


__all__ = ["router", "round_coords_by_role", "redact_pii"]
