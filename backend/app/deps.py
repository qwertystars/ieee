"""Shared FastAPI dependencies: DB session re-export and pagination params."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query

from app.db import get_db  # re-exported for convenience

__all__ = ["get_db", "Pagination", "pagination_params", "parse_bbox", "BBox"]


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination_params(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


@dataclass
class BBox:
    minx: float
    miny: float
    maxx: float
    maxy: float


def parse_bbox(
    bbox: str | None = Query(None, description="minx,miny,maxx,maxy in EPSG:4326"),
) -> BBox | None:
    """Parse a `?bbox=minx,miny,maxx,maxy` query string into a BBox, or None."""
    if not bbox:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        return None
    try:
        minx, miny, maxx, maxy = (float(p) for p in parts)
    except ValueError:
        return None
    return BBox(minx=minx, miny=miny, maxx=maxx, maxy=maxy)
