"""Confidence vector computation — 6 dimensions per SOTA spec §6.1.

Computes q_i = [S_i, C_i, F_i, G_i, M_i, K_i] for each observation:
- S: source reliability (Beta model via SourceReliabilityTracker)
- C: corroboration strength (nearby observations supporting same claim)
- F: freshness (exponential decay via FreshnessCalculator)
- G: geographic precision (source-type-based)
- M: model uncertainty (None for direct observations)
- K: conflict level (contradicting observations)

The 6-dimensional vector is stored in quality_flags["confidence_vector"].
Display confidence (weighted sum) is for UI ONLY — the reasoning engine
always uses the full vector, never a compressed scalar.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fusion.freshness import FreshnessCalculator
from app.fusion.reliability import SourceReliabilityTracker
from app.lib.time import now_ms
from app.models.enums import SourceType

# Geographic precision by source type.
_GEO_PRECISION: dict[SourceType, float] = {
    SourceType.sensor: 1.0,          # exact GPS coordinates
    SourceType.satellite: 0.9,       # high-res imagery
    SourceType.drone: 0.8,           # drone imagery
    SourceType.official_feed: 0.7,  # road-segment level
    SourceType.model: 0.5,           # model output
    SourceType.social_media: 0.3,    # vague text
    SourceType.citizen_report: 0.3,  # vague text
    SourceType.other: 0.1,           # unknown / vague
}

# Display confidence weights. M and K have negative weights: higher
# uncertainty/conflict decreases the display score. The reasoning engine
# never uses this scalar — it always consumes the full 6-D vector.
_W_S = 0.25
_W_C = 0.20
_W_F = 0.20
_W_G = 0.10
_W_M = -0.10
_W_K = -0.15

# Relative tolerance for value comparison (corroborating vs contradicting).
_VALUE_TOLERANCE = 0.2


@dataclass(frozen=True, slots=True)
class ConfidenceVector:
    """6-dimensional confidence vector q_i = [S, C, F, G, M, K]."""

    s: float            # source reliability [0, 1]
    c: float            # corroboration [0, 1]
    f: float            # freshness [0, 1]
    g: float            # geo precision [0, 1]
    m: float | None     # model uncertainty [0, 1], None for direct obs
    k: float            # conflict level [0, 1]

    def to_dict(self) -> dict[str, float | None]:
        """Serialize for storage in quality_flags["confidence_vector"]."""
        return {
            "s": self.s, "c": self.c, "f": self.f,
            "g": self.g, "m": self.m, "k": self.k,
        }


class _ObsLike(Protocol):
    """Structural type for observation-like objects."""

    observation_id: str
    source_id: str
    source_type: SourceType
    phenomenon: str
    observed_at: int
    geometry_uncertainty: float
    model_uncertainty: float | None
    quality_flags: dict[str, Any]
    geometry: object
    org_id: str
    event_type: str
    value: float | None


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters between two lat/lng points."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _extract_coords(geometry: object) -> tuple[float, float] | None:
    """Extract (lat, lng) from WKT, WKB, GeoJSON, shapely, or geoalchemy2."""
    import shapely.geometry
    import shapely.wkb
    import shapely.wkt

    if geometry is None:
        return None
    geom: Any
    if isinstance(geometry, str):
        geom = shapely.wkt.loads(geometry)
    elif isinstance(geometry, (bytes, bytearray)):
        geom = shapely.wkb.loads(bytes(geometry))
    elif isinstance(geometry, dict):
        geom = shapely.geometry.shape(geometry)
    elif hasattr(geometry, "geom_type"):
        geom = geometry
    else:
        from geoalchemy2.shape import to_shape
        geom = to_shape(geometry)
    point = geom.centroid if geom.geom_type != "Point" else geom
    return (float(point.y), float(point.x))


def _is_contradicting(a: _ObsLike, b: _ObsLike) -> bool:
    """True if b contradicts a (divergent value within tolerance)."""
    if a.value is None or b.value is None:
        return False
    denom = max(abs(a.value), abs(b.value), 1.0)
    return abs(a.value - b.value) / denom >= _VALUE_TOLERANCE


class ConfidenceVectorCalculator:
    """Computes the 6-dimensional confidence vector for an observation."""

    def __init__(self, freshness_calc: FreshnessCalculator | None = None) -> None:
        self._freshness = freshness_calc or FreshnessCalculator()

    def compute_vector(
        self,
        observation: _ObsLike,
        current_time_ms: int | None = None,
        db_session: Session | None = None,
        candidates: Sequence[_ObsLike] | None = None,
    ) -> ConfidenceVector:
        """Compute all 6 dimensions of the confidence vector."""
        current = current_time_ms or now_ms()
        return ConfidenceVector(
            s=self._source_reliability(observation, db_session),
            c=self.compute_corroboration(observation, db_session, candidates),
            f=self._freshness.compute_freshness(
                observation.observed_at, current, observation.phenomenon
            ),
            g=self.compute_geo_precision(observation.source_type),
            m=observation.model_uncertainty,
            k=self.compute_conflict(observation, db_session, candidates),
        )

    def compute_geo_precision(self, source_type: SourceType) -> float:
        """G_i: geographic precision based on source type."""
        return _GEO_PRECISION.get(source_type, 0.1)

    def compute_corroboration(
        self,
        observation: _ObsLike,
        db_session: Session | None = None,
        candidates: Sequence[_ObsLike] | None = None,
    ) -> float:
        """C_i: corroboration strength in [0, 1].

        Counts nearby observations (spatial+temporal window) supporting
        the same claim. Returns 1 - exp(-n) where n is the count.
        """
        nearby = self._nearby(observation, db_session, candidates)
        n = sum(1 for o in nearby if not _is_contradicting(observation, o))
        return 1.0 - math.exp(-n)

    def compute_conflict(
        self,
        observation: _ObsLike,
        db_session: Session | None = None,
        candidates: Sequence[_ObsLike] | None = None,
    ) -> float:
        """K_i: conflict level in [0, 1].

        0 if no contradictions, increases with contradicting observations.
        Returns 1 - exp(-n) where n is the contradicting count.
        """
        nearby = self._nearby(observation, db_session, candidates)
        n = sum(1 for o in nearby if _is_contradicting(observation, o))
        return 1.0 - math.exp(-n)

    def compute_display_confidence(self, vector: ConfidenceVector) -> float:
        """Weighted sum for UI display ONLY. Never use for reasoning."""
        m = vector.m if vector.m is not None else 0.0
        return (
            _W_S * vector.s
            + _W_C * vector.c
            + _W_F * vector.f
            + _W_G * vector.g
            + _W_M * m
            + _W_K * vector.k
        )

    def attach_to_observation(
        self, observation: _ObsLike, vector: ConfidenceVector
    ) -> None:
        """Store vector in observation.quality_flags["confidence_vector"]."""
        observation.quality_flags["confidence_vector"] = vector.to_dict()

    def _source_reliability(
        self, observation: _ObsLike, db_session: Session | None
    ) -> float:
        """S_i: source reliability from Beta model."""
        if db_session is None:
            return 0.5  # prior Beta(2,2) expected value
        tracker = SourceReliabilityTracker(db_session)
        expected, _, _ = tracker.get_reliability(
            observation.source_id, observation.phenomenon
        )
        return expected

    def _nearby(
        self,
        observation: _ObsLike,
        db_session: Session | None,
        candidates: Sequence[_ObsLike] | None,
    ) -> list[_ObsLike]:
        """Observations within spatial+temporal window, excluding self."""
        if candidates is not None:
            pool = list(candidates)
        elif db_session is not None:
            pool = self._query_nearby(observation, db_session)
        else:
            return []
        tau = self._freshness.get_tau(observation.phenomenon)
        window_ms = 2 * tau * 1000
        t_lo = observation.observed_at - window_ms
        t_hi = observation.observed_at + window_ms
        coords = _extract_coords(observation.geometry)
        result: list[_ObsLike] = []
        for o in pool:
            if o.observation_id == observation.observation_id:
                continue
            if not (t_lo <= o.observed_at <= t_hi):
                continue
            if coords is not None:
                oc = _extract_coords(o.geometry)
                if oc is not None:
                    dist = _haversine_m(coords[0], coords[1], oc[0], oc[1])
                    radius = max(
                        observation.geometry_uncertainty,
                        o.geometry_uncertainty,
                        100.0,
                    )
                    if dist > radius:
                        continue
            result.append(o)
        return result

    def _query_nearby(
        self, observation: _ObsLike, db_session: Session
    ) -> list[_ObsLike]:
        """Query DB for same-phenomenon observations in temporal window."""
        from app.models.observation import Observation

        tau = self._freshness.get_tau(observation.phenomenon)
        window_ms = 2 * tau * 1000
        stmt = select(Observation).where(
            Observation.phenomenon == observation.phenomenon,
            Observation.org_id == observation.org_id,
            Observation.observed_at >= observation.observed_at - window_ms,
            Observation.observed_at <= observation.observed_at + window_ms,
            Observation.observation_id != observation.observation_id,
        )
        return list(db_session.execute(stmt).scalars().all())


__all__ = ["ConfidenceVector", "ConfidenceVectorCalculator"]
