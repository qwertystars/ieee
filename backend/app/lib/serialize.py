"""Visibility serializer — whitelist fields by visibility + review_status.

Given an object (ORM model instance or dict), the viewer's visibility level,
and the object's review_status, return a dict containing only the fields the
viewer is allowed to see.

Rules:
- `sensitive` fields are hidden when the viewer's visibility is `public`.
- `draft` fields are hidden when review_status is `draft` and the viewer is
  not `internal` (i.e. visibility is `public` or `sensitive`).

`visibility` here is the viewer's clearance level, one of
{public, internal, sensitive}. `review_status` is the object's lifecycle state,
one of {draft, reviewed, official}.
"""

from collections.abc import Mapping

# Fields that carry operational risk if exposed publicly.
SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "internal_notes",
        "raw_data_hash",
        "provenance_chain",
        "source_reliability",
        "source_id",
        "contact_info",
    }
)

# Fields that are provisional until human review.
DRAFT_FIELDS: frozenset[str] = frozenset(
    {
        "quality_flags",
        "corroboration_state",
        "freshness",
        "confidence",
    }
)


def _to_dict(obj: object) -> dict:
    """Best-effort conversion of obj to a plain dict."""
    if isinstance(obj, dict):
        return dict(obj)
    # SQLAlchemy ORM instance: use __dict__ but skip SQLAlchemy internals.
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    # Fallback: try mapping protocol.
    if isinstance(obj, Mapping):
        return dict(obj)
    return {}


def serialize(
    obj: object,
    visibility: str,
    review_status: str,
) -> dict:
    """Serialize obj based on viewer visibility and object review_status.

    Args:
        obj: ORM model instance, dict, or mapping.
        visibility: viewer's clearance — "public", "internal", or "sensitive".
        review_status: object's state — "draft", "reviewed", or "official".

    Returns:
        A dict with disallowed fields stripped out.
    """
    data = _to_dict(obj)
    is_internal = visibility == "internal"
    is_sensitive_clearance = visibility == "sensitive"

    out: dict = {}
    for k, v in data.items():
        # Sensitive fields: only visible to internal or sensitive viewers.
        if k in SENSITIVE_FIELDS and not (is_internal or is_sensitive_clearance):
            continue
        # Draft fields: hidden from non-internal viewers when review_status is draft.
        if k in DRAFT_FIELDS and review_status == "draft" and not is_internal:
            continue
        out[k] = v
    return out


__all__ = ["DRAFT_FIELDS", "SENSITIVE_FIELDS", "serialize"]
