"""Social media ingestion API with durable publish acknowledgement.

POST /api/incidents/{id}/ingest/social-media?source_type=twitter returns 202
only after the ingestion event has been durably published. Unavailable
streaming infrastructure returns 503 without acknowledging the request.
"""

from __future__ import annotations

import logging
from typing import Any

import anyio
from aiokafka.errors import KafkaError
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)

from app.db import SessionLocal
from app.deps import require_roles
from app.ingestion.adapters.instagram import InstagramAdapter
from app.ingestion.adapters.reddit import RedditAdapter
from app.ingestion.adapters.twitter import TwitterAdapter
from app.ingestion.adapters.youtube import YouTubeAdapter
from app.lib.observability_metrics import record_event_state, record_external_feed
from app.models.user import User
from app.streaming.producer import ProducerManager

logger = logging.getLogger("app.api.routes.ingest")

router = APIRouter(prefix="/incidents", tags=["ingest"])

_WRITE_ROLES = ("admin", "emergency_manager", "responder_coordinator")

_ADAPTERS: dict[str, type] = {
    "twitter": TwitterAdapter,
    "reddit": RedditAdapter,
    "instagram": InstagramAdapter,
    "youtube": YouTubeAdapter,
}


class ProducerUnavailableError(RuntimeError):
    pass


async def _start_producer() -> ProducerManager:
    producer = ProducerManager()
    try:
        with anyio.fail_after(5.0):
            await producer.start()
    except (KafkaError, OSError, RuntimeError, TimeoutError) as exc:
        await producer.stop()
        raise ProducerUnavailableError("Redpanda is unavailable") from exc
    return producer


async def _run_ingestion(
    adapter_cls: type,
    config: dict[str, Any],
    org_id: str,
    incident_id: str,
) -> int:
    db = SessionLocal()
    producer = await _start_producer()
    adapter = adapter_cls(config)
    try:
        count = await adapter.sync(db, producer, org_id, incident_id)
        record_external_feed(adapter_cls.__name__, "processed")
        record_event_state("processed", "api", "observations.raw")
        logger.info(
            "Ingested %d observations for incident %s via %s",
            count, incident_id, adapter_cls.__name__,
        )
        return count
    finally:
        await adapter.close()
        await producer.stop()
        db.close()


@router.post(
    "/{incident_id}/ingest/social-media",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_social_media_ingestion(
    incident_id: str,
    request: Request,
    source_type: str = Query(
        ..., description="twitter|reddit|instagram|youtube",
    ),
    config: dict[str, Any] | None = Body(default=None),
    user: User = Depends(require_roles(*_WRITE_ROLES)),
) -> dict[str, Any]:
    org_id = request.state.org_id or ""
    source = source_type.lower()
    if source not in _ADAPTERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source_type must be one of {list(_ADAPTERS)}",
        )

    try:
        count = await _run_ingestion(
            _ADAPTERS[source], config or {}, org_id, incident_id
        )
    except ProducerUnavailableError as exc:
        record_external_feed(source, "failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "deferred", "reason": str(exc)},
        ) from exc
    except (OSError, RuntimeError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "deferred", "reason": "publish failed"},
        ) from exc

    return {
        "status": "accepted",
        "incident_id": incident_id,
        "source_type": source,
        "published_count": count,
        "message": "Ingestion triggered. Observations land as access_policy=sensitive.",
    }


__all__ = ["router"]
