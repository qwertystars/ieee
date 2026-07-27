"""Citizen-report NLP pipeline (T21).

Pipeline: speech/text -> language ID -> ASR -> PII redaction -> urgency +
category -> place-name -> geolocation candidate -> duplicate clustering ->
credibility -> human review.

PII is redacted BEFORE any LLM call. Geolocation candidates are NEVER exact
points for vague reports. Whisper is lazy-imported (NOT in requirements.txt
— see learnings notepad). Clustering delegates to ``DuplicateClusterer``.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.perception.nlp_clustering import DuplicateClusterer
from app.perception.nlp_patterns import (
    AADHAAR_RE,
    CATEGORY_KEYWORDS,
    COORD_RE,
    EMAIL_RE,
    NAME_RE,
    PHONE_RE,
    PLACE_PATTERN_RE,
    PLACE_SUFFIXES,
    URGENCY_KEYWORDS,
    VAGUE_QUALIFIERS,
)
from app.perception.nlp_types import (
    Category,
    GeoCandidate,
    GeoType,
    PIISpan,
    PIIType,
    ProcessedReport,
    Urgency,
)


def _keyword_match(keyword: str, text: str) -> bool:
    """Match keyword using ASCII-only word boundaries (``\\b`` breaks on
    Devanagari combining marks like ं and े)."""
    pattern = (
        r"(?<![a-zA-Z0-9])"
        + re.escape(keyword.lower())
        + r"(?![a-zA-Z0-9])"
    )
    return re.search(pattern, text) is not None


class CitizenReportProcessor:
    """Multilingual NLP pipeline. ``asr_fn`` and ``embed_fn`` are injectable."""

    def __init__(
        self,
        org_id: str = "org_default",
        asr_fn: Callable[[bytes], str] | None = None,
        embed_fn: Callable[[str], list[float]] | None = None,
        duplicate_threshold: float = 0.85,
    ) -> None:
        self._org_id = org_id
        self._asr_fn = asr_fn
        self._clusterer = DuplicateClusterer(
            embed_fn=embed_fn, threshold=duplicate_threshold,
        )

    # ── Public API ──────────────────────────────────────────────────────

    def process_report(
        self,
        text: str | None,
        audio: bytes | None = None,
        image: bytes | None = None,
    ) -> ProcessedReport:
        """Process a single report end-to-end. Exactly one of text/audio."""
        if text is None and audio is None:
            raise ValueError("either text or audio must be provided")

        transcription: str | None = None
        working_text = text or ""
        if audio is not None:
            transcription = self._transcribe_audio(audio)
            working_text = transcription

        language = self._identify_language(working_text)
        pii_spans = self._detect_pii(working_text)
        redacted = self._redact_pii(working_text, pii_spans)
        urgency = self._extract_urgency(redacted)
        category = self._extract_category(redacted)
        geolocation = self._extract_geolocation(redacted)
        credibility = self._estimate_credibility(
            redacted, has_image=image is not None, urgency=urgency,
        )
        needs_review = self._needs_human_review(urgency, credibility, category)

        return ProcessedReport(
            report_id=generate_ulid(),
            org_id=self._org_id,
            created_at=now_ms(),
            language=language,
            original_text=working_text,
            redacted_text=redacted,
            transcription=transcription,
            pii_spans=pii_spans,
            urgency=urgency,
            category=category,
            geolocation=geolocation,
            credibility=credibility,
            image_corroboration=image is not None,
            needs_human_review=needs_review,
        )

    def cluster_duplicates(
        self,
        reports: list[ProcessedReport],
        threshold: float | None = None,
    ) -> list[list[str]]:
        """Cluster near-duplicate reports by embedding similarity."""
        return self._clusterer.cluster(reports, threshold)

    # ── Pipeline stages ──────────────────────────────────────────────────

    def _identify_language(self, text: str) -> str:
        """``en``, ``hi``, or ``code-mixed`` (Devanagari U+0900–U+097F)."""
        devanagari = sum(1 for c in text if "\u0900" <= c <= "\u097f")
        latin = sum(1 for c in text if "a" <= c.lower() <= "z")
        if devanagari > 0 and latin > devanagari:
            return "code-mixed"
        if devanagari > 0:
            return "hi"
        return "en"

    def _transcribe_audio(self, audio: bytes) -> str:
        """Whisper ASR (lazy-imported). Mockable via ``asr_fn``."""
        if self._asr_fn is not None:
            return self._asr_fn(audio)
        try:
            import whisper  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "whisper is not installed; install openai-whisper or "
                "inject asr_fn for testing",
            ) from exc
        model = whisper.load_model("base")
        result = model.transcribe(audio)
        return str(result.get("text", ""))

    def _detect_pii(self, text: str) -> list[PIISpan]:
        """Detect PII via regex: phone, email, Aadhaar, person names."""
        spans: list[PIISpan] = []
        for regex, pii_type, token in (
            (PHONE_RE, PIIType.phone, "[PHONE]"),
            (EMAIL_RE, PIIType.email, "[EMAIL]"),
            (AADHAAR_RE, PIIType.aadhaar, "[AADHAAR]"),
        ):
            for m in regex.finditer(text):
                spans.append(PIISpan(
                    start=m.start(), end=m.end(), text=m.group(),
                    type=pii_type, redacted=token,
                ))
        for m in NAME_RE.finditer(text):
            spans.append(PIISpan(
                start=m.start(), end=m.end(), text=m.group(),
                type=PIIType.person_name, redacted="[NAME]",
            ))
        return sorted(spans, key=lambda s: s.start)

    def _redact_pii(self, text: str, pii_spans: list[PIISpan]) -> str:
        """Replace PII spans with redaction tokens (right-to-left)."""
        chars = list(text)
        for span in sorted(pii_spans, key=lambda s: s.start, reverse=True):
            chars[span.start:span.end] = list(span.redacted)
        return "".join(chars)

    def _extract_urgency(self, text: str) -> Urgency:
        """Keyword match: critical > high > medium > low (word-boundary)."""
        lowered = text.lower()
        for urgency in (Urgency.critical, Urgency.high, Urgency.medium, Urgency.low):
            for kw in URGENCY_KEYWORDS[urgency.value]:
                if _keyword_match(kw, lowered):
                    return urgency
        return Urgency.medium

    def _extract_category(self, text: str) -> Category:
        """Humanitarian category by keyword hit count (word-boundary match)."""
        lowered = text.lower()
        best, best_hits = Category.irrelevant, 0
        for cat, keywords in CATEGORY_KEYWORDS.items():
            hits = sum(1 for kw in keywords if _keyword_match(kw, lowered))
            if hits > best_hits:
                best, best_hits = Category(cat), hits
        return best

    def _extract_geolocation(self, text: str) -> GeoCandidate:
        """Build a geolocation candidate. NEVER invents exact GPS from vague
        text. Exact only when ``lat,lng`` appears explicitly; vague qualifiers
        yield ``uncertainty_polygon``; named places with suffixes yield
        ``named_place``; multiple names yield ``distribution``."""
        coord_match = COORD_RE.search(text)
        if coord_match:
            lat = float(coord_match.group(1))
            lng = float(coord_match.group(2))
            return GeoCandidate(
                type=GeoType.exact, place_names=[],
                candidates=[(lat, lng)], uncertainty_m=10.0, confidence=0.95,
            )

        place_names = self._extract_place_names(text)
        has_vague = any(q in text.lower() for q in VAGUE_QUALIFIERS)
        has_suffix = any(
            any(s in name.lower() for s in PLACE_SUFFIXES)
            for name in place_names
        )

        if not place_names:
            return GeoCandidate(GeoType.uncertainty_polygon, [],
                [], 5000.0, [], 0.1)
        if has_vague:
            return GeoCandidate(GeoType.uncertainty_polygon, place_names,
                [], 2000.0, [], 0.3)
        if has_suffix:
            return GeoCandidate(GeoType.named_place, place_names,
                [], 500.0, None, 0.6)
        if len(place_names) > 1:
            return GeoCandidate(GeoType.distribution, place_names,
                [], 1000.0, None, 0.4)
        return GeoCandidate(GeoType.named_place, place_names,
            [], 800.0, None, 0.5)

    def _estimate_credibility(
        self, text: str, has_image: bool, urgency: Urgency,
    ) -> float:
        """Heuristic [0,1] feeding the M dimension of the confidence vector."""
        score = 0.3
        if len(text) > 100:
            score += 0.1
        if any(c.isdigit() for c in text):
            score += 0.1
        if COORD_RE.search(text):
            score += 0.2
        if has_image:
            score += 0.2
        if urgency == Urgency.critical and not has_image:
            score -= 0.1
        return max(0.0, min(1.0, score))

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _needs_human_review(
        urgency: Urgency, credibility: float, category: Category,
    ) -> bool:
        """True when operationally consequential."""
        if urgency == Urgency.critical:
            return True
        if credibility < 0.4:
            return True
        return category == Category.irrelevant

    @staticmethod
    def _extract_place_names(text: str) -> list[str]:
        """Extract candidate place names via preposition patterns + suffixes."""
        names: list[str] = []
        for m in PLACE_PATTERN_RE.finditer(text):
            name = m.group(1).strip().rstrip(",.")
            if len(name) > 2:
                names.append(name)
        for suffix in PLACE_SUFFIXES:
            pattern = r"\b([A-Za-z][a-zA-Z]+\s+" + re.escape(suffix) + r")\b"
            for m in re.finditer(pattern, text, re.IGNORECASE):
                name = m.group(1).strip()
                if name not in names:
                    names.append(name)
        return names


__all__ = ["CitizenReportProcessor"]
