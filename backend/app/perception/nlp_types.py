"""Dataclasses and enums for the citizen-report NLP pipeline (T21).

The pipeline processes social-media posts, citizen reports, and helpline-call
transcripts: speech/text -> language ID -> ASR -> PII detection/redaction ->
urgency + category extraction -> place-name extraction -> geolocation
candidate generation -> duplicate clustering -> credibility estimation ->
human review queue.

Geolocation candidates are NEVER exact points for vague reports. A vague
reference like "near the old market" is represented as a ``distribution`` or
``uncertainty_polygon`` — the downstream reasoning engine decides how to
reconcile it with other evidence.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Urgency(str, enum.Enum):
    """Operational urgency of a report."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Category(str, enum.Enum):
    """Humanitarian category of a report."""

    trapped_person = "trapped_person"
    missing_person = "missing_person"
    medical_emergency = "medical_emergency"
    flooding = "flooding"
    structural_collapse = "structural_collapse"
    fire_electrical = "fire_electrical"
    blocked_route = "blocked_route"
    shelter_request = "shelter_request"
    food_water_medication = "food_water_medication"
    infrastructure_outage = "infrastructure_outage"
    rescue_completed = "rescue_completed"
    irrelevant = "irrelevant"


class GeoType(str, enum.Enum):
    """Type of geolocation candidate.

    ``exact`` / ``road_segment`` / ``building`` / ``named_place`` / ``ward``
    are used when the report contains a specific, identifiable reference.
    ``distribution`` is used when multiple candidate locations are plausible.
    ``uncertainty_polygon`` is used for vague references — NEVER invent an
    exact GPS point from a vague report.
    """

    exact = "exact"
    road_segment = "road_segment"
    building = "building"
    named_place = "named_place"
    ward = "ward"
    distribution = "distribution"
    uncertainty_polygon = "uncertainty_polygon"


class PIIType(str, enum.Enum):
    """Kind of personally identifiable information detected."""

    phone = "phone"
    email = "email"
    aadhaar = "aadhaar"
    person_name = "person_name"
    address = "address"


@dataclass(slots=True, frozen=True)
class PIISpan:
    """A detected PII span in the text.

    ``start`` / ``end`` are character offsets into the original text.
    ``redacted`` is the replacement token written into the redacted text
    (e.g. ``[PHONE]``), ensuring no PII reaches an unrestricted LLM.
    """

    start: int
    end: int
    text: str
    type: PIIType
    redacted: str


@dataclass(slots=True, frozen=True)
class GeoCandidate:
    """A geolocation candidate extracted from free text.

    For vague reports (``type=distribution`` or ``uncertainty_polygon``),
    ``candidates`` is empty and ``uncertainty_m`` is large — the downstream
    reasoning engine must NOT treat this as an exact point. ``place_names``
    holds the raw extracted place tokens for downstream gazetteer resolution.

    ``polygon`` is a list of (lat, lng) vertices for the
    ``uncertainty_polygon`` type; ``None`` for other types.
    """

    type: GeoType
    place_names: list[str]
    candidates: list[tuple[float, float]] = field(default_factory=list)
    uncertainty_m: float = 0.0
    polygon: list[tuple[float, float]] | None = None
    confidence: float = 0.0


@dataclass(slots=True, frozen=True)
class ProcessedReport:
    """The fully processed output of ``CitizenReportProcessor.process_report``.

    ``redacted_text`` is what would be sent to an LLM (PII removed).
    ``needs_human_review`` is True when the report is operationally
    consequential (critical urgency, low credibility, or ambiguous category).
    ``duplicate_group_id`` is set by ``_cluster_duplicates`` after batch
    processing — ``None`` until clustering runs.
    """

    report_id: str
    org_id: str
    created_at: int
    language: str
    original_text: str
    redacted_text: str
    transcription: str | None
    pii_spans: list[PIISpan]
    urgency: Urgency
    category: Category
    geolocation: GeoCandidate
    credibility: float
    image_corroboration: bool
    needs_human_review: bool
    duplicate_group_id: str | None = None


__all__ = [
    "Category",
    "GeoCandidate",
    "GeoType",
    "PIISpan",
    "PIIType",
    "ProcessedReport",
    "Urgency",
]
