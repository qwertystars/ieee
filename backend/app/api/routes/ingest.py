"""Social media ingestion API — trigger async ingestion per incident.

POST /api/incidents/{id}/ingest/social-media?source_type=twitter
Returns 202 (Accepted) immediately; ingestion runs in the background via
FastAPI BackgroundTasks. Each adapter degrades gracefully when credentials
are missing (returns 0 observations) and when Kafka is unavailable (noop
producer logs sends instead of crashing).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.deps import get_db, require_roles
from app.ingestion.adapters.instagram import InstagramAdapter
from app.ingestion.adapters.reddit import RedditAdapter
from app.ingestion.adapters.twitter import TwitterAdapter
from app.ingestion.adapters.youtube import YouTubeAdapter
from app.models.user import User

logger = logging.getLogger("app.api.routes.ingest")

router = APIRouter(prefix="/incidents", tags=["ingest"])

_WRITE_ROLES = ("admin", "emergency_manager", "responder_coordinator")

_ADAPTERS: dict[str, type] = {
    "twitter": TwitterAdapter,
    "reddit": RedditAdapter,
    "instagram": InstagramAdapter,
    "youtube": YouTubeAdapter,
}


class _NoopProducer:
    """No-op producer used when Kafka/Redpanda is unavailable.

    Allows adapter.sync() to complete (pull + map + dedup) even when the
    broker is down. Observations are not published but idempotency keys
    are recorded so re-runs skip already-processed items.
    """

    async def send(
        self, topic: str, message: dict, key: str | None = None,
    ) -> None:
        logger.debug("noop producer: would send to %s", topic)

    async def stop(self) -> None:
        pass


async def _start_producer() -> Any:
    """Start ProducerManager; fall back to _NoopProducer on failure."""
    try:
        import asyncio

        from app.streaming.producer import ProducerManager

        producer = ProducerManager()
        await asyncio.wait_for(producer.start(), timeout=5.0)
        return producer
    except Exception as exc:
        logger.warning("Kafka unavailable, using noop producer: %s", exc)
        return _NoopProducer()


async def _run_ingestion(
    adapter_cls: type,
    config: dict[str, Any],
    org_id: str,
    incident_id: str,
) -> None:
    """Background task: pull observations, dedup, publish to Kafka."""
    db = SessionLocal()
    try:
        producer = await _start_producer()
        adapter = adapter_cls(config)
        try:
            count = await adapter.sync(db, producer, org_id, incident_id)
            logger.info(
                "Ingested %d observations for incident %s via %s",
                count, incident_id, adapter_cls.__name__,
            )
        finally:
            await adapter.close()
            await producer.stop()
    except Exception as exc:
        logger.error(
            "Social media ingestion failed for %s: %s", incident_id, exc,
        )
    finally:
        db.close()


@router.post(
    "/{incident_id}/ingest/social-media",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_social_media_ingestion(
    incident_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    source_type: str = Query(
        ..., description="twitter|reddit|instagram|youtube",
    ),
    config: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> dict[str, Any]:
    """Trigger async social media ingestion for an incident.

    Returns 202 (Accepted) immediately. The adapter's ``pull_observations()``
    runs in the background via ``sync()``. Degrades gracefully when
    credentials are missing (adapter returns 0) or Kafka is down (noop
    producer).
    """
    org_id = request.state.org_id or ""
    source = source_type.lower()
    if source not in _ADAPTERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source_type must be one of {list(_ADAPTERS)}",
        )

    adapter_cls = _ADAPTERS[source]
    background_tasks.add_task(
        _run_ingestion, adapter_cls, config or {}, org_id, incident_id,
    )

    return {
        "status": "accepted",
        "incident_id": incident_id,
        "source_type": source,
        "message": "Ingestion triggered. Observations land as access_policy=sensitive.",
    }


__all__ = ["router"]
