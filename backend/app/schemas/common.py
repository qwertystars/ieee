"""Shared schema building blocks: ORM base config and GeoJSON geometry typing."""
from __future__ import annotations

from typing import Annotated, Optional, Union

from geojson_pydantic import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from pydantic import BaseModel, ConfigDict, Field

# A GeoJSON geometry object as exchanged by the API (DESIGN §3).
GeometryField = Annotated[
    Union[
        Point,
        MultiPoint,
        LineString,
        MultiLineString,
        Polygon,
        MultiPolygon,
        GeometryCollection,
    ],
    Field(description="GeoJSON geometry object (EPSG:4326)"),
]

OptionalGeometry = Optional[GeometryField]


class ORMBase(BaseModel):
    """Base for `XRead` schemas reading from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)


class PaginatedMeta(BaseModel):
    limit: int
    offset: int
    total: int | None = None
