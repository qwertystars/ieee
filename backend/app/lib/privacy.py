"""Progressive precision access control — data minimization serializer.

Same entity serialized differently based on viewer's role + task assignment.
Exact personal locations are exposed only when operationally necessary.

Precision levels (ward -> shelter -> dispatcher -> rescue team -> auditor):
  PUBLIC           — ward-level aggregation, NO exact coordinates, NO PII
  SHELTER_OPERATOR — shelter + assigned-person info (name, phone)
  DISPATCHER       — task-relevant approximate (~100m) or exact location
  RESCUE_TEAM      — exact rescue location (only for assigned tasks)
  AUDITOR          — controlled access to decision history + audit trail

This module controls how entities are SERIALIZED for different viewers.
Storage-level data minimization (separate tables for public vs. internal
data) is the responsibility of the schema layer — exact personal locations
must NOT be stored in public-facing tables.
"""

from collections.abc import Mapping
from enum import Enum

# PII fields — stripped unless the level explicitly grants visibility.
PII_FIELDS: frozenset[str] = frozenset(
    {"name", "phone", "email", "address", "contact", "dob", "ssn", "medical_info"}
)

# Audit-only fields — visible only to AUDITOR level.
AUDIT_ONLY_FIELDS: frozenset[str] = frozenset(
    {"decision_history", "audit_trail", "internal_notes", "prev_hash", "hash", "raw_data_hash"}
)

# Public-safe fields — whitelist for PUBLIC level.
PUBLIC_WHITELIST: frozenset[str] = frozenset(
    {"id", "type", "ward", "severity", "status", "shelter_id", "centroid", "count"}
)

# Coordinate decimal places per level.
# 3 decimals ~ 111m, 4 decimals ~ 11m. None = exact (no rounding).
COORD_DECIMALS: dict[str, int | None] = {
    "public": None,
    "shelter_operator": 4,
    "dispatcher": 3,
    "rescue_team": None,
    "auditor": None,
}

# PII fields visible per level (subset of PII_FIELDS).
_PII_VISIBLE: dict[str, frozenset[str]] = {
    "public": frozenset(),
    "shelter_operator": frozenset({"name", "phone"}),
    "dispatcher": frozenset(),
    "rescue_team": frozenset({"name", "medical_info"}),
    "auditor": frozenset(PII_FIELDS),
}


class PrecisionLevel(str, Enum):
    """Progressive precision levels — ward -> shelter -> dispatcher -> rescue -> auditor."""

    PUBLIC = "public"
    SHELTER_OPERATOR = "shelter_operator"
    DISPATCHER = "dispatcher"
    RESCUE_TEAM = "rescue_team"
    AUDITOR = "auditor"


# Role -> default precision level. Unknown roles default to PUBLIC.
_ROLE_PRECISION: dict[str, PrecisionLevel] = {
    "viewer": PrecisionLevel.PUBLIC,
    "shelter_manager": PrecisionLevel.SHELTER_OPERATOR,
    "responder_coordinator": PrecisionLevel.DISPATCHER,
    "emergency_manager": PrecisionLevel.DISPATCHER,
    "field_responder": PrecisionLevel.DISPATCHER,
    "admin": PrecisionLevel.AUDITOR,
}


def _to_dict(obj: object) -> dict:
    """Best-effort conversion of obj to a plain dict."""
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    if isinstance(obj, Mapping):
        return dict(obj)
    return {}


def _reduce_location(location: object, decimals: int | None) -> object:
    """Round coordinates to `decimals` places. None = exact (return as-is)."""
    if decimals is None:
        return location
    if isinstance(location, Mapping):
        out = dict(location)
        for key in ("lat", "lon", "latitude", "longitude"):
            if key in out and isinstance(out[key], (int, float)):
                out[key] = round(float(out[key]), decimals)
        return out
    if isinstance(location, (list, tuple)) and len(location) >= 2:
        coords = [round(float(location[0]), decimals), round(float(location[1]), decimals)]
        coords.extend(location[2:])
        return coords
    return location


class ProgressivePrecision:
    """Progressive precision serializer — same entity, different views by role.

    Maps viewer's role to a precision level and serializes the entity
    accordingly. A field_responder assigned to a task gets RESCUE_TEAM
    precision for entities on that task; otherwise DISPATCHER.
    """

    def __init__(self, ward_centroids: Mapping[str, tuple[float, float]] | None = None) -> None:
        self._ward_centroids: dict[str, tuple[float, float]] = dict(ward_centroids or {})

    def serialize(
        self,
        entity: object,
        viewer_role: str,
        task_assignment: str | None = None,
    ) -> dict:
        """Serialize entity based on viewer's role and optional task assignment."""
        data = _to_dict(entity)
        level = self._resolve_level(viewer_role, data, task_assignment)
        return self._serialize_at_level(data, level, task_assignment)

    @staticmethod
    def _resolve_level(
        viewer_role: str,
        data: dict,
        task_assignment: str | None,
    ) -> PrecisionLevel:
        """Map viewer role + task assignment to a precision level."""
        if viewer_role == "field_responder":
            if task_assignment is not None and data.get("task_id") == task_assignment:
                return PrecisionLevel.RESCUE_TEAM
            return PrecisionLevel.DISPATCHER
        return _ROLE_PRECISION.get(viewer_role, PrecisionLevel.PUBLIC)

    def _serialize_at_level(
        self,
        data: dict,
        level: PrecisionLevel,
        task_assignment: str | None,
    ) -> dict:
        """Dispatch to the appropriate view serializer for the level."""
        if level == PrecisionLevel.PUBLIC:
            return self._public_view(data)
        if level == PrecisionLevel.AUDITOR:
            return self._auditor_view(data)
        return self._operational_view(data, level, task_assignment)

    def _public_view(self, data: dict) -> dict:
        """Ward-level aggregation — no PII, no exact coordinates."""
        out: dict = {k: v for k, v in data.items() if k in PUBLIC_WHITELIST}
        ward = data.get("ward")
        if ward and ward in self._ward_centroids:
            lat, lon = self._ward_centroids[ward]
            out["centroid"] = {"lat": lat, "lon": lon}
        out.pop("location", None)
        return out

    @staticmethod
    def _auditor_view(data: dict) -> dict:
        """Controlled access to decision history — exact locations + audit fields."""
        return dict(data)

    @staticmethod
    def _operational_view(
        data: dict,
        level: PrecisionLevel,
        task_assignment: str | None,
    ) -> dict:
        """Shelter operator / dispatcher / rescue team views."""
        is_rescue = level == PrecisionLevel.RESCUE_TEAM
        task_match = (
            task_assignment is not None and data.get("task_id") == task_assignment
        )
        pii_visible = _PII_VISIBLE[level.value]
        out: dict = {}
        for k, v in data.items():
            if k in AUDIT_ONLY_FIELDS:
                continue
            if k in PII_FIELDS and k not in pii_visible:
                continue
            if k == "location":
                if is_rescue or task_match:
                    out[k] = v
                else:
                    out[k] = _reduce_location(v, COORD_DECIMALS[level.value])
            else:
                out[k] = v
        return out


__all__ = [
    "AUDIT_ONLY_FIELDS",
    "COORD_DECIMALS",
    "PII_FIELDS",
    "PUBLIC_WHITELIST",
    "PrecisionLevel",
    "ProgressivePrecision",
]
