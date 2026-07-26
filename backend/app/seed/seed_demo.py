"""Main seed script — populates DB with the Rivertown cyclone-flood scenario.

Run:  python -m app.seed.seed_demo

Creates: 1 incident, 5 zones, 20 roads, 3 shelters, 2 hospitals, 10 buildings,
3 substations, 5 cell towers, 5 responders, 3 vehicles, 2 rescue-ball devices,
50 observations, 5 hypotheses (2 contradictory), 3 scenarios (best/expected/worst),
1 draft trapped-person alert, 1 draft rescue recommendation, 1 assigned task.

Idempotent: running twice produces the same row counts. Uses deterministic IDs
(SHA-256 of stable keys) and delete-then-insert per org+incident scope.
All fixtures are local files — no internet required.
"""

import sys

from app.db import SessionLocal
from app.seed.db_setup import clean_demo_data
from app.seed.domain import (
    seed_alert,
    seed_incident,
    seed_recommendation,
    seed_task,
)
from app.seed.entities import (
    seed_buildings,
    seed_hospitals,
    seed_infrastructure,
    seed_rescue_ball_devices,
    seed_responders,
    seed_vehicles,
    seed_roads,
    seed_shelters,
    seed_zones,
)
from app.seed.hypotheses import seed_hypotheses
from app.seed.ids import INCIDENT_ID, INCIDENT_NAME, ORG_ID
from app.seed.observations import seed_observations
from app.seed.scenarios import seed_scenarios


def seed_demo() -> dict[str, int]:
    """Execute the full seed. Returns a dict of {entity: count}.

    Safe to call multiple times — deletes existing demo data before inserting.
    """
    db = SessionLocal()
    try:
        clean_demo_data(db)
        counts: dict[str, int] = {}
        counts["incident"] = seed_incident(db)
        counts["zones"] = seed_zones(db)
        counts["roads"] = seed_roads(db)
        counts["shelters"] = seed_shelters(db)
        counts["hospitals"] = seed_hospitals(db)
        counts["buildings"] = seed_buildings(db)
        subs, towers = seed_infrastructure(db)
        counts["substations"] = subs
        counts["cell_towers"] = towers
        counts["responders"] = seed_responders(db)
        counts["vehicles"] = seed_vehicles(db)
        counts["rescue_ball_devices"] = seed_rescue_ball_devices(db)
        counts["observations"] = seed_observations(db)
        counts["hypotheses"] = seed_hypotheses(db)
        counts["scenarios"] = seed_scenarios(db)
        counts["alerts"] = seed_alert(db)
        counts["recommendations"] = seed_recommendation(db)
        counts["tasks"] = seed_task(db)
        return counts
    finally:
        db.close()


def main() -> None:
    """CLI entry point — run seed and print summary."""
    print(f"Seeding demo scenario: {INCIDENT_NAME}")
    print(f"  org_id={ORG_ID}  incident_id={INCIDENT_ID}")
    counts = seed_demo()
    print("Seed complete:")
    for entity, count in counts.items():
        print(f"  {entity:20s} {count:>4d}")
    total = sum(counts.values())
    print(f"  {'TOTAL':20s} {total:>4d}")
    print("Idempotent: re-run produces the same counts.")


if __name__ == "__main__":
    sys.exit(main())
