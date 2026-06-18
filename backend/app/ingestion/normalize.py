"""Normalization (DESIGN §6). Stub; Task #4 implements real mapping.

``normalize(source_type, raw_payload) -> list[NormalizedObsDict]``
where NormalizedObsDict is a plain dict matching NormalizedObservation fields.
"""
from __future__ import annotations

from typing import Any

NormalizedObsDict = dict[str, Any]


def normalize(source_type: str, raw_payload: dict[str, Any]) -> list[NormalizedObsDict]:
    """Map a raw payload to zero or more normalized observation dicts. Stub: []."""
    return []
