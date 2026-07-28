"""SensorIngestionService — reads from any SensorSource and publishes to Kafka.

Bridges the ``SensorSource`` protocol (MQTT, serial, SensorThings) to the
platform's streaming pipeline via ``ProducerManager.send(
"observations.raw", payload)``. The service can run in a continuous
loop or be called once (``ingest_once``).

Error handling: if a single ``read_telemetry()`` call fails, the error
is logged and the loop continues (does not crash). If the producer is
unavailable, observations are logged but not published.
"""

from __future__ import annotations

import asyncio
import logging

from app.sensing.sensor_source import SensorSource
from app.streaming.producer import ProducerManager

logger = logging.getLogger(__name__)

_TOPIC = "observations.raw"
_DEFAULT_LOOP_INTERVAL_S = 1.0


class SensorIngestionService:
    """Reads telemetry from a ``SensorSource`` and publishes to Kafka.

    Usage:
        service = SensorIngestionService(source, producer)
        await service.start()
        await service.ingest_once()
        await service.stop()

    Or run continuously:
        await service.run()  # blocks until stopped
    """

    def __init__(
        self,
        source: SensorSource,
        producer: ProducerManager,
        loop_interval_s: float = _DEFAULT_LOOP_INTERVAL_S,
    ) -> None:
        self._source = source
        self._producer = producer
        self._loop_interval_s = loop_interval_s
        self._running = False

    async def start(self) -> None:
        """Start the Kafka producer if not already started."""
        if not self._producer.is_started:
            await self._producer.start()

    async def ingest_once(self) -> dict | None:
        """Read one telemetry sample and publish it.

        Returns the published payload dict, or ``None`` if reading
        failed or the producer is not started. Errors are logged but
        not raised — the caller can decide whether to retry.
        """
        if not self._producer.is_started:
            logger.warning("Producer not started — call start() first")
            return None

        try:
            payload = self._source.read_telemetry()
        except Exception as exc:
            logger.error(
                "Failed to read telemetry from %s: %s",
                getattr(self._source, "device_id", "unknown"),
                exc,
            )
            return None

        try:
            await self._producer.send(_TOPIC, payload)
            logger.info(
                "Published telemetry from %s (observation_id=%s)",
                self._source.device_id,
                payload.get("observation_id"),
            )
        except Exception as exc:
            logger.error(
                "Failed to publish telemetry from %s: %s",
                self._source.device_id,
                exc,
            )
            return None

        return payload

    async def run(self) -> None:
        """Run the ingestion loop until ``stop()`` is called.

        Reads telemetry, publishes it, then sleeps for
        ``loop_interval_s`` before the next iteration. Errors in
        individual iterations are logged and the loop continues.
        """
        self._running = True
        await self.start()
        logger.info(
            "SensorIngestionService started for device %s",
            self._source.device_id,
        )
        while self._running:
            await self.ingest_once()
            await asyncio.sleep(self._loop_interval_s)

    def stop(self) -> None:
        """Signal the ingestion loop to stop after the current iteration."""
        self._running = False

    async def stop_and_close(self) -> None:
        """Stop the loop and shut down the producer."""
        self.stop()
        if self._producer.is_started:
            await self._producer.stop()
        close = getattr(self._source, "close", None)
        if callable(close):
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("Error closing source %s: %s", self._source.device_id, exc)


__all__ = ["SensorIngestionService"]
