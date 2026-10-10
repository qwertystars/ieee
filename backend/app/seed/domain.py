"""Domain seeder — creates the Incident plus alert, recommendation, and task.

The Incident is the top-level container (FK target for alerts and
recommendations). It must be created before any alert/recommendation/task.
All domain objects use deterministic IDs from ids.py and are scoped to the
demo org_id and incident_id.
"""

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.models.alert import Alert
from app.models.entities import OperationalTask
from app.models.incident import Incident
from app.models.recommendation import Recommendation
from app.seed.ids import (
    ALERT_ID,
    INCIDENT_ID,
    INCIDENT_NAME,
    ORG_ID,
    RECOMMENDATION_ID,
    TASK_ID,
    seed_id,
)

_BASE_TS = 1753000000000  # 2026-07-20T00:00:00Z — matches observations.py
_RESPONDER_1_ID = seed_id("responder:1")  # Aarav Sharma, team_lead


def seed_incident(db: Session) -> int:
    """Create the demo Incident (top-level container for FK targets)."""
    ts = now_ms()
    db.add(Incident(
        id=INCIDENT_ID,
        org_id=ORG_ID,
        title=INCIDENT_NAME,
        disaster_type="cyclone_flood",
        severity="major",
        status="active",
        declaration_level="state",
        description="Cyclone-induced urban flooding in Rivertown. "
                    "Wards 1-3 most affected. Bridge BR-04 status disputed.",
        geometry=WKTElement(
            "POLYGON((72.84 19.05, 72.94 19.05, 72.94 19.11, 72.84 19.11, 72.84 19.05))",
            srid=4326,
        ),
        start_time=_BASE_TS,
        expected_end=_BASE_TS + 72 * 3600 * 1000,  # 72h duration
        config={"demo": True, "region": "rivertown"},
        created_at=ts,
        updated_at=ts,
    ))
    db.commit()
    return 1


def seed_alert(db: Session) -> int:
    """Create 1 draft trapped-person alert in Ward 2."""
    ts = now_ms()
    db.add(Alert(
        id=ALERT_ID,
        org_id=ORG_ID,
        incident_id=INCIDENT_ID,
        alert_type="trapped_person",
        title="Trapped person reported in Ward-2-Riverside",
        message="Citizen report: family of 4 trapped on rooftop near "
                "Bridge BR-04. Water level rising. Rescue ball deployed.",
        area=WKTElement("POINT(72.872 19.070)", srid=4326),
        severity="critical",
        recommended_action="Dispatch boat rescue team immediately",
        confidence_vector={"s": 0.7, "c": 0.5},
        status="draft",
        created_by="seed_demo",
        created_at=ts,
        updated_at=ts,
    ))
    db.commit()
    return 1


def seed_recommendation(db: Session) -> int:
    """Create 1 draft rescue-operation recommendation linked to the alert."""
    ts = now_ms()
    db.add(Recommendation(
        id=RECOMMENDATION_ID,
        org_id=ORG_ID,
        incident_id=INCIDENT_ID,
        alert_id=ALERT_ID,
        recommendation_type="rescue_operation",
        title="Deploy boat rescue team to Ward-2-Riverside",
        description="Dispatch Boat-01 with team lead Aarav Sharma to "
                    "the reported rooftop location. Estimated 15 min ETA.",
        reasoning="Citizen report corroborated by rescue-ball sensor "
                  "deployment. Water level rising. Window of opportunity "
                  "estimated at 45 minutes before submersion.",
        supporting_evidence={
            "alert_id": ALERT_ID,
            "rescue_ball_device": "Rescue-Ball-01",
            "observation_id": seed_id("obs:citizen:5"),
        },
        contradicting_evidence=None,
        confidence_vector={"s": 0.7, "c": 0.5, "f": 0.6},
        urgency="high",
        status="draft",
        assigned_team_id=None,
        created_at=ts,
        updated_at=ts,
    ))
    db.commit()
    return 1


def seed_task(db: Session) -> int:
    """Create 1 assigned rescue task linked to the incident."""
    ts = now_ms()
    db.add(OperationalTask(
        id=TASK_ID,
        org_id=ORG_ID,
        incident_id=INCIDENT_ID,
        title="Rescue trapped person",
        status="assigned",
        priority="high",
        assigned_team_id=_RESPONDER_1_ID,
        required_capability="boat_rescue",
        assignment_history={
            "log": [
                {"team": _RESPONDER_1_ID, "at": ts, "reason": "initial assignment"},
            ],
        },
        geometry=WKTElement("POINT(72.872 19.070)", srid=4326),
        properties={"alert_id": ALERT_ID, "eta_minutes": 15},
        created_at=ts,
        updated_at=ts,
    ))
    db.commit()
    return 1
