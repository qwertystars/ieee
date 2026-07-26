"""Dedicated worker entry point — runs ConsumerManager in its own process.

Subscribes to ``observations.normalized``, persists observations to PostgreSQL
with retry on transient errors, and sends permanent failures to the DLQ.
Exposes Prometheus metrics on port 8001. Handles SIGTERM/SIGINT for graceful
shutdown so the container orchestrator can stop it cleanly.

Run with::

    python -m app.worker.main
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from prometheus_client import Counter, start_http_server

from app.config import settings
from app.streaming.consumer import ConsumerManager

logger = logging.getLogger("app.worker")

TOPICS = ["observations.normalized"]
METRICS_PORT = 8001

# ── Prometheus metrics ───────────────────────────────────────────────────────

messages_processed_total = Counter(
    "worker_messages_processed_total",
    "Total messages processed successfully",
)
messages_failed_total = Counter(
    "worker_messages_failed_total",
    "Total messages that failed processing (sent to DLQ)",
)
retry_attempts_total = Counter(
    "worker_retry_attempts_total",
    "Total retry attempts for transient errors",
)


async def run_worker() -> None:
    """Start the consumer, run the consume loop, and shut down on signal."""
    consumer = ConsumerManager(
        bootstrap_servers=settings.REDPANDA_BOOTSTRAP_SERVERS,
    )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_stop)

    await consumer.start(TOPICS)
    logger.info(
        "Worker started — topics=%s bootstrap=%s",
        TOPICS,
        settings.REDPANDA_BOOTSTRAP_SERVERS,
    )

    consume_task = asyncio.create_task(consumer.consume())
    stop_task = asyncio.create_task(stop_event.wait())

    done, _ = await asyncio.wait(
        {consume_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if consume_task not in done:
        consume_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consume_task

    await consumer.stop()
    logger.info("Worker stopped")


def main() -> None:
    """Entry point — configure logging, start metrics server, run consumer."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    start_http_server(METRICS_PORT)
    logger.info("Prometheus metrics on :%d", METRICS_PORT)

    try:
        asyncio.run(run_worker())
    except Exception:
        logger.exception("Worker crashed")
        raise


if __name__ == "__main__":
    main()
