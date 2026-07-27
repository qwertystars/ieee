"""Hypothesis seeder — creates 5 hypotheses, including 2 contradictory.

The contradictory pair is about Bridge BR-04 passability:
  H1: "Bridge BR-04 is passable for emergency vehicles" (P=0.7, satellite)
  H2: "Bridge BR-04 is impassable due to flooding" (P=0.6, citizen reports)

Both are preserved with status=active — the system does NOT silently choose one.
Resolution is deferred to the human decision-maker.
"""

from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.models.enums import HypothesisStatus
from app.models.hypotheses import Hypothesis
from app.seed.ids import INCIDENT_ID, ORG_ID, seed_id

# Entity IDs referenced by hypotheses (must match entities.py seed IDs).
_BRIDGE_04_ID = seed_id("road:road_4")  # Bridge Road (road_4 in fixtures)
_COASTAL_HWY_ID = seed_id("road:road_1")  # Coastal Highway
_HOSPITAL_01_ID = seed_id("hospital:hospital_1")
_SUBSTATION_02_ID = seed_id("substation:substation_2")


def seed_hypotheses(db: Session) -> int:
    """Create 5 hypotheses (2 contradictory about Bridge BR-04)."""
    ts = now_ms()
    hyps = [
        # H1: Bridge BR-04 passable (contradicts H2)
        Hypothesis(
            id=seed_id("hyp:bridge_passable"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            entity_type="road_segment", entity_id=_BRIDGE_04_ID,
            claim="Bridge BR-04 is passable for emergency vehicles",
            probability=0.7,
            supporting_evidence={
                "source": "satellite",
                "observation_id": seed_id("obs:stac:sentinel1_flood_001"),
                "note": "Satellite imagery shows bridge surface above water",
            },
            contradicting_evidence={
                "source": "citizen_report",
                "note": "Unverified report of flooding at bridge",
            },
            status=HypothesisStatus.active,
            created_at=ts, updated_at=ts,
        ),
        # H2: Bridge BR-04 impassable (contradicts H1)
        Hypothesis(
            id=seed_id("hyp:bridge_impassable"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            entity_type="road_segment", entity_id=_BRIDGE_04_ID,
            claim="Bridge BR-04 is impassable due to flooding",
            probability=0.6,
            supporting_evidence={
                "source": "citizen_report",
                "observation_id": seed_id("obs:citizen:2"),
                "note": "Multiple reports of water over bridge deck",
            },
            contradicting_evidence={
                "source": "satellite",
                "note": "Satellite imagery shows surface above water",
            },
            status=HypothesisStatus.active,
            created_at=ts, updated_at=ts,
        ),
        # H3: Coastal Highway passable
        Hypothesis(
            id=seed_id("hyp:coastal_passable"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            entity_type="road_segment", entity_id=_COASTAL_HWY_ID,
            claim="Coastal Highway is passable for all vehicles",
            probability=0.8,
            supporting_evidence={
                "source": "official_feed",
                "observation_id": seed_id("obs:official:1"),
                "note": "Official patrol reports road clear",
            },
            contradicting_evidence=None,
            status=HypothesisStatus.active,
            created_at=ts, updated_at=ts,
        ),
        # H4: Hospital has capacity
        Hypothesis(
            id=seed_id("hyp:hospital_capacity"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            entity_type="hospital", entity_id=_HOSPITAL_01_ID,
            claim="Rivertown General Hospital has capacity for 20 more patients",
            probability=0.9,
            supporting_evidence={
                "source": "official_feed",
                "observation_id": seed_id("obs:official:10"),
                "note": "180/200 beds occupied, 20 available",
            },
            contradicting_evidence=None,
            status=HypothesisStatus.active,
            created_at=ts, updated_at=ts,
        ),
        # H5: Substation SS-02 restoration unlikely soon
        Hypothesis(
            id=seed_id("hyp:substation_restoration"),
            org_id=ORG_ID, incident_id=INCIDENT_ID,
            entity_type="power_substation", entity_id=_SUBSTATION_02_ID,
            claim="Substation SS-02 will NOT be restored within 4 hours",
            probability=0.3,
            supporting_evidence={
                "source": "official_feed",
                "observation_id": seed_id("obs:official:4"),
                "note": "Substation flooded, transformer damage suspected",
            },
            contradicting_evidence={
                "source": "model",
                "note": "Flood water receding model predicts 3h to drain",
            },
            status=HypothesisStatus.active,
            created_at=ts, updated_at=ts,
        ),
    ]
    for h in hyps:
        db.add(h)
    db.commit()
    return len(hyps)
