"""Honest degradation display — per-feed health, data age, lost feeds, widening uncertainty.

Exposes per-feed status (healthy/degraded/down) based on data age vs phenomenon-specific
tau thresholds. Stale data is flagged as degraded/down, never displayed as current.

GET /api/incidents/{id}/feed-health returns per-feed status with:
- feed_name, status, data_age_seconds, last_update, coverage_pct, queue_backlog, sync_state
"""
from __future__ import annotations

import logging
import math

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.fusion.freshness import DEFAULT_TAU, TAU_BY_PHENOMENON
from app.lib.time import now_ms
from app.models.observation import Observation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Status thresholds: age > tau*DEGRADED → degraded; age > tau*DOWN → down.
DEGRADED_MULTIPLIER: float = 1.0
DOWN_MULTIPLIER: float = 3.0

# Maps phenomenon → capability name. When a feed is down/degraded, the
# corresponding capability is marked unavailable in the degradation summary.
_CAPABILITY_BY_PHENOMENON: dict[str, str] = {
    "water_level": "flood_inundation_map",
    "flood_depth": "flood_inundation_map",
    "road_passability": "route_planning",
    "responder_position": "responder_tracking",
    "shelter_capacity": "shelter_management",
    "rainfall": "rainfall_nowcast",
    "wind_speed": "wind_nowcast",
}


class FeedHealthTracker:
    """Computes per-feed health status based on data age vs tau thresholds.

    A "feed" is a (source_id, phenomenon) pair. Status is derived from the
    age of the most recent observation relative to the phenomenon's tau:
    - age <= tau → healthy
    - tau < age <= 3*tau → degraded
    - age > 3*tau → down (feed considered lost)

    Stale data is NEVER displayed as current — degraded/down feeds are
    clearly marked so operators know the data is stale.
    """

    def __init__(
        self,
        degraded_multiplier: float = DEGRADED_MULTIPLIER,
        down_multiplier: float = DOWN_MULTIPLIER,
    ) -> None:
        self._degraded_multiplier = degraded_multiplier
        self._down_multiplier = down_multiplier

    def compute_data_age(
        self, last_update_ms: int, current_ms: int | None = None
    ) -> float:
        """Return seconds since last_update. Never negative (clamps to 0)."""
        now = current_ms if current_ms is not None else now_ms()
        age_ms = now - last_update_ms
        return max(0.0, age_ms / 1000.0)

    def compute_coverage(self, fresh_count: int, total_count: int) -> float:
        """Return percentage of fresh data in [0.0, 100.0]."""
        if total_count <= 0:
            return 0.0
        return (fresh_count / total_count) * 100.0

    def is_stale(self, data_age_seconds: float, threshold_seconds: float) -> bool:
        """Return True if data_age exceeds threshold."""
        return data_age_seconds > threshold_seconds

    def _feed_status(self, data_age_seconds: float, tau: int) -> str:
        """Derive feed status from age vs tau."""
        if data_age_seconds > tau * self._down_multiplier:
            return "down"
        if data_age_seconds > tau * self._degraded_multiplier:
            return "degraded"
        return "healthy"

    def _uncertainty_multiplier(self, data_age_seconds: float, tau: int) -> float:
        """Return uncertainty multiplier — widens as data ages past tau.

        Fresh data (age <= tau): multiplier = 1.0
        Stale data (age > tau): multiplier = 1.0 + (age - tau) / tau
        """
        if data_age_seconds <= tau:
            return 1.0
        return 1.0 + (data_age_seconds - tau) / tau

    def get_feed_health(
        self,
        incident_id: str,
        db: Session,
        current_ms: int | None = None,
    ) -> dict[str, object]:
        """Return per-feed health status for an incident.

        Groups observations by (source_id, phenomenon) and computes status
        for each feed based on the most recent observation's age.
        """
        rows = db.execute(
            select(
                Observation.source_id,
                Observation.phenomenon,
                func.max(Observation.observed_at).label("last_update"),
                func.count(Observation.observation_id).label("obs_count"),
            )
            .where(Observation.incident_id == incident_id)
            .group_by(Observation.source_id, Observation.phenomenon)
        ).all()

        feeds: list[dict[str, object]] = []
        fresh_count = 0
        for row in rows:
            source_id, phenomenon, last_update, _obs_count = row
            tau = TAU_BY_PHENOMENON.get(phenomenon, DEFAULT_TAU)
            age_s = self.compute_data_age(last_update, current_ms)
            status = self._feed_status(age_s, tau)
            if status == "healthy":
                fresh_count += 1
            feeds.append({
                "feed_name": f"{source_id}:{phenomenon}",
                "source_id": source_id,
                "phenomenon": phenomenon,
                "status": status,
                "data_age_seconds": round(age_s, 3),
                "last_update_ms": last_update,
                "coverage_pct": 100.0 if status == "healthy" else 0.0,
                "queue_backlog": 0,
                "sync_state": "synced",
                "tau_seconds": tau,
                "uncertainty_multiplier": round(
                    self._uncertainty_multiplier(age_s, tau), 3
                ),
            })

        total = len(feeds)
        coverage = self.compute_coverage(fresh_count, total)
        return {
            "incident_id": incident_id,
            "feeds": feeds,
            "total_feeds": total,
            "healthy_feeds": fresh_count,
            "coverage_pct": round(coverage, 2),
        }

    def get_degradation_summary(
        self,
        incident_id: str,
        db: Session,
        current_ms: int | None = None,
    ) -> dict[str, object]:
        """Return overall degradation level, lost feeds, unavailable capabilities."""
        health = self.get_feed_health(incident_id, db, current_ms)
        feeds = health["feeds"]

        lost_feeds = [f["feed_name"] for f in feeds if f["status"] == "down"]
        degraded_feeds = [
            f["feed_name"] for f in feeds if f["status"] == "degraded"
        ]

        if not feeds:
            level = "unknown"
        elif lost_feeds:
            level = "severe"
        elif degraded_feeds:
            level = "degraded"
        else:
            level = "nominal"

        unavailable: list[str] = []
        for f in feeds:
            if f["status"] in ("down", "degraded"):
                cap = _CAPABILITY_BY_PHENOMENON.get(f["phenomenon"])
                if cap and cap not in unavailable:
                    unavailable.append(cap)

        return {
            "incident_id": incident_id,
            "degradation_level": level,
            "lost_feeds": lost_feeds,
            "degraded_feeds": degraded_feeds,
            "unavailable_capabilities": unavailable,
            "coverage_pct": health["coverage_pct"],
            "total_feeds": health["total_feeds"],
            "healthy_feeds": health["healthy_feeds"],
        }


tracker = FeedHealthTracker()


@router.get("/api/incidents/{incident_id}/feed-health")
def feed_health(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return per-feed health status for an incident.

    Each feed is classified as healthy / degraded / down based on data age
    vs phenomenon-specific tau. Stale data is NEVER displayed as current.
    """
    return tracker.get_feed_health(incident_id, db)


@router.get("/api/incidents/{incident_id}/degradation-summary")
def degradation_summary(
    incident_id: str,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return overall degradation summary for an incident."""
    return tracker.get_degradation_summary(incident_id, db)


__all__ = ["FeedHealthTracker", "tracker", "router"]
