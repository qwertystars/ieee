from __future__ import annotations

import math
from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    ValidationError,
    field_validator,
)
from pydantic.types import JsonValue

from app.models.enums import AccessPolicy, CorroborationState, SourceType


class ObservationProperties(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_type: str = Field(min_length=1)
    phenomenon: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    value: StrictFloat | StrictInt | None = None
    observed_at: StrictInt | None = Field(default=None, ge=0)
    valid_from: StrictInt | None = Field(default=None, ge=0)
    valid_until: StrictInt | None = Field(default=None, ge=0)
    geometry_uncertainty: StrictFloat | StrictInt = Field(default=0, ge=0)
    source_type: SourceType = SourceType.other
    source_reliability: StrictFloat | StrictInt = Field(default=0.5, ge=0, le=1)
    freshness: StrictFloat | StrictInt = Field(default=1, ge=0)
    corroboration_state: CorroborationState = CorroborationState.uncorroborated
    model_uncertainty: StrictFloat | StrictInt | None = None
    quality_flags: dict[str, JsonValue] = Field(default_factory=dict)
    access_policy: AccessPolicy = AccessPolicy.internal
    provenance_chain: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("value", "geometry_uncertainty", "source_reliability", "freshness", "model_uncertainty")
    @classmethod
    def finite_numbers(cls, value: float | None) -> float | int | None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("finite numeric value required")
        return value


class ObservationFeature(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["Feature"]
    geometry: dict[str, JsonValue]
    properties: ObservationProperties

    @field_validator("geometry")
    @classmethod
    def valid_geometry(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        geometry_type = value.get("type")
        coordinates = value.get("coordinates")
        if not isinstance(geometry_type, str) or not geometry_type:
            raise ValueError("geometry type is required")
        if geometry_type != "GeometryCollection" and not _valid_coordinates(coordinates):
            raise ValueError("geometry coordinates are invalid")
        return value


def _valid_coordinates(value: JsonValue) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if not isinstance(value, list) or not value:
        return False
    return all(_valid_coordinates(item) for item in value)


def parse_feature(feature: dict[str, Any]) -> dict[str, Any]:
    try:
        return ObservationFeature.model_validate(feature).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid observation feature",
        ) from exc


def parse_feature_collection(body: dict[str, Any]) -> list[dict[str, Any]]:
    if body.get("type") != "FeatureCollection":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="GeoJSON FeatureCollection required",
        )
    features = body.get("features")
    if not isinstance(features, list) or not features:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="FeatureCollection must contain at least one feature",
        )
    return [parse_feature(feature) for feature in features]


__all__ = ["parse_feature", "parse_feature_collection"]
