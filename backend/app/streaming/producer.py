"""Async Kafka producer for Redpanda — wraps aiokafka AIOKafkaProducer.

Sends JSON messages to Redpanda topics with idempotent semantics. Used by
the FastAPI app and ingestion workers to publish raw observations to
`observations.raw`, which the Benthos pipeline consumes.
"""

import json
import logging

from aiokafka import AIOKafkaProducer

from app.config import settings
from app.lib.ulid import generate_ulid

logger = logging.getLogger("app.streaming.producer")


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
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            enable_idempotence=True,
            acks="all",
        )
        await self._producer.start()
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
        await self._producer.send_and_wait(topic, message, key=key)
        logger.debug("Sent message to %s (key=%s)", topic, key)

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


__all__ = ["ProducerManager"]
