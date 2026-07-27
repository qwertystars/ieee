"""ABAC data types — Actor, Subject, Context, Action, EmergencyOverride.

Frozen dataclasses with slots for memory efficiency and hashability. These
are value objects: they carry attributes the policy engine evaluates, never
behavior.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    """Actions that can be performed on a subject."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    APPROVE = "approve"
    DISPATCH = "dispatch"
    OVERRIDE = "override"


class Sensitivity(str, Enum):
    """Data sensitivity classification."""

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"


@dataclass(frozen=True, slots=True)
class EmergencyOverride:
    """Temporary elevated access granted by an admin during a crisis.

    Stored on the Actor and in the ABACEngine's override map. The engine
    checks `expires_at` against its injected clock before honoring the
    override.
    """

    granted_by: str
    reason: str
    granted_at: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class Actor:
    """The user attempting an action.

    `incident_assignments` is a tuple (hashable) of incident IDs the user
    is explicitly assigned to. `current_task` is the active task ID, if any.
    `emergency_override` is the per-actor override (may also be stored in
    the engine; the engine checks both).
    """

    user_id: str
    role: str
    org_id: str
    incident_assignments: tuple[str, ...] = ()
    jurisdiction: str = "all"
    current_task: str | None = None
    emergency_override: EmergencyOverride | None = None


@dataclass(frozen=True, slots=True)
class Subject:
    """The resource being acted upon.

    `type` is one of {observation, hypothesis, scenario, task, decision}.
    `task_id` is set only for task-typed subjects; it lets the sensitivity
    check match the actor's `current_task`.
    """

    type: str
    sensitivity: str
    org_id: str
    incident_id: str
    jurisdiction: str
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class Context:
    """The operational context in which the action is attempted.

    `emergency_mode` is a system-wide crisis flag. It does not bypass
    policy on its own — the per-user emergency override is the bypass
    mechanism. `emergency_mode` is metadata for audit and alerting.
    """

    current_org_id: str
    current_incident_id: str | None = None
    emergency_mode: bool = False


Clock = Callable[[], int]


__all__ = [
    "Action",
    "Actor",
    "Clock",
    "Context",
    "EmergencyOverride",
    "Sensitivity",
    "Subject",
]
