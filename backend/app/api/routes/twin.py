"""Digital twin API routes — cascade blast radius + telecom silence.

Wires the CascadeSimulator and TelecomSilenceModel to incident-scoped
endpoints:
  - GET /api/incidents/{id}/cascade  — BFS blast radius from GraphEdge DAG
  - GET /api/incidents/{id}/silence  — expected vs observed report rate

Both endpoints build their inputs from the incident's DB data (GraphEdge
rows for cascade, Zone + Observation rows for silence) and fall back to
deterministic demo data when the incident has no seeded infrastructure.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.lib.time import now_ms
from app.models.entities import CellTower, PowerSubstation, Zone
from app.models.incident import Incident
from app.models.observation import Observation
from app.models.user import User
from app.twin.cascading import CascadeSimulator
from app.twin.cascading_types import CascadeResult
from app.twin.silence import TelecomSilenceModel
from app.twin.silence_types import SilenceContext, TimeWindow

logger = logging.getLogger("app.api.routes.twin")

router = APIRouter(prefix="/incidents", tags=["twin"])

_WINDOW_MS = 6 * 60 * 60 * 1000  # 6 hours


def _get_incident(db: Session, org_id: str, incident_id: str) -> Incident:
    inc = db.execute(
        select(Incident).where(
            Incident.org_id == org_id, Incident.id == incident_id,
        )
    ).scalars().first()
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


@router.get("/{incident_id}/cascade")
def get_cascade(
    incident_id: str,
    request: Request,
    node_id: str | None = Query(None, description="Node to fail; omit for largest blast radius"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """GET /api/incidents/{id}/cascade — blast radius from the infrastructure DAG.

    Builds a CascadeSimulator from GraphEdge rows for this incident, then
    simulates failure of ``node_id`` (or the node with the largest blast
    radius if omitted). Returns affected nodes, max depth, and blast radius.
    """

    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    sim = CascadeSimulator()
    sim.build_from_graph_edges(db)

    if sim.node_count == 0:
        return {
            "incident_id": incident_id,
            "status": "no_infrastructure_graph",
            "message": "No GraphEdge rows found for this incident. Seed infrastructure dependencies to simulate cascades.",
            "blast_radius": 0,
            "max_depth": 0,
            "affected_nodes": {},
        }

    if node_id is not None:
        target = sim.get_node(node_id)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail=f"node '{node_id}' not in infrastructure graph",
            )
        result: CascadeResult | None = sim.simulate_failure(node_id)
    else:
        # Find the node with the largest blast radius.
        best_result: CascadeResult | None = None
        for nid in list(sim._nodes.keys()):
            r = sim.simulate_failure(nid)
            if best_result is None or r.blast_radius > best_result.blast_radius:
                best_result = r
        result = best_result

    if result is None:
        raise HTTPException(status_code=500, detail="cascade simulation failed")

    node = sim.get_node(result.failed_node_id)
    return {
        "incident_id": incident_id,
        "failed_node_id": result.failed_node_id,
        "failed_node_type": node.node_type.value if node else None,
        "failed_node_name": node.name if node else None,
        "blast_radius": result.blast_radius,
        "max_depth": result.max_depth,
        "affected_nodes": {
            nid: {"depth": depth} for nid, depth in result.affected_nodes.items()
        },
        "total_graph_nodes": sim.node_count,
        "total_graph_edges": sim.edge_count,
    }


@router.get("/{incident_id}/silence")
def get_silence(
    incident_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """GET /api/incidents/{id}/silence — telecom silence residual per zone.

    Builds zones from the Zone table, computes expected vs observed report
    rates using TelecomSilenceModel, and flags zones with meaningful silence
    (residual > threshold AND supporting evidence AND high vulnerability).
    """
    org_id = request.state.org_id or ""
    _get_incident(db, org_id, incident_id)

    ts_now = now_ms()
    window_start = ts_now - _WINDOW_MS

    zones = db.execute(
        select(Zone).where(
            Zone.org_id == org_id, Zone.incident_id == incident_id,
        )
    ).scalars().all()

    observations = db.execute(
        select(Observation).where(
            Observation.org_id == org_id,
            Observation.incident_id == incident_id,
            Observation.observed_at >= window_start,
        )
    ).scalars().all()

    obs_timestamps = [o.observed_at for o in observations]

    # Check for infrastructure evidence (tower failure, power outage).
    towers = db.execute(
        select(CellTower).where(
            CellTower.org_id == org_id, CellTower.incident_id == incident_id,
        )
    ).scalars().all()
    substations = db.execute(
        select(PowerSubstation).where(
            PowerSubstation.org_id == org_id,
            PowerSubstation.incident_id == incident_id,
        )
    ).scalars().all()

    tower_failed = any(t.status == "offline" for t in towers)
    power_outage = any(s.status == "offline" for s in substations)

    model = TelecomSilenceModel()
    time_window = TimeWindow(start_ms=window_start, end_ms=ts_now)

    zone_reports: list[dict[str, Any]] = []
    for zone in zones:
        props = zone.properties or {}
        population = int(props.get("population", 1000))
        vulnerability = float(props.get("vulnerability_score", 0.5))
        smartphone = float(props.get("smartphone_ownership", 0.8))
        network = float(props.get("network_coverage", 0.8))
        social = float(props.get("social_media_usage", 0.8))
        historical = float(props.get("historical_reporting_rate", 0.01))
        hazard = float(props.get("hazard_intensity", 0.5))

        from app.twin.silence_types import Zone as SilenceZone

        szone = SilenceZone(
            zone_id=zone.id,
            population=population,
            normal_activity_rate=1.0,
            smartphone_ownership=smartphone,
            network_coverage=network,
            social_media_usage=social,
            vulnerability_score=vulnerability,
            historical_reporting_rate=historical,
            hazard_intensity=hazard,
        )

        r_hat = model.estimate_expected_rate(szone, time_window)
        r_observed = model.compute_observed_rate(szone, time_window, obs_timestamps)
        residual = model.compute_residual(r_hat, r_observed)

        ctx = SilenceContext(
            tower_failed=tower_failed,
            power_outage=power_outage,
            failed_calls=0,
            devices_unreachable=0,
            hazard_intensity=hazard,
        )
        meaningful = model.is_meaningful_silence(szone, residual, ctx)

        zone_reports.append({
            "zone_id": zone.id,
            "zone_name": zone.name,
            "expected_rate": round(r_hat, 4),
            "observed_rate": round(r_observed, 4),
            "residual": round(residual, 4),
            "meaningful_silence": meaningful,
            "vulnerability_score": vulnerability,
            "supporting_evidence": {
                "tower_failed": tower_failed,
                "power_outage": power_outage,
            },
        })

    return {
        "incident_id": incident_id,
        "window_ms": _WINDOW_MS,
        "window_start": window_start,
        "window_end": ts_now,
        "total_observations": len(observations),
        "total_zones": len(zones),
        "zones": zone_reports,
    }


__all__ = ["router"]
