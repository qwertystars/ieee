"""Build OptimizerInput from incident DB data or a demo fallback.

Used by the GET /api/incidents/{id}/optimize endpoint. Queries the
incident's responders, tasks, zones, and shelters from the DB and maps
them to optimizer types. Falls back to a deterministic demo scenario
when the incident has no seeded optimizer data.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    OperationalTask,
    Responder as ResponderModel,
    Shelter as ShelterModel,
    Zone as ZoneModel,
)
from app.optimizer.optimizer_types import (
    OptimizerInput,
    Responder,
    RoadArc,
    ScenarioLoss,
    Shelter,
    Task,
    Zone,
)

_ROLE_TO_SKILLS: dict[str, frozenset[str]] = {
    "team_lead": frozenset({"medical", "search", "evacuation"}),
    "medic": frozenset({"medical"}),
    "engineer": frozenset({"search"}),
    "rescuer": frozenset({"evacuation", "search"}),
    "driver": frozenset({"evacuation"}),
}

_DEFAULT_SCENARIOS = (
    ScenarioLoss(probability=0.3, harm_multiplier=1.0),
    ScenarioLoss(probability=0.4, harm_multiplier=1.5),
    ScenarioLoss(probability=0.3, harm_multiplier=0.8),
)


def build_input_from_db(
    db: Session, org_id: str, incident_id: str,
) -> OptimizerInput | None:
    """Build OptimizerInput from incident DB data. Returns None if insufficient."""
    responders_db = db.execute(
        select(ResponderModel).where(
            ResponderModel.org_id == org_id, ResponderModel.incident_id == incident_id,
        )
    ).scalars().all()
    tasks_db = db.execute(
        select(OperationalTask).where(
            OperationalTask.org_id == org_id, OperationalTask.incident_id == incident_id,
        )
    ).scalars().all()
    zones_db = db.execute(
        select(ZoneModel).where(
            ZoneModel.org_id == org_id, ZoneModel.incident_id == incident_id,
        )
    ).scalars().all()
    shelters_db = db.execute(
        select(ShelterModel).where(
            ShelterModel.org_id == org_id, ShelterModel.incident_id == incident_id,
        )
    ).scalars().all()

    if not responders_db or not tasks_db or not zones_db:
        return None

    zones = tuple(
        Zone(
            id=z.id,
            demand=int((z.properties or {}).get("demand", 1)),
            vulnerable=bool((z.properties or {}).get("vulnerable", False)),
            c_min=int((z.properties or {}).get("c_min", 0)),
        )
        for z in zones_db
    )
    responders = tuple(
        Responder(
            id=r.id,
            skills=frozenset((r.properties or {}).get("skills", list(
                _ROLE_TO_SKILLS.get(r.role or "", frozenset({"search"}))
            ))),
            vehicle_class=(r.properties or {}).get("vehicle_class", "ambulance"),
        )
        for r in responders_db
    )
    tasks = tuple(
        Task(
            id=t.id,
            zone_id=(t.properties or {}).get("zone_id", zones[0].id),
            required_skill=t.required_capability or "search",
            harm_if_unserved=float((t.properties or {}).get("harm_if_unserved", 100.0)),
        )
        for t in tasks_db
    )
    shelters = tuple(
        Shelter(id=s.id, capacity=s.capacity or 100, initial_occupancy=s.occupancy or 0)
        for s in shelters_db
    ) if shelters_db else ()

    return OptimizerInput(
        zones=zones, responders=responders, tasks=tasks, scenarios=_DEFAULT_SCENARIOS,
        road_arcs=(), shelters=shelters,
        alpha=0.95, lambda_risk=1.0, max_solve_seconds=10.0,
    )


def demo_input() -> OptimizerInput:
    """Deterministic demo scenario for incidents without seeded optimizer data."""
    zones = (
        Zone(id="z0", demand=1, vulnerable=True, c_min=1),
        Zone(id="z1", demand=1, vulnerable=False),
        Zone(id="z2", demand=1, vulnerable=False),
    )
    responders = (
        Responder(id="r0", skills=frozenset({"medical", "search"}), vehicle_class="ambulance"),
        Responder(id="r1", skills=frozenset({"medical"}), vehicle_class="ambulance"),
        Responder(id="r2", skills=frozenset({"search", "evacuation"}), vehicle_class="boat"),
        Responder(id="r3", skills=frozenset({"evacuation"}), vehicle_class="high_clearance"),
    )
    tasks = (
        Task(id="t0", zone_id="z0", required_skill="medical", harm_if_unserved=100.0),
        Task(id="t1", zone_id="z1", required_skill="search", harm_if_unserved=50.0),
        Task(id="t2", zone_id="z2", required_skill="evacuation", harm_if_unserved=75.0),
    )
    roads = (
        RoadArc(from_node=0, to_node=1, vehicle_classes=frozenset({"ambulance", "boat", "high_clearance"})),
        RoadArc(from_node=0, to_node=2, vehicle_classes=frozenset({"ambulance", "boat", "high_clearance"})),
        RoadArc(from_node=0, to_node=3, vehicle_classes=frozenset({"boat"})),
    )
    shelters = (Shelter(id="z2", capacity=10, initial_occupancy=0),)
    return OptimizerInput(
        zones=zones, responders=responders, tasks=tasks, scenarios=_DEFAULT_SCENARIOS,
        road_arcs=roads, shelters=shelters,
        alpha=0.95, lambda_risk=1.0, max_solve_seconds=10.0,
    )


__all__ = ["build_input_from_db", "demo_input"]
