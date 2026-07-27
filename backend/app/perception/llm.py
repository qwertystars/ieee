"""LLM integration for evidence summarization and incident reasoning (T36).

Offline LLM strategy (Metis GAP 15): fallback chain cloud -> local
(Ollama llama3.1:8b) -> disabled. PII redaction before LLM call, prompt
injection defense (fenced untrusted data), Pydantic validation with 1
retry, citation requirement on every claim, all outputs review_status=draft.
Prompt versioning (``prompts`` table), call logging (``ai_calls`` table).
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.perception.llm_types import (
    DEFAULT_PROMPTS,
    PII_REPLACEMENTS,
    PROMPT_VERSION,
    BriefingDraft,
    EvidenceSummary,
    OptimizerExplanation,
    ParsedReport,
    ProcedureMatch,
    PromptRecord,
    Provider,
    ProviderConfig,
    QueryAnswer,
    Translation,
    make_call_record,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)

_DEFAULT_LOCAL = ProviderConfig(
    base_url="http://ollama:11434/v1",
    api_key="ollama",
    model="llama3.1:8b",
    provider=Provider.local,
)

_UNTRUSTED_OPEN = "<UNTRUSTED_DATA>"
_UNTRUSTED_CLOSE = "</UNTRUSTED_DATA>"


class LLMIntegration:
    """LLM integration with provider fallback chain and citation enforcement.

    Provider chain: cloud (OpenAI-compatible) -> local (Ollama) -> disabled.
    ``client`` is injectable for testing (duck typing — any object with
    ``chat.completions.create()`` works).
    """

    def __init__(
        self,
        org_id: str,
        incident_id: str | None = None,
        user_id: str | None = None,
        cloud_config: ProviderConfig | None = None,
        local_config: ProviderConfig | None = None,
        client: object | None = None,
        db_session: Session | None = None,
    ) -> None:
        self._org_id = org_id
        self._incident_id = incident_id
        self._user_id = user_id
        self._cloud = cloud_config
        self._local = local_config or _DEFAULT_LOCAL
        self._client = client
        self._db = db_session
        self._prompts_cache: dict[str, str] = {}

    def _resolve_provider(self) -> tuple[ProviderConfig, Any]:
        """Resolve provider config: cloud -> local -> disabled."""
        for cfg in (self._cloud, self._local):
            if cfg is None:
                continue
            client = self._get_client(cfg)
            if client is not None:
                return cfg, client
        raise RuntimeError("all LLM providers unavailable (disabled)")

    def _get_client(self, cfg: ProviderConfig) -> object | None:
        """Get or create an OpenAI-compatible client for the config."""
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("openai package not installed")
            return None
        try:
            return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
        except Exception:
            logger.warning("failed to create client for %s", cfg.provider)
            return None

    @staticmethod
    def _redact_pii(text: str) -> str:
        """Redact PII (phone, email, Aadhaar, names) before LLM call."""
        spans: list[tuple[int, int, str]] = []
        for regex, token in PII_REPLACEMENTS:
            for m in regex.finditer(text):
                spans.append((m.start(), m.end(), token))
        spans.sort(key=lambda s: s[0], reverse=True)
        chars = list(text)
        for start, end, token in spans:
            chars[start:end] = list(token)
        return "".join(chars)

    @staticmethod
    def _fence_untrusted(untrusted: str) -> str:
        """Fence untrusted data in delimited blocks for injection defense."""
        return f"{_UNTRUSTED_OPEN}\n{untrusted}\n{_UNTRUSTED_CLOSE}"

    def _run(
        self,
        prompt_name: str,
        schema: type[_T],
        untrusted_data: str,
        system_prompt: str = "",
    ) -> _T:
        """Run an LLM call: redact PII, fence untrusted data, validate output.

        Returns a Pydantic-validated output with ``review_status=draft``.
        Retries once on parse failure with a "output valid JSON" instruction.
        Logs every call to the ``ai_calls`` table.
        """
        redacted = self._redact_pii(untrusted_data)
        fenced = self._fence_untrusted(redacted)
        prompt_template = self._get_prompt(prompt_name)
        full_prompt = prompt_template.replace("{input}", fenced)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt},
        ]

        cfg, client = self._resolve_provider()
        start = time.monotonic()
        content = client.chat.completions.create(
            model=cfg.model, messages=messages, temperature=0.1,
        ).choices[0].message.content
        latency_ms = int((time.monotonic() - start) * 1000)

        try:
            result = schema.model_validate(json.loads(content))
        except (ValidationError, json.JSONDecodeError):
            logger.warning("parse failed for %s, retrying", prompt_name)
            retry_msg = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": "Output valid JSON only, no prose."},
            ]
            content = client.chat.completions.create(
                model=cfg.model, messages=retry_msg, temperature=0.1,
            ).choices[0].message.content
            result = schema.model_validate(json.loads(content))

        self._log_call(
            prompt_name, PROMPT_VERSION,
            len(redacted), len(content), latency_ms, cfg.provider,
        )
        return result

    def _get_prompt(self, name: str) -> str:
        """Get prompt template by name (from cache, DB, or built-in default)."""
        if name in self._prompts_cache:
            return self._prompts_cache[name]
        template = self._load_prompt_from_db(name) or DEFAULT_PROMPTS.get(name, "")
        self._prompts_cache[name] = template
        return template

    def _load_prompt_from_db(self, name: str) -> str | None:
        """Load the latest prompt template from the ``prompts`` table."""
        if self._db is None:
            return None
        from sqlalchemy import select
        stmt = (
            select(PromptRecord)
            .where(PromptRecord.name == name)
            .order_by(PromptRecord.created_at.desc())
            .limit(1)
        )
        record = self._db.execute(stmt).scalar_one_or_none()
        return record.template if record is not None else None

    def _log_call(
        self,
        prompt_name: str,
        prompt_version: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        provider: Provider,
    ) -> None:
        """Log the LLM call to the ``ai_calls`` table."""
        if self._db is None:
            return
        record = make_call_record(
            org_id=self._org_id,
            incident_id=self._incident_id,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost=0.0,
            provider=provider.value,
        )
        self._db.add(record)
        self._db.commit()

    # ── 7 use cases ────────────────────────────────────────────────────

    def parse_report(self, text: str) -> ParsedReport:
        """(1) Parse free-text report into structured observation."""
        return self._run(
            "parse_report", ParsedReport, text,
            system_prompt="Extract structured observation from the report.",
        )

    def summarize_evidence(self, observations: list[dict[str, Any]]) -> EvidenceSummary:
        """(2) Summarize evidence across heterogeneous streams (cited)."""
        return self._run(
            "summarize_evidence", EvidenceSummary, json.dumps(observations, default=str),
            system_prompt="Summarize evidence with citations to observation IDs.",
        )

    def translate(self, text: str, target_language: str) -> Translation:
        """(3) Translate text to the target language."""
        return self._run(
            "translate", Translation,
            f"Target language: {target_language}\nText: {text}",
            system_prompt="Translate the text to the target language.",
        )

    def answer_query(self, query: str, incident_context: str) -> QueryAnswer:
        """(4) Answer a natural-language query about incident state."""
        return self._run(
            "answer_query", QueryAnswer,
            f"Query: {query}\nContext: {incident_context}",
            system_prompt="Answer the query with cited observations.",
        )

    def generate_briefing(self, observations: list[dict[str, Any]]) -> BriefingDraft:
        """(5) Generate an incident briefing draft from observations."""
        return self._run(
            "generate_briefing", BriefingDraft, json.dumps(observations, default=str),
            system_prompt="Generate a briefing with cited key developments.",
        )

    def explain_optimizer_output(self, optimizer_result: dict[str, Any]) -> OptimizerExplanation:
        """(6) Explain optimizer output in natural language."""
        return self._run(
            "explain_optimizer", OptimizerExplanation,
            json.dumps(optimizer_result, default=str),
            system_prompt="Explain the optimizer output in plain language.",
        )

    def retrieve_procedure(self, query: str) -> ProcedureMatch:
        """(7) Retrieve applicable operating procedures for a query."""
        return self._run(
            "retrieve_procedure", ProcedureMatch, query,
            system_prompt="Retrieve the most relevant operating procedure.",
        )


__all__ = ["LLMIntegration"]
