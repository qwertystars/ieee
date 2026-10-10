"""Observation schemas — Pydantic v2 response models."""

from pydantic import BaseModel, ConfigDict


class ObservationResponse(BaseModel):
    """Response schema for an observation (ORM-mapped)."""

    model_config = ConfigDict(from_attributes=True)

    observation_id: str
    event_type: str
    phenomenon: str
    value: float | None = None
    unit: str | None = None
    observed_at: int
    valid_from: int
    valid_until: int | None = None
    received_at: int
    source_id: str
    source_type: str
    org_id: str
    incident_id: str


__all__ = ["ObservationResponse"]
