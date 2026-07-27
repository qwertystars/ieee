"""Types, Pydantic schemas, and ORM models for LLM integration (T36).

Split from ``llm.py`` to keep both files under the 250 pure LOC ceiling.

Contents:
- Enums: ``ReviewStatus``, ``Provider``.
- ``ProviderConfig``: hierarchical config (org -> incident -> user).
- Pydantic output schemas for the 7 LLM use cases. Every schema carries
  ``review_status`` (always ``draft``) and every ``Claim`` MUST cite at
  least one observation ID — the validator rejects uncited claims
  (hallucination guard).
- ORM models: ``PromptRecord`` (prompt versioning) and ``AICallRecord``
  (call logging).
"""

from __future__ import annotations

import enum
import re

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import BigInteger, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.perception.nlp_patterns import (
    AADHAAR_RE,
    EMAIL_RE,
    NAME_RE,
    PHONE_RE,
)

# ─── Enums ───────────────────────────────────────────────────────────────────


class ReviewStatus(str, enum.Enum):
    """Lifecycle state of an LLM-generated artifact."""

    draft = "draft"
    reviewed = "reviewed"
    official = "official"


class Provider(str, enum.Enum):
    """LLM provider in the fallback chain: cloud -> local -> disabled."""

    cloud = "cloud"
    local = "local"
    disabled = "disabled"


# ─── Provider config ─────────────────────────────────────────────────────────


class ProviderConfig:
    """Hierarchical provider config resolved org -> incident -> user.

    ``base_url``/``api_key``/``model`` for an OpenAI-compatible endpoint.
    For Ollama (local), ``base_url`` is ``http://ollama:11434/v1`` and
    ``api_key`` is the dummy string ``"ollama"``.
    """

    __slots__ = ("api_key", "base_url", "model", "provider")

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        provider: Provider,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.provider = provider


# ─── Pydantic output schemas ─────────────────────────────────────────────────
# Every output carries review_status=draft. Claim requires non-empty
# observation_ids (citation requirement — hallucinations are rejected).


class Claim(BaseModel):
    """A single claim linked to source observation IDs (citations)."""

    text: str
    observation_ids: list[str] = Field(
        ..., description="Source observation IDs for this claim",
    )

    @field_validator("observation_ids")
    @classmethod
    def _must_have_citations(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("every claim must cite at least one observation ID")
        return v


class EvidenceSummary(BaseModel):
    """Retrieval-augmented evidence summary with source-traceable claims."""

    summary: str
    claims: list[Claim]
    review_status: str = ReviewStatus.draft.value


class ParsedReport(BaseModel):
    """Structured observation parsed from free-text report."""

    category: str
    urgency: str
    location_description: str
    key_facts: list[str]
    review_status: str = ReviewStatus.draft.value


class Translation(BaseModel):
    """Translated text with source language detected."""

    translated_text: str
    source_language: str
    target_language: str
    review_status: str = ReviewStatus.draft.value


class QueryAnswer(BaseModel):
    """Natural-language answer about incident state, with citations."""

    answer: str
    claims: list[Claim]
    review_status: str = ReviewStatus.draft.value


class BriefingDraft(BaseModel):
    """Incident briefing draft with sections, every claim cited."""

    title: str
    situation_overview: str
    key_developments: list[Claim]
    priorities: list[str]
    review_status: str = ReviewStatus.draft.value


class OptimizerExplanation(BaseModel):
    """Natural-language explanation of an optimizer output."""

    explanation: str
    constraints_respected: list[str]
    tradeoffs: list[str]
    review_status: str = ReviewStatus.draft.value


class ProcedureMatch(BaseModel):
    """Retrieved operating procedure relevant to a query."""

    procedure_id: str
    title: str
    relevance_reason: str
    summary: str
    review_status: str = ReviewStatus.draft.value


# ─── ORM models ──────────────────────────────────────────────────────────────


class PromptRecord(Base):
    """Prompt template with versioning (``prompts`` table)."""

    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String)
    template: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(BigInteger)


class AICallRecord(Base):
    """Audit log for every LLM call (``ai_calls`` table)."""

    __tablename__ = "ai_calls"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    org_id: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str] = mapped_column(String, index=True, nullable=True)
    prompt_name: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String)
    tokens_in: Mapped[int] = mapped_column(Integer)
    tokens_out: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    cost: Mapped[float] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String)
    created_at: Mapped[int] = mapped_column(BigInteger)


def make_call_record(
    org_id: str,
    incident_id: str | None,
    prompt_name: str,
    prompt_version: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    cost: float,
    provider: str,
) -> AICallRecord:
    """Build an ``AICallRecord`` with ULID id and current timestamp."""
    return AICallRecord(
        id=generate_ulid(),
        org_id=org_id,
        incident_id=incident_id or "",
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cost=cost,
        provider=provider,
        created_at=now_ms(),
    )


# ─── Default prompt templates ────────────────────────────────────────────────
# Stored in the ``prompts`` table on first use; versioned via PROMPT_VERSION.

PROMPT_VERSION = "1.0.0"

PII_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (PHONE_RE, "[PHONE]"),
    (EMAIL_RE, "[EMAIL]"),
    (AADHAAR_RE, "[AADHAAR]"),
    (NAME_RE, "[NAME]"),
]

DEFAULT_PROMPTS: dict[str, str] = {
    "parse_report": (
        "Extract a structured observation from the report. "
        "Output JSON with keys: category, urgency, location_description, key_facts. "
        "Do NOT invent missing values or convert uncertain locations to exact "
        "coordinates. Report:\n{input}"
    ),
    "summarize_evidence": (
        "Summarize the evidence. Every claim MUST include observation_ids "
        "citing the source observations. Output JSON with keys: summary, claims "
        "(each claim has text and observation_ids). Evidence:\n{input}"
    ),
    "translate": (
        "Translate the text to the target language. "
        "Output JSON with keys: translated_text, source_language, target_language. "
        "Text:\n{input}"
    ),
    "answer_query": (
        "Answer the query about the incident state. Every claim MUST include "
        "observation_ids. Output JSON with keys: answer, claims. "
        "Query and context:\n{input}"
    ),
    "generate_briefing": (
        "Generate an incident briefing. Every key_development MUST include "
        "observation_ids. Output JSON with keys: title, situation_overview, "
        "key_developments (each with text and observation_ids), priorities. "
        "Observations:\n{input}"
    ),
    "explain_optimizer": (
        "Explain the optimizer output. Output JSON with keys: explanation, "
        "constraints_respected, tradeoffs. Do NOT bypass optimization "
        "constraints. Optimizer result:\n{input}"
    ),
    "retrieve_procedure": (
        "Retrieve the most relevant operating procedure. Output JSON with "
        "keys: procedure_id, title, relevance_reason, summary. "
        "Query:\n{input}"
    ),
}


__all__ = [
    "DEFAULT_PROMPTS",
    "PII_REPLACEMENTS",
    "PROMPT_VERSION",
    "AICallRecord",
    "BriefingDraft",
    "Claim",
    "EvidenceSummary",
    "OptimizerExplanation",
    "ParsedReport",
    "ProcedureMatch",
    "PromptRecord",
    "Provider",
    "ProviderConfig",
    "QueryAnswer",
    "ReviewStatus",
    "Translation",
    "make_call_record",
]
