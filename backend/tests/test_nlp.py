"""Tests for the citizen-report NLP pipeline (T21).

Tests mock Whisper ASR (no real model required) and inject a deterministic
embedding function for duplicate clustering (no FAISS hash randomization).
The pipeline processes 5 mixed-language reports, extracts urgency +
category + geolocation candidates (distributions, not points), flags PII
for redaction before any LLM call, and clusters 2 duplicate reports.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from app.perception.nlp import CitizenReportProcessor
from app.perception.nlp_types import (
    Category,
    GeoType,
    PIIType,
    Urgency,
)

ORG_ID = "org_test_nlp"


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _mock_asr(audio: bytes) -> str:
    """Mock Whisper ASR — returns a fixed Hindi transcript."""
    return "बाढ़ का पानी बढ़ रहा है, लोग फंसे हुए हैं, जल्दी मदद करें"


def _deterministic_embed(text: str) -> list[float]:
    """Deterministic 64-dim bag-of-words embedding using hashlib (not hash())).
    Python's hash() is randomized per process (PYTHONHASHSEED), which makes
    the default hash-based embedder flaky across runs. This embedder uses
    hashlib.sha256 for deterministic hashing.
    """
    tokens = re.findall(r"[a-zà-ÿ\u0900-\u097f]{2,}", text.lower())
    vec = [0.0] * 64
    for token in tokens:
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % 64
        vec[h] += 1.0
    return vec


@pytest.fixture
def processor() -> CitizenReportProcessor:
    """Processor with mocked ASR and deterministic embedder."""
    return CitizenReportProcessor(
        org_id=ORG_ID,
        asr_fn=_mock_asr,
        embed_fn=_deterministic_embed,
    )


# ─── Test reports ───────────────────────────────────────────────────────────

# 5 reports: English, Hindi (Devanagari), code-mixed, and two near-duplicates.
_REPORTS = [
    # 1. English, critical urgency, trapped person.
    (
        "Help! People are trapped on the roof of Sharma Hospital near the old "
        "market. Water is rising fast. Call 9876543210."
    ),
    # 2. Hindi (Devanagari), high urgency, flooding.
    "बाढ़ का पानी तेजी से बढ़ रहा है। गांव में लोग परेशान हैं। जल्दी मदद भेजें।",
    # 3. Code-mixed (Devanagari + Latin), medium urgency, shelter.
    (
        "Need shelter in Gandhi Nagar colony, पानी ghar mein ghus gaya, "
        "family needs bhojan and medicine."
    ),
    # 4. Near-duplicate of report 1 (same incident, different wording).
    (
        "People trapped on roof of Sharma Hospital near old market, water "
        "rising, urgent rescue needed. Contact 9876543210."
    ),
    # 5. English, low urgency, rescue completed.
    (
        "All safe now near the railway station. Everyone was saved, minor "
        "flooding only. Everyone is fine."
    ),
]


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_processes_mixed_reports(processor: CitizenReportProcessor):
    """5 reports (English, Hindi, code-mixed) -> urgency + category extracted.

    Verifies language identification (en/hi/code-mixed), urgency extraction
    across all 4 levels, and category extraction for each report.
    """
    reports = [processor.process_report(text=t) for t in _REPORTS]

    assert len(reports) == 5
    # Language identification.
    assert reports[0].language == "en"
    assert reports[1].language == "hi"
    assert reports[2].language == "code-mixed"

    # Urgency extraction — covers critical, high, medium, low.
    assert reports[0].urgency == Urgency.critical  # "trapped"
    assert reports[1].urgency == Urgency.high      # "madad"/"jaldi"
    assert reports[2].urgency == Urgency.medium    # "need"
    assert reports[4].urgency == Urgency.low       # "safe"/"fine"

    # Category extraction.
    assert reports[0].category == Category.trapped_person
    assert reports[1].category == Category.flooding
    assert reports[4].category == Category.rescue_completed

    # Every report has a non-empty redacted text and a geolocation candidate.
    for r in reports:
        assert len(r.redacted_text) > 0
        assert r.geolocation is not None
        assert r.report_id  # ULID
        assert r.org_id == ORG_ID


def test_vague_geolocation(processor: CitizenReportProcessor):
    """'near the old market' -> uncertainty_polygon, NOT exact point.

    A vague report must NEVER produce an exact GPS coordinate. The candidate
    list must be empty and the type must be ``uncertainty_polygon`` or
    ``distribution``.
    """
    report = processor.process_report(
        text="Stranded near the old market, water everywhere, need help."
    )
    geo = report.geolocation

    assert geo.type in (GeoType.uncertainty_polygon, GeoType.distribution)
    # No exact coordinates invented from a vague reference.
    assert geo.candidates == []
    assert geo.uncertainty_m > 100.0  # large uncertainty
    assert "old market" in " ".join(geo.place_names).lower() or \
           "market" in " ".join(geo.place_names).lower()
    assert geo.confidence < 0.7  # low confidence for vague location


def test_exact_geolocation_when_coordinates_present(
    processor: CitizenReportProcessor,
):
    """When explicit lat,lng appears in text, ``exact`` type is returned.

    This confirms the geolocation logic CAN produce exact points — but only
    when the report contains an explicit coordinate, never from vague text.
    """
    report = processor.process_report(
        text="Flooding at coordinates 28.6139, 77.2090. People need rescue."
    )
    geo = report.geolocation
    assert geo.type == GeoType.exact
    assert len(geo.candidates) == 1
    lat, lng = geo.candidates[0]
    assert abs(lat - 28.6139) < 0.001
    assert abs(lng - 77.2090) < 0.001


def test_pii_redaction(processor: CitizenReportProcessor):
    """PII (phone, email, Aadhaar, person name) detected and redacted before
    the text reaches any downstream stage (urgency/category/geo extraction).

    The redacted text must NOT contain the original PII tokens.
    """
    text = (
        "Trapped near Gandhi Nagar. Call Ramesh Kumar at 9876543210 or "
        "email ramesh@example.com. Aadhaar 1234 5678 9012."
    )
    report = processor.process_report(text=text)

    # PII spans detected.
    pii_types = {s.type for s in report.pii_spans}
    assert PIIType.phone in pii_types
    assert PIIType.email in pii_types
    assert PIIType.aadhaar in pii_types

    # Original PII tokens must NOT appear in the redacted text.
    assert "9876543210" not in report.redacted_text
    assert "ramesh@example.com" not in report.redacted_text
    assert "1234 5678 9012" not in report.redacted_text
    assert "ramesh@example.com" not in report.redacted_text

    # Redaction tokens ARE present.
    assert "[PHONE]" in report.redacted_text
    assert "[EMAIL]" in report.redacted_text
    assert "[AADHAAR]" in report.redacted_text

    # The redacted text is what downstream stages used.
    assert "[PHONE]" in report.redacted_text


def test_duplicate_clustering(processor: CitizenReportProcessor):
    """Two near-duplicate reports (reports 0 and 3) cluster together.

    Uses the pure-Python cosine fallback (no FAISS required). The two
    duplicates must be in the same cluster; the other reports must not
    cluster with them.
    """
    reports = [processor.process_report(text=t) for t in _REPORTS]
    clusters = processor.cluster_duplicates(reports, threshold=0.7)

    # Find the cluster containing report 0.
    report_0_id = reports[0].report_id
    report_3_id = reports[3].report_id
    dup_cluster = None
    for cluster in clusters:
        if report_0_id in cluster:
            dup_cluster = cluster
            break

    assert dup_cluster is not None, "report 0 must be in a cluster"
    assert report_3_id in dup_cluster, (
        "report 3 (near-duplicate of report 0) must be in the same cluster"
    )
    # The duplicate cluster should have exactly these two (not all 5).
    assert len(dup_cluster) == 2


def test_urgency_extraction(processor: CitizenReportProcessor):
    """All 4 urgency levels correctly classified by keyword matching."""
    cases = [
        ("People are trapped and drowning, help immediately!", Urgency.critical),
        ("Urgent rescue needed, water is rising fast.", Urgency.high),
        ("Need food and water, stranded on roof.", Urgency.medium),
        ("Everyone is safe now, minor flooding only.", Urgency.low),
        ("बचाओ बचाओ, पानी आ रहा है", Urgency.high),  # Hindi "bachao"
    ]
    for text, expected in cases:
        report = processor.process_report(text=text)
        assert report.urgency == expected, (
            f"expected {expected.value} for '{text[:40]}...', "
            f"got {report.urgency.value}"
        )


def test_category_extraction(processor: CitizenReportProcessor):
    """Humanitarian categories correctly classified by keyword matching."""
    cases = [
        ("People trapped in their homes, need rescue", Category.trapped_person),
        ("My grandfather is missing since the flood", Category.missing_person),
        ("Injured person needs medical attention, bleeding", Category.medical_emergency),
        ("Flood water rising rapidly in our area", Category.flooding),
        ("Building collapsed, structure fell down", Category.structural_collapse),
        ("Fire broke out, smoke everywhere, electrical short", Category.fire_electrical),
        ("Main road is blocked, impassable due to debris", Category.blocked_route),
        ("Need shelter, looking for a roof over head", Category.shelter_request),
        ("Need food, water and medicine urgently", Category.food_water_medication),
        ("No power for 2 days, bijli gone", Category.infrastructure_outage),
        ("Rescued by boat team, everyone saved", Category.rescue_completed),
    ]
    for text, expected in cases:
        report = processor.process_report(text=text)
        assert report.category == expected, (
            f"expected {expected.value} for '{text[:40]}...', "
            f"got {report.category.value}"
        )


def test_audio_input_uses_asr(processor: CitizenReportProcessor):
    """Audio input triggers ASR; the transcription becomes the report text."""
    report = processor.process_report(text=None, audio=b"fake-audio-bytes")
    assert report.transcription is not None
    assert "फंसे" in report.transcription  # from _mock_asr
    assert report.original_text == report.transcription
    assert report.language == "hi"
    assert report.urgency == Urgency.critical  # "फंसे" is a critical keyword


def test_human_review_flagged_for_critical(processor: CitizenReportProcessor):
    """Critical-urgency reports are flagged for human review."""
    report = processor.process_report(
        text="People are trapped and drowning, help immediately!"
    )
    assert report.urgency == Urgency.critical
    assert report.needs_human_review is True


def test_no_text_no_audio_raises():
    """ValueError when neither text nor audio is provided."""
    processor = CitizenReportProcessor(
        org_id=ORG_ID, asr_fn=_mock_asr, embed_fn=_deterministic_embed,
    )
    with pytest.raises(ValueError, match="either text or audio"):
        processor.process_report(text=None, audio=None)
