"""DataSource and RawIngestedRecord schemas (DESIGN §5)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import DataSourceType, ProcessingStatus
from app.schemas.common import ORMBase


class DataSourceBase(BaseModel):
    name: str
    type: DataSourceType
    provider: str | None = None
    refresh_interval_s: int = 300
    status: str = "active"
    config: dict | None = None


class DataSourceCreate(DataSourceBase):
    pass


class DataSourceUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    refresh_interval_s: int | None = None
    status: str | None = None
    config: dict | None = None
    last_error: str | None = None


class DataSourceRead(ORMBase):
    id: uuid.UUID
    name: str
    type: DataSourceType
    provider: str | None = None
    refresh_interval_s: int
    last_success_at: datetime | None = None
    last_error: str | None = None
    status: str
    config: dict | None = None
    created_at: datetime
    updated_at: datetime


class RawIngestedRecordRead(ORMBase):
    id: uuid.UUID
    source_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    raw_payload: dict | None = None
    received_at: datetime
    processing_status: ProcessingStatus
    error_message: str | None = None
