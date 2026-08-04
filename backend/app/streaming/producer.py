"""Async Kafka producer for Redpanda — wraps aiokafka AIOKafkaProducer.

Sends JSON messages to Redpanda topics with idempotent semantics. Used by
the FastAPI app and ingestion workers to publish raw observations to
`observations.raw`, which the Benthos pipeline consumes.
"""

import json
import logging

from aiokafka import AIOKafkaProducer
from sqlalchemy.orm import Session

from app.config import settings
from app.lib.idempotency import record_replay_dispatch, replay_payload
from app.lib.observability import inject_trace_headers, telemetry_span
from app.lib.observability_metrics import record_event_state, record_queue_message
from app.lib.ulid import generate_ulid
from app.models.events import Event, RawEvent

logger = logging.getLogger("app.streaming.producer")

RAW_TOPIC = "observations.raw"


class ProducerManager:
    """Async Kafka producer writing JSON messages to Redpanda topics.

    Usage:
        producer = ProducerManager()
        await producer.start()
        await producer.send("observations.raw", {"observation_id": "..."})
        await producer.stop()
    """

    def __init__(self, bootstrap_servers: str | None = None) -> None:
        self._bootstrap = bootstrap_servers or settings.REDPANDA_BOOTSTRAP_SERVERS
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Connect to Redpanda and start the underlying aiokafka producer."""
        producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            enable_idempotence=True,
            acks="all",
        )
        try:
            await producer.start()
        except (OSError, RuntimeError, TimeoutError):
            await producer.stop()
            raise
        self._producer = producer
        logger.info("Kafka producer connected to %s", self._bootstrap)

    async def send(self, topic: str, message: dict, key: str | None = None) -> None:
        """Send a JSON message to a Kafka topic.

        If key is None, uses the message's observation_id or generates a ULID
        as the partition key for consistent routing.
        """
        if self._producer is None:
            raise RuntimeError("Producer not started — call start() first")
        if key is None:
            key = message.get("observation_id") or generate_ulid()
        trace_headers: dict[str, str] = {}
        inject_trace_headers(trace_headers)
        kafka_headers = [(name, value.encode("ascii")) for name, value in trace_headers.items()]
        with telemetry_span("queue.publish", {"queue_name": topic}):
            await self._producer.send_and_wait(topic, message, key=key, headers=kafka_headers)
        record_queue_message(topic, "published")
        record_event_state("accepted", "api", topic)
        logger.debug("Published durable queue message")

    async def send_raw_event(self, event: RawEvent) -> None:
        await self.send(
            RAW_TOPIC,
            event.model_dump(mode="json"),
            key=f"{event.org_id}:{event.source_id}:{event.external_id}",
        )

    async def replay_failure(
        self,
        db: Session,
        entity: str,
        *,
        org_id: str,
        actor: str,
        role: str,
    ) -> Event:
        failure, payload = replay_payload(db, entity, org_id=org_id, role=role)
        await self.send(
            RAW_TOPIC,
            payload,
            key=str(payload.get("external_id") or payload.get("observation_id") or entity),
        )
        return record_replay_dispatch(db, failure, actor=actor, role=role)

    @property
    def is_started(self) -> bool:
        """True if the producer is connected and ready to send."""
        return self._producer is not None

    async def stop(self) -> None:
        """Gracefully shut down the producer, flushing pending messages."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka producer stopped")


__all__ = ["RAW_TOPIC", "ProducerManager"]
