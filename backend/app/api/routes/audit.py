"""audit routes stub (DESIGN §8). Feature workers fill endpoints here.

Exposes `router` aggregated by app/api/router.py and mounted under /api by main.py.
Do NOT edit main.py or api/router.py to add endpoints — add them to this router.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["audit"])
