"""Background worker entrypoint (DESIGN §1 / §6).

Runs an APScheduler loop that calls ``ingestion.pipeline.run_source`` per active
source on its refresh interval. This is a boot stub so the ``worker`` container
starts cleanly; Task #9 fills in source scheduling and the processing chain.

Run with: ``python -m app.worker``
"""
from __future__ import annotations

import logging
import time

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")


def tick() -> None:
    """One scheduler iteration. Stub: no-op; Task #9 wires run_source per source."""
    logger.debug("worker tick (stub) — no sources scheduled yet")


def main() -> None:
    logger.info(
        "Worker started (poll interval=%ss). Stub loop — Task #9 adds source scheduling.",
        settings.WORKER_POLL_INTERVAL_S,
    )
    try:
        while True:
            tick()
            time.sleep(settings.WORKER_POLL_INTERVAL_S)
    except KeyboardInterrupt:  # pragma: no cover
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
