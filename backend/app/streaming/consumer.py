"""Async Kafka consumer for observations.normalized — INSERT to PostgreSQL.

Reads normalized observation messages from the `observations.normalized` topic
(written by the Benthos pipeline), deduplicates by observation_id via the
idempotency_keys table, and INSERTs valid observations into PostgreSQL with
audit provenance. Malformed messages are forwarded to `observations.dlq`.
"""

import json
import logging

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import func

from app.config import settings
from app.db import SessionLocal
from app.lib.audit import write_audit
from app.lib.idempotency import check_and_record
from app.lib.time import now_ms
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.models.observation import Observation

logger = logging.getLogger("app.streaming.consumer")

DLQ_TOPIC = "observations.dlq"


class ConsumerManager:
    """Async Kafka consumer persisting observations to PostgreSQL.

    Reads from `observations.normalized`, deduplicates by observation_id via
    the idempotency_keys table, and INSERTs valid observations. Malformed
    messages are forwarded to the `observations.dlq` topic.
    """

    def __init__(self, bootstrap_servers: str | None = None) -> None:
        self._bootstrap = bootstrap_servers or settings.REDPANDA_BOOTSTRAP_SERVERS
        self._consumer: AIOKafkaConsumer | None = None
        self._dlq_producer: AIOKafkaProducer | None = None

    async def start(self, topics: list[str]) -> None:
        """Subscribe to the given Kafka topics and start the DLQ producer."""
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self._bootstrap,
            group_id="observations-consumer",
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

        logger.info("Consumer started on topics %s", topics)

    async def consume(self) -> None:
        """Main consume loop — read, dedup, INSERT, commit offset.

        On processing error, the message is forwarded to the DLQ and the
        offset is committed to avoid infinite reprocessing.
        """
        if self._consumer is None:
            raise RuntimeError("Consumer not started — call start() first")

        async for msg in self._consumer:
            try:
                await self._process(msg.value)
            except Exception as exc:
                logger.error("Failed to process message: %s", exc)
                await self._send_to_dlq(msg.value, str(exc))
            finally:
                await self._consumer.commit()

    async def _process(self, payload: dict) -> None:
        """Parse, dedup, and INSERT a single observation."""
        observation_id = payload.get("observation_id")
        if not observation_id:
            raise ValueError("missing observation_id")

        db = SessionLocal()
        try:
            source = str(payload.get("source_type", "unknown")).lower()
            is_new = check_and_record(db, source, observation_id)
            if not is_new:
                logger.debug("Duplicate observation_id=%s, skipping", observation_id)
                return

            obs = self._build_observation(payload)
            db.add(obs)
            db.commit()

            write_audit(
                db,
                org_id=payload.get("org_id", ""),
                incident_id=payload.get("incident_id", ""),
                actor="streaming-consumer",
                action="observation.ingested",
                entity=observation_id,
                after={
                    "source_type": payload.get("source_type"),
                    "observed_at": payload.get("observed_at"),
                },
            )
            logger.info("Inserted observation %s", observation_id)
        finally:
            db.close()

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
        """Gracefully shut down consumer and DLQ producer."""
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        if self._dlq_producer is not None:
            await self._dlq_producer.stop()
            self._dlq_producer = None
        logger.info("Consumer stopped")


__all__ = ["ConsumerManager"]
