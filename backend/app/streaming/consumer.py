"""Async Kafka consumer for observations.normalized — INSERT to PostgreSQL.

Reads normalized observation messages from the `observations.normalized` topic
(written by the Benthos pipeline), deduplicates by observation_id via the
idempotency_keys table, and INSERTs valid observations into PostgreSQL with
audit provenance. Malformed messages are forwarded to `observations.dlq`.
"""

import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal
from app.lib.idempotency import check_and_record
from app.lib.time import now_ms
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation
from app.streaming.post_commit import run_post_commit_fusion

logger = logging.getLogger("app.streaming.consumer")

DLQ_TOPIC = "observations.dlq"


class ConsumerManager:
    """Async Kafka consumer persisting observations to PostgreSQL.

    Reads from `observations.normalized`, deduplicates by observation_id via
    the idempotency_keys table, and INSERTs valid observations. Malformed
    messages are forwarded to the `observations.dlq` topic.
    """

    def __init__(self, bootstrap_servers: str | None = None, group_id: str = "observations-consumer") -> None:
        self._bootstrap = bootstrap_servers or settings.REDPANDA_BOOTSTRAP_SERVERS
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._dlq_producer: AIOKafkaProducer | None = None
        self._batch_size = int(os.environ.get("CONSUMER_BATCH_SIZE", "10"))
        self._flush_interval_s = float(
            os.environ.get("CONSUMER_FLUSH_INTERVAL_S", "5")
        )
        self._buffer: list[dict] = []
        self._last_flush_ms = now_ms()
        self._flush_task: asyncio.Task[None] | None = None

    async def start(self, topics: list[str]) -> None:
        """Subscribe to the given Kafka topics and start the DLQ producer."""
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        await self._consumer.start()

        self._dlq_producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        await self._dlq_producer.start()

        self._flush_task = asyncio.create_task(self._timer_flush())
        logger.info("Consumer started on topics %s", topics)

    async def consume(self) -> None:
        """Main consume loop — read, retry, INSERT, commit offset.

        Transient errors are retried with exponential backoff. Permanent
        errors and exhausted retries forward the message to the DLQ. The
        offset is always committed to avoid infinite reprocessing.
        """
        if self._consumer is None:
            raise RuntimeError("Consumer not started — call start() first")

        async for msg in self._consumer:
            try:
                await self._retry_with_backoff(msg.value)
            except Exception as exc:
                logger.error("Failed to process message after retries: %s", exc)
                await self._send_to_dlq(msg.value, str(exc))
            finally:
                await self._consumer.commit()

    def _should_retry(self, exc: Exception) -> bool:
        """Classify an exception as transient (retry) or permanent (DLQ)."""
        if isinstance(exc, (ValueError, KeyError, TypeError, AttributeError)):
            return False
        if isinstance(exc, IntegrityError):
            return False
        return True

    async def _retry_with_backoff(self, payload: dict) -> None:
        """Process a message with exponential backoff on transient errors.

        Permanent errors raise immediately. Transient errors are retried up
        to 3 times with 1s, 2s, 4s delays before re-raising.
        """
        delays = [1.0, 2.0, 4.0]
        for attempt in range(len(delays) + 1):
            try:
                await self._process(payload)
                return
            except Exception as exc:
                if not self._should_retry(exc) or attempt == len(delays):
                    raise
                logger.warning(
                    "Transient error (attempt %d/%d), retrying in %ss: %s",
                    attempt + 1,
                    len(delays) + 1,
                    delays[attempt],
                    exc,
                )
                await asyncio.sleep(delays[attempt])

    async def _process(self, payload: dict) -> None:
        """Validate and buffer a payload for batch insertion.

        The payload is added to an in-memory buffer. When the buffer reaches
        ``_batch_size`` or ``_flush_interval_s`` seconds elapse, the buffer is
        flushed via ``_flush_batch`` which does a single ``add_all`` + ``commit``.
        Confidence/hypothesis/audit run as a post-commit background thread.
        """
        observation_id = payload.get("observation_id")
        if not observation_id:
            raise ValueError("missing observation_id")

        self._buffer.append(payload)
        if len(self._buffer) >= self._batch_size:
            await self._flush_batch()
            return
        if self._should_flush_by_time():
            await self._flush_batch()

    def _should_flush_by_time(self) -> bool:
        """True if ``_flush_interval_s`` has elapsed since the last flush."""
        return (now_ms() - self._last_flush_ms) / 1000.0 >= self._flush_interval_s

    async def _flush_batch(self) -> None:
        """Flush buffered payloads: idempotency check + batch INSERT + spawn fusion."""
        if not self._buffer:
            return

        payloads = self._buffer[:]
        self._buffer.clear()
        self._last_flush_ms = now_ms()

        db = SessionLocal()
        observation_ids: list[str] = []
        audit_payloads: list[dict] = []
        try:
            observations: list[Observation] = []
            for payload in payloads:
                observation_id = payload.get("observation_id")
                if observation_id is None:
                    logger.warning("Payload missing observation_id, skipping")
                    continue
                source = str(payload.get("source_type", "unknown")).lower()
                is_new = check_and_record(db, source, observation_id)
                if not is_new:
                    logger.debug(
                        "Duplicate observation_id=%s, skipping", observation_id
                    )
                    continue
                observations.append(self._build_observation(payload))
                observation_ids.append(observation_id)
                audit_payloads.append(payload)

            if observations:
                db.add_all(observations)
                db.commit()
                logger.info("Flushed batch of %d observations", len(observations))
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if observation_ids:
            asyncio.create_task(
                asyncio.to_thread(
                    run_post_commit_fusion, observation_ids, audit_payloads
                )
            )

    async def _timer_flush(self) -> None:
        """Periodically flush non-empty buffer between message arrivals."""
        while True:
            await asyncio.sleep(self._flush_interval_s)
            if self._buffer:
                try:
                    await self._flush_batch()
                except Exception as exc:
                    logger.error("Timer flush failed: %s", exc)

    def _build_observation(self, p: dict) -> Observation:
        """Map a normalized payload dict to an Observation ORM instance."""
        geojson = json.dumps(p["geometry"])
        return Observation(
            observation_id=p["observation_id"],
            event_type=p["event_type"],
            phenomenon=p["phenomenon"],
            value=p.get("value"),
            unit=p.get("unit"),
            geometry=func.ST_SetSRID(func.ST_GeomFromGeoJSON(geojson), 4326),
            geometry_uncertainty=p.get("geometry_uncertainty", 0.0),
            observed_at=p["observed_at"],
            valid_from=p.get("valid_from", p["observed_at"]),
            valid_until=p.get("valid_until"),
            received_at=p.get("received_at", now_ms()),
            source_id=p["source_id"],
            source_type=SourceType(str(p["source_type"]).lower()),
            collection_method=p.get("collection_method", "unknown"),
            source_reliability=p.get("source_reliability", 0.5),
            freshness=p.get("freshness", 1.0),
            corroboration_state=CorroborationState(
                p.get("corroboration_state", "uncorroborated")
            ),
            model_uncertainty=p.get("model_uncertainty"),
            quality_flags=p.get("quality_flags", {}),
            access_policy=AccessPolicy(p.get("access_policy", "internal")),
            provenance_chain=p.get("provenance_chain", {}),
            raw_data_hash=p.get("raw_data_hash", ""),
            model_version=p.get("model_version"),
            supersedes=p.get("supersedes"),
            duplicate_group=p.get("duplicate_group"),
            org_id=p["org_id"],
            incident_id=p["incident_id"],
        )

    async def _send_to_dlq(self, payload: dict, error: str) -> None:
        """Send a malformed message to the DLQ topic with error context."""
        if self._dlq_producer is None:
            return
        await self._dlq_producer.send_and_wait(
            DLQ_TOPIC,
            {
                "error": error,
                "original_payload": payload,
                "failed_at": now_ms(),
            },
        )
        logger.warning("Sent message to DLQ: %s", error)

    async def stop(self) -> None:
        """Gracefully shut down: cancel timer, flush buffer, stop consumer/producer."""
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        if self._buffer:
            try:
                await self._flush_batch()
            except Exception as exc:
                logger.error("Final flush failed: %s", exc)
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        if self._dlq_producer is not None:
            await self._dlq_producer.stop()
            self._dlq_producer = None
        logger.info("Consumer stopped")


__all__ = ["ConsumerManager"]
