"""Update active hypotheses when new observations arrive.

After an observation is inserted and its confidence vector is computed,
this module checks if the observation corroborates or contradicts any
active hypothesis for the same incident. Evidence arrays and probability
are updated in-place. Contradictory hypotheses are preserved — never deleted.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.lib.time import now_ms
from app.models.enums import HypothesisStatus
from app.models.hypotheses import Hypothesis
from app.models.observation import Observation

logger = logging.getLogger(__name__)

# Probability adjustment per evidence item (clamped to [0, 1]).
_PROB_DELTA = 0.1


def _corroborates(claim: str, value: float | None) -> bool | None:
    """Heuristic: does the observation value support the claim?

    Returns True (corroborates), False (contradicts), or None (undetermined).
    """
    if value is None:
        return None
    claim_lower = claim.lower()
    if "impassable" in claim_lower:
        return value < 0.5
    if "passable" in claim_lower:
        return value >= 0.5
    return None


def update_hypotheses_for_observation(
    db: Session, obs: Observation
) -> int:
    """Update active hypotheses with evidence from a new observation.

    Matches by entity_type == observation.phenomenon. Appends to
    supporting_evidence or contradicting_evidence arrays and adjusts
    probability by +/- _PROB_DELTA (clamped to [0, 1]). Returns the
    number of hypotheses updated. Contradictory hypotheses are preserved.
    """
    stmt = select(Hypothesis).where(
        Hypothesis.org_id == obs.org_id,
        Hypothesis.incident_id == obs.incident_id,
        Hypothesis.entity_type == obs.phenomenon,
        Hypothesis.status == HypothesisStatus.active,
    )
    hypotheses = list(db.execute(stmt).scalars().all())
    if not hypotheses:
        return 0

    evidence_entry = {
        "observation_id": obs.observation_id,
        "value": obs.value,
        "observed_at": obs.observed_at,
        "source_type": obs.source_type.value if obs.source_type else None,
    }

    updated = 0
    for h in hypotheses:
        result = _corroborates(h.claim, obs.value)
        if result is None:
            continue
        if result:
            ev = dict(h.supporting_evidence or {})
            obs_list = ev.get("observations", [])
            obs_list.append(evidence_entry)
            ev["observations"] = obs_list
            h.supporting_evidence = ev
            h.probability = min(1.0, h.probability + _PROB_DELTA)
        else:
            ev = dict(h.contradicting_evidence or {})
            obs_list = ev.get("observations", [])
            obs_list.append(evidence_entry)
            ev["observations"] = obs_list
            h.contradicting_evidence = ev
            h.probability = max(0.0, h.probability - _PROB_DELTA)
        h.updated_at = now_ms()
        flag_modified(h, "supporting_evidence")
        flag_modified(h, "contradicting_evidence")
        updated += 1

    if updated > 0:
        db.commit()
    return updated


__all__ = ["update_hypotheses_for_observation"]
