"""Post-commit fusion for batched observations — confidence, hypothesis, audit.

Runs synchronously in a thread (via ``asyncio.to_thread``) after the batch
INSERT commits. Opens its own ``SessionLocal`` since the batch session is
closed by the time this runs. Failures are logged and swallowed — the
observations are already committed; fusion is best-effort enrichment.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm.attributes import flag_modified

from app.db import SessionLocal
from app.fusion.confidence import ConfidenceVectorCalculator
from app.fusion.hypothesis_update import update_hypotheses_for_observation
from app.lib.audit import write_audit
from app.models.observation import Observation

logger = logging.getLogger("app.streaming.post_commit")


def run_post_commit_fusion(
    observation_ids: list[str], payloads: list[dict]
) -> None:
    """Compute confidence vectors, update hypotheses, write audit entries.

    Called via ``asyncio.to_thread`` so it does not block the consumer's
    event loop. Each observation is enriched independently — a failure on
    one does not prevent enrichment of the others.
    """
    db = SessionLocal()
    try:
        calc = ConfidenceVectorCalculator()
        for obs_id, payload in zip(observation_ids, payloads):
            obs = db.get(Observation, obs_id)
            if obs is None:
                continue
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
                    "Confidence computation failed for %s: %s", obs_id, exc
                )
                db.rollback()
                continue
            try:
                update_hypotheses_for_observation(db, obs)
            except Exception as exc:
                logger.warning(
                    "Hypothesis update failed for %s: %s", obs_id, exc
                )
                db.rollback()
            write_audit(
                db,
                org_id=payload.get("org_id", ""),
                incident_id=payload.get("incident_id", ""),
                actor="streaming-consumer",
                action="observation.ingested",
                entity=obs_id,
                after={
                    "source_type": payload.get("source_type"),
                    "observed_at": payload.get("observed_at"),
                },
            )
    except Exception as exc:
        logger.error("Post-commit fusion failed: %s", exc)
    finally:
        db.close()


__all__ = ["run_post_commit_fusion"]
