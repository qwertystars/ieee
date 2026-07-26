"""Alert evaluation rules — generate draft alerts from observations.

Evaluates thermal/human-detection observations against confidence thresholds
and creates draft alerts. The system NEVER auto-dispatches — all alerts
require explicit human approval before any action is taken.

Configurable thresholds (defaults shown):
    S >= 0.5  (source reliability — confidence_vector.s)
    C >= 0.2  (corroboration strength — confidence_vector.c)

The 6D confidence vector is stored in ``observation.quality_flags["confidence_vector"]``
as ``{"s": ..., "c": ..., "f": ..., "g": ..., "m": ..., "k": ...}``.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.alert import Alert
from app.models.observation import Observation

logger = logging.getLogger("app.alerts.rules")

# ── Configurable thresholds ─────────────────────────────────────────────────
# A draft alert is created when an observation's confidence vector meets BOTH.
_THRESHOLD_S = 0.5  # source reliability
_THRESHOLD_C = 0.2  # corroboration strength

# Phenomena that trigger alert evaluation.
_ALERT_PHENOMENA: tuple[str, ...] = ("thermal_detection", "human_detection")

# Lookback window for recent observations (24 hours in ms).
_LOOKBACK_MS = 24 * 60 * 60 * 1000


def _get_confidence_vector(obs: Observation) -> dict[str, Any] | None:
    """Extract the 6D confidence vector from observation.quality_flags."""
    qf = obs.quality_flags or {}
    cv = qf.get("confidence_vector")
    return cv if isinstance(cv, dict) else None


def _meets_threshold(cv: dict[str, Any]) -> bool:
    """Check if S >= _THRESHOLD_S AND C >= _THRESHOLD_C."""
    s = cv.get("s")
    c = cv.get("c")
    if s is None or c is None:
        return False
    return float(s) >= _THRESHOLD_S and float(c) >= _THRESHOLD_C


def _existing_draft_alert(
    db: Session, org_id: str, incident_id: str, observation_id: str
) -> Alert | None:
    """Check if a draft alert already exists for this observation.

    The source observation_id is stored in
    ``alert.confidence_vector["source_observation_id"]`` for idempotency tracking.
    """
    stmt = select(Alert).where(
        Alert.org_id == org_id,
        Alert.incident_id == incident_id,
        Alert.status == "draft",
        Alert.confidence_vector["source_observation_id"].astext == observation_id,
    )
    return db.execute(stmt).scalars().first()


def _build_alert(
    obs: Observation, org_id: str, incident_id: str, cv: dict[str, Any]
) -> Alert:
    """Construct a draft Alert from a threshold-meeting observation."""
    ts = now_ms()
    return Alert(
        id=generate_ulid(),
        org_id=org_id,
        incident_id=incident_id,
        alert_type="trapped_person",
        title=f"Possible trapped person detected ({obs.phenomenon})",
        message=(
            f"Observation {obs.observation_id} from source {obs.source_id} "
            f"indicates potential human presence. "
            f"Confidence: S={cv.get('s')}, C={cv.get('c')}. "
            f"Manual review required before any action."
        ),
        severity="urgent",
        recommended_action=(
            "Dispatch field team to verify and assist. "
            "Await human approval before deployment."
        ),
        confidence_vector={
            "s": cv.get("s"),
            "c": cv.get("c"),
            "f": cv.get("f"),
            "g": cv.get("g"),
            "m": cv.get("m"),
            "k": cv.get("k"),
            "source_observation_id": obs.observation_id,
        },
        status="draft",
        created_by="system",
        created_at=ts,
        updated_at=ts,
    )


def evaluate_alerts(db: Session, incident_id: str) -> list[Alert]:
    """Evaluate recent observations and create draft alerts for threshold-meeting ones.

    Idempotent: does not create duplicate draft alerts for the same observation.
    The system NEVER auto-dispatches — all alerts require human approval.

    Returns the list of newly created alerts.
    """
    # org_id is consistent within an incident (enforced by OrgContextMiddleware).
    org_id_row = db.execute(
        select(Observation.org_id)
        .where(Observation.incident_id == incident_id)
        .limit(1)
    ).first()
    if org_id_row is None:
        return []
    org_id = org_id_row[0]

    cutoff = now_ms() - _LOOKBACK_MS
    stmt = (
        select(Observation)
        .where(
            Observation.incident_id == incident_id,
            Observation.org_id == org_id,
            Observation.phenomenon.in_(_ALERT_PHENOMENA),
            Observation.observed_at >= cutoff,
        )
        .order_by(Observation.observed_at.desc())
    )
    observations = db.execute(stmt).scalars().all()

    created: list[Alert] = []
    for obs in observations:
        cv = _get_confidence_vector(obs)
        if cv is None or not _meets_threshold(cv):
            continue
        if _existing_draft_alert(db, org_id, incident_id, obs.observation_id) is not None:
            continue
        alert = _build_alert(obs, org_id, incident_id, cv)
        db.add(alert)
        created.append(alert)

    if created:
        db.commit()
        for a in created:
            db.refresh(a)
        logger.info(
            "alert.evaluate: created %d draft alerts for incident %s",
            len(created),
            incident_id,
        )

    return created


__all__ = ["evaluate_alerts"]
