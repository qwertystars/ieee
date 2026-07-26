"""DB setup helpers — clean demo data.

Migration 0002a added the entity columns that were previously missing from
migration 0001. This module now only contains the clean_demo_data helper
for idempotent re-seeding.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.seed.ids import INCIDENT_ID, ORG_ID

# Tables with org_id+incident_id columns to clear for demo data, FK-safe order.
# graph_edges has no org_id column — skip it (seed doesn't create edges).
_DEMO_TABLES = [
    "observations",
    "hypotheses",
    "scenarios",
    "events",
    "decisions",
    "operational_tasks",
    "sensors",
    "vehicles",
    "responders",
    "shelters",
    "hospitals",
    "cell_towers",
    "power_substations",
    "buildings",
    "road_segments",
    "zones",
    "hazards",
]


def clean_demo_data(db: Session) -> None:
    """Delete all demo rows for the demo org+incident (idempotency)."""
    for table in _DEMO_TABLES:
        db.execute(
            text(
                f"DELETE FROM {table} "
                f"WHERE org_id = :oid AND incident_id = :iid"
            ),
            {"oid": ORG_ID, "iid": INCIDENT_ID},
        )
    db.commit()
