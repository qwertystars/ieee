"""Situation report schemas (DESIGN §5 / §8)."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class SituationReportRequest(BaseModel):
    format: Literal["text", "pdf"] = "text"
    include_recommendations: bool = True
    include_map: bool = False


class SituationReport(BaseModel):
    event_id: uuid.UUID | None = None
    format: Literal["text", "pdf"] = "text"
    generated_at: str | None = None
    content: str | None = None  # text body, or base64 for pdf
    filename: str | None = None
