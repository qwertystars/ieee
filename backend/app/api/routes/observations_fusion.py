"""Post-commit fusion helper for the single-observation POST route.

Moved to a separate module so ``observations.py`` stays under the 250 LOC
ceiling. Follows the same pattern as ``observations_batch.py``'s
``_run_post_commit_fusion``: opens its own session, computes confidence,
updates hypotheses, writes audit. Failures are logged and swallowed.
"""

from __future__ import annotations

import logging

from app.db import SessionLocal
from app.models.observation import Observation

logger = logging.getLogger("app.api.routes.observations_fusion")


def run_single_post_commit_fusion(
    observation_id: str, org_id: str, incident_id: str, actor: str
) -> None:
    """Background task: compute confidence, update hypotheses, write audit.

    Opens its own session (the request session is closed by the time
    ``BackgroundTasks`` runs). The observation is already committed; this
    is best-effort enrichment.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from app.fusion.confidence import ConfidenceVectorCalculator
    from app.fusion.hypothesis_update import update_hypotheses_for_observation
    from app.lib.audit import write_audit

    db = SessionLocal()
    try:
        obs = db.get(Observation, observation_id)
        if obs is None:
            return
        calc = ConfidenceVectorCalculator()
        try:
            vector = calc.compute_vector(obs, db_session=db)
            calc.attach_to_observation(obs, vector)
            obs.quality_flags["display_confidence"] = (
                calc.compute_display_confidence(vector)
            )
            flag_modified(obs, "quality_flags")
            db.commit()
        except Exception as exc:
            logger.warning(
                "Confidence computation failed for %s: %s", observation_id, exc
            )
            db.rollback()
        try:
            update_hypotheses_for_observation(db, obs)
        except Exception as exc:
            logger.warning(
                "Hypothesis update failed for %s: %s", observation_id, exc
            )
            db.rollback()
        write_audit(
            db,
            org_id=org_id,
            incident_id=incident_id,
            actor=actor,
            action="observation.created",
            entity=observation_id,
            after={
                "event_type": obs.event_type,
                "phenomenon": obs.phenomenon,
                "observed_at": obs.observed_at,
            },
        )
    except Exception as exc:
        logger.error("Post-commit fusion failed for %s: %s", observation_id, exc)
    finally:
        db.close()


__all__ = ["run_single_post_commit_fusion"]
