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
from aiokafka.structs import TopicPartition
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal
from app.lib.idempotency import (
    INGESTION_FAILURE_RETENTION_DAYS,
    IdempotencyConflictError,
    check_and_record,
    record_ingestion_failure,
    record_raw_event,
)
from app.lib.observability import extract_trace_context, telemetry_span
from app.lib.observability_metrics import (
    queue_age_seconds,
    queue_depth,
    record_event_state,
    record_queue_message,
    record_worker_message,
    worker_retries_total,
)
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.events import RawEvent
from app.models.observation import Observation
from app.streaming.post_commit import run_post_commit_fusion

logger = logging.getLogger("app.streaming.consumer")

DLQ_TOPIC = "observations.dlq"
DLQ_RETENTION_DAYS = INGESTION_FAILURE_RETENTION_DAYS
_OffsetKey = tuple[str, int]
_PendingOffset = tuple[str, int, int]


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
        self._buffer_offsets: list[_PendingOffset | None] = []
        self._pending_fusion: list[tuple[str, dict]] = []
        self._pending_fusion_offsets: list[_PendingOffset] = []
        self._offset_state: dict[_OffsetKey, tuple[int, set[int]]] = {}
        self._ready_offsets: dict[_OffsetKey, int] = {}
        self._ack_pending = False
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
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            enable_idempotence=True,
            acks="all",
        )
        await self._dlq_producer.start()

        self._flush_task = asyncio.create_task(self._timer_flush())
        logger.info("Consumer started on topics %s", topics)

    async def consume(self) -> None:
        """Main consume loop — read, retry, INSERT, commit offset.

        Transient errors are retried with exponential backoff. Permanent
        errors and exhausted retries are recorded and forwarded to the DLQ;
        offsets commit only after durable persistence or DLQ acknowledgement.
        """
        if self._consumer is None:
            raise RuntimeError("Consumer not started — call start() first")

        async for msg in self._consumer:
            self._ack_pending = True
            pending_offset = (str(msg.topic), msg.partition, msg.offset)
            self._register_offset(pending_offset)
            queue_name = str(msg.topic)
            record_queue_message(queue_name, "received")
            record_event_state("accepted", "worker", queue_name)
            if msg.timestamp is not None:
                queue_age_seconds.labels(queue_name=queue_name).observe(
                    max(0.0, (now_ms() - msg.timestamp) / 1000.0)
                )
            parent = extract_trace_context({
                key: value.decode("ascii", errors="ignore")
                for key, value in msg.headers or []
            })
            from opentelemetry.context import attach, detach

            token = attach(parent)
            try:
                with telemetry_span("worker.process", {"queue_name": queue_name}):
                    await self._retry_with_backoff(msg.value, pending_offset)
                record_worker_message("processed")
                record_event_state("processed", "worker", queue_name)
            except Exception as exc:
                failure = self._record_failure(msg.value, str(exc))
                sent = await self._send_to_dlq(msg.value, str(exc), failure)
                if not sent:
                    record_event_state("lost", "worker", queue_name)
                    raise RuntimeError(
                        "DLQ handoff was not acknowledged; source offset retained"
                    ) from exc
                self._mark_offset_complete(pending_offset)
                record_event_state("failed", "worker", queue_name)
                record_worker_message("failed")
                logger.error("Failed to process message after retries: %s", type(exc).__name__)
                if self._buffer or self._pending_fusion:
                    await self._flush_batch()
            finally:
                detach(token)
            await self._commit_ready_offsets()
            self._ack_pending = False

    def _should_retry(self, exc: Exception) -> bool:
        """Classify an exception as transient (retry) or permanent (DLQ)."""
        if isinstance(
            exc,
            (
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
                IdempotencyConflictError,
            ),
        ):
            return False
        if isinstance(exc, IntegrityError):
            return False
        return True

    async def _retry_with_backoff(
        self, payload: dict, pending_offset: _PendingOffset | None = None
    ) -> None:
        """Process a message with exponential backoff on transient errors.

        Permanent errors raise immediately. Transient errors are retried up
        to 3 times with 1s, 2s, 4s delays before re-raising.
        """
        delays = [1.0, 2.0, 4.0]
        for attempt in range(len(delays) + 1):
            try:
                await self._process(payload, pending_offset)
                return
            except Exception as exc:
                if not self._should_retry(exc) or attempt == len(delays):
                    raise
                worker_retries_total.labels(worker="worker").inc()
                logger.warning(
                    "Transient worker error (attempt %d/%d), retrying in %ss: %s",
                    attempt + 1,
                    len(delays) + 1,
                    delays[attempt],
                    type(exc).__name__,
                )
                await asyncio.sleep(delays[attempt])

    async def _process(
        self, payload: dict, pending_offset: _PendingOffset | None = None
    ) -> None:
        """Validate and buffer a payload for batch insertion.

        The payload is added to an in-memory buffer. When the buffer reaches
        ``_batch_size`` or ``_flush_interval_s`` seconds elapse, the buffer is
        flushed via ``_flush_batch`` which does a single ``add_all`` + ``commit``.
        Confidence/hypothesis/audit run as a post-commit background thread.
        """
        observation_id = payload.get("observation_id")
        if not observation_id:
            raise ValueError("missing observation_id")

        self._build_observation(payload)
        if pending_offset is None or pending_offset not in self._buffer_offsets:
            self._buffer.append(payload)
            self._buffer_offsets.append(pending_offset)
        queue_depth.labels(queue_name="observations.normalized").set(len(self._buffer))
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
        if not self._buffer and not self._pending_fusion:
            return

        payloads = self._buffer[:]
        batch_offsets = [offset for offset in self._buffer_offsets if offset is not None]
        pending_fusion = self._pending_fusion[:]
        pending_fusion_offsets = self._pending_fusion_offsets[:]

        db = SessionLocal()
        try:
            observations: list[Observation] = []
            fusion_items = pending_fusion[:]
            for payload in payloads:
                observation_id = payload.get("observation_id")
                if observation_id is None:
                    raise ValueError("missing observation_id")
                source = str(payload["source_id"])
                external_id = str(payload.get("external_id") or observation_id)
                is_new = check_and_record(
                    db,
                    source,
                    external_id,
                    org_id=payload["org_id"],
                    incident_id=payload["incident_id"],
                    payload=payload,
                    commit=False,
                )
                if not is_new:
                    logger.debug("Duplicate event skipped")
                    continue
                raw_event = self._build_raw_event(payload)
                if not record_raw_event(db, raw_event):
                    continue
                observations.append(self._build_observation(payload, raw_event))
                fusion_items.append((observation_id, payload))

            if observations:
                db.add_all(observations)
                db.commit()
                logger.info("Flushed observation batch")
            elif not fusion_items:
                db.rollback()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        self._buffer.clear()
        self._buffer_offsets.clear()
        queue_depth.labels(queue_name="observations.normalized").set(0)
        self._last_flush_ms = now_ms()
        self._pending_fusion = fusion_items
        self._pending_fusion_offsets = pending_fusion_offsets + batch_offsets
        if fusion_items:
            fusion_ids, fusion_payloads = zip(*fusion_items)
            await asyncio.to_thread(
                run_post_commit_fusion,
                list(fusion_ids),
                list(fusion_payloads),
            )
            self._pending_fusion.clear()
        for offset in self._pending_fusion_offsets:
            self._mark_offset_complete(offset)
        self._pending_fusion_offsets.clear()

    async def _timer_flush(self) -> None:
        """Periodically flush non-empty buffer between message arrivals."""
        while True:
            await asyncio.sleep(self._flush_interval_s)
            if self._buffer or self._pending_fusion:
                try:
                    await self._flush_batch()
                    await self._commit_ready_offsets()
                    if not self._buffer and not self._pending_fusion:
                        self._ack_pending = False
                except Exception as exc:
                    logger.error("Timer flush failed: %s", type(exc).__name__)

    def _build_raw_event(self, p: dict) -> RawEvent:
        return RawEvent(
            event_id=p.get("raw_event_id") or generate_ulid(),
            org_id=p["org_id"],
            incident_id=p["incident_id"],
            source_id=p["source_id"],
            external_id=p.get("external_id") or p["observation_id"],
            event_type=p["event_type"],
            source_time_ms=p.get("source_time_ms", p["observed_at"]),
            receipt_time_ms=p.get(
                "receipt_time_ms", p.get("received_at", now_ms())
            ),
            sequence=p.get("sequence", 1),
            payload=p,
            provenance=p.get("provenance"),
            visibility=p.get("visibility", p.get("access_policy", "internal")),
            review_status=p.get("review_status", "draft"),
            schema_version=p.get("schema_version", "1.0"),
        )

    def _build_observation(
        self, p: dict, raw_event: RawEvent | None = None
    ) -> Observation:
        """Map a normalized payload dict to an Observation ORM instance."""
        canonical_hash = raw_event.canonical_hash() if raw_event else p.get("raw_data_hash", "")
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
            raw_data_hash=canonical_hash,
            model_version=p.get("model_version"),
            supersedes=p.get("supersedes"),
            duplicate_group=p.get("duplicate_group"),
            org_id=p["org_id"],
            incident_id=p["incident_id"],
            raw_event_id=raw_event.event_id if raw_event else p.get("raw_event_id"),
            source_time_ms=raw_event.source_time_ms if raw_event else p.get("source_time_ms"),
            receipt_time_ms=raw_event.receipt_time_ms if raw_event else p.get("receipt_time_ms"),
            sequence=raw_event.sequence if raw_event else p.get("sequence"),
            payload_hash=canonical_hash,
            provenance=(
                raw_event.provenance.model_dump(mode="json")
                if raw_event is not None and raw_event.provenance is not None
                else p.get("provenance")
            ),
            visibility=(
                raw_event.visibility.value
                if raw_event is not None
                else p.get("visibility")
            ),
            review_status=(
                raw_event.review_status.value
                if raw_event is not None
                else p.get("review_status")
            ),
            schema_version=(
                raw_event.schema_version
                if raw_event is not None
                else p.get("schema_version")
            ),
        )

    def _record_failure(self, payload: dict, error: str) -> str:
        db = SessionLocal()
        try:
            return record_ingestion_failure(db, payload, error).id
        finally:
            db.close()

    async def _send_to_dlq(
        self, payload: dict, error: str, failure_id: str | None = None
    ) -> bool:
        """Send a malformed message to the DLQ topic with error context."""
        if self._dlq_producer is None:
            return False
        external_id = str(payload.get("external_id") or payload.get("observation_id") or "unknown")
        await self._dlq_producer.send_and_wait(
            DLQ_TOPIC,
            {
                "failure_event_id": failure_id,
                "error": error,
                "original_payload": payload,
                "failed_at": now_ms(),
                "retention_days": DLQ_RETENTION_DAYS,
            },
            key=external_id,
        )
        record_queue_message(DLQ_TOPIC, "published")
        logger.warning("Sent message to DLQ")
        return True

    async def stop(self) -> None:
        """Gracefully shut down: cancel timer, flush buffer, stop consumer/producer."""
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        if self._buffer or self._pending_fusion:
            try:
                await self._flush_batch()
            except Exception as exc:
                logger.error("Final flush failed: %s", type(exc).__name__)
        try:
            await self._commit_ready_offsets()
        except (OSError, RuntimeError, TimeoutError) as exc:
            logger.error("Final offset commit failed: %s", type(exc).__name__)
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        if self._dlq_producer is not None:
            await self._dlq_producer.stop()
            self._dlq_producer = None
        logger.info("Consumer stopped")

    def _register_offset(self, pending_offset: _PendingOffset) -> None:
        key = pending_offset[:2]
        if key not in self._offset_state:
            self._offset_state[key] = (pending_offset[2], set())

    def _mark_offset_complete(self, pending_offset: _PendingOffset) -> None:
        key = pending_offset[:2]
        state = self._offset_state.get(key)
        if state is None:
            self._offset_state[key] = (pending_offset[2] + 1, set())
            self._ready_offsets[key] = pending_offset[2] + 1
            return
        next_offset, completed = state
        completed.add(pending_offset[2])
        previous_next_offset = next_offset
        while next_offset in completed:
            completed.remove(next_offset)
            next_offset += 1
        self._offset_state[key] = (next_offset, completed)
        if next_offset > previous_next_offset:
            self._ready_offsets[key] = next_offset

    async def _commit_ready_offsets(self) -> None:
        if self._consumer is None or not self._ready_offsets:
            return
        offsets = {
            self._topic_partition(key): value
            for key, value in self._ready_offsets.items()
        }
        await self._consumer.commit(offsets)
        self._ready_offsets.clear()

    @staticmethod
    def _topic_partition(key: _OffsetKey) -> TopicPartition:
        return TopicPartition(key[0], key[1])


__all__ = ["ConsumerManager"]
