"""Ingestion router stub (DESIGN §8). Owned by ingestion (Task #4).

Mounted at ``/api`` by main.py. Manual-trigger endpoint
``POST /events/{eventId}/ingest/{sourceType}`` is added by Task #4.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["ingestion"])
