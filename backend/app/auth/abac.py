"""Attribute-Based Access Control (ABAC) policy engine.

Beyond role-based access control, ABAC considers multiple attributes before
granting access:

1. User role (admin, emergency_manager, responder_coordinator, ...)
2. Incident assignment (is the user explicitly assigned to the incident?)
3. Jurisdiction (does the user's jurisdiction cover the subject's area?)
4. Data sensitivity (public, internal, sensitive)
5. Current operational task (is the user actively deployed on a task?)
6. Emergency override status (temporary elevated access during crisis)

The `can(actor, action, subject, context)` method evaluates all attributes
and returns True only if every applicable rule passes.

Emergency overrides grant temporary elevated access during crises. They are
logged to the hash-chained audit log on grant and revoke, and expire after
a configurable TTL (default 1 hour). An expired override is treated as if
it does not exist.
"""

from sqlalchemy.orm import Session

from app.auth.abac_types import (
    Actor,
    Clock,
    Context,
    EmergencyOverride,
    Subject,
)
from app.lib.audit import write_audit
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid

DEFAULT_OVERRIDE_TTL_SECONDS = 3600

ELEVATED_ROLES = frozenset({"admin", "emergency_manager"})
OVERRIDE_GRANTOR_ROLES = frozenset({"admin"})

ACTION_MIN_ROLES: dict[str, frozenset[str]] = {
    "read": frozenset({
        "admin", "emergency_manager", "responder_coordinator",
        "field_responder", "shelter_manager", "viewer",
    }),
    "write": frozenset({
        "admin", "emergency_manager", "responder_coordinator",
        "field_responder", "shelter_manager",
    }),
    "delete": frozenset({"admin", "emergency_manager"}),
    "approve": frozenset({"admin", "emergency_manager"}),
    "dispatch": frozenset({
        "admin", "emergency_manager", "responder_coordinator",
    }),
    "override": frozenset({"admin"}),
}


class ABACEngine:
    """Attribute-based access control policy engine.

    Emergency overrides are stored in-memory (per engine instance). In
    production, overrides should be persisted (e.g., in a DB table or KV
    store) for durability across restarts. The engine accepts an injectable
    clock for deterministic testing of override expiry.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self._overrides: dict[str, EmergencyOverride] = {}
        self._clock: Clock = clock or now_ms

    def can(
        self,
        actor: Actor,
        action: str,
        subject: Subject,
        context: Context,
    ) -> bool:
        """Evaluate whether actor can perform action on subject in context."""
        if action not in ACTION_MIN_ROLES:
            return False

        if actor.org_id != subject.org_id:
            return False
        if actor.org_id != context.current_org_id:
            return False

        override_active = self._is_override_active(actor)

        if not _check_jurisdiction(actor, subject, override_active):
            return False
        if not _check_incident(actor, subject, override_active):
            return False
        if not _check_action_role(actor, action, override_active):
            return False
        if not _check_sensitivity(actor, subject, override_active):
            return False
        return True

    def grant_emergency_override(
        self,
        db: Session,
        admin_actor: Actor,
        target_user_id: str,
        reason: str,
        ttl_seconds: int = DEFAULT_OVERRIDE_TTL_SECONDS,
    ) -> EmergencyOverride:
        """Grant temporary elevated access to target_user. Logs to audit."""
        if admin_actor.role not in OVERRIDE_GRANTOR_ROLES:
            raise PermissionError("only admin can grant emergency overrides")
        if not reason.strip():
            raise ValueError("reason is required for emergency override")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        now = self._clock()
        expires_at = now + ttl_seconds * 1000
        override = EmergencyOverride(
            granted_by=admin_actor.user_id,
            reason=reason,
            granted_at=now,
            expires_at=expires_at,
        )
        self._overrides[target_user_id] = override

        write_audit(
            db,
            org_id=admin_actor.org_id,
            incident_id="",
            actor=admin_actor.user_id,
            action="emergency_override_grant",
            entity=f"user:{target_user_id}",
            before=None,
            after={
                "override_id": generate_ulid(),
                "reason": reason,
                "granted_by": admin_actor.user_id,
                "granted_at": now,
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds,
            },
        )
        return override

    def revoke_emergency_override(
        self,
        db: Session,
        admin_actor: Actor,
        target_user_id: str,
    ) -> bool:
        """Revoke emergency override for target_user. Logs to audit."""
        if admin_actor.role not in OVERRIDE_GRANTOR_ROLES:
            raise PermissionError("only admin can revoke emergency overrides")

        removed = self._overrides.pop(target_user_id, None)
        write_audit(
            db,
            org_id=admin_actor.org_id,
            incident_id="",
            actor=admin_actor.user_id,
            action="emergency_override_revoke",
            entity=f"user:{target_user_id}",
            before=(
                {"reason": removed.reason, "expires_at": removed.expires_at}
                if removed is not None
                else None
            ),
            after=None,
        )
        return removed is not None

    def get_override(self, user_id: str) -> EmergencyOverride | None:
        """Return the active override for a user, or None if expired/absent."""
        ov = self._overrides.get(user_id)
        if ov is None:
            return None
        if self._clock() >= ov.expires_at:
            return None
        return ov

    def _is_override_active(self, actor: Actor) -> bool:
        """Check actor's embedded override and the engine's override store."""
        if actor.emergency_override is not None:
            if self._clock() < actor.emergency_override.expires_at:
                return True
        stored = self._overrides.get(actor.user_id)
        if stored is not None and self._clock() < stored.expires_at:
            return True
        return False


def _check_jurisdiction(
    actor: Actor, subject: Subject, override: bool,
) -> bool:
    if actor.role == "admin" or override:
        return True
    if actor.jurisdiction == "all":
        return True
    return actor.jurisdiction == subject.jurisdiction


def _check_incident(
    actor: Actor, subject: Subject, override: bool,
) -> bool:
    if actor.role in ELEVATED_ROLES or override:
        return True
    return subject.incident_id in actor.incident_assignments


def _check_action_role(
    actor: Actor, action: str, override: bool,
) -> bool:
    if override:
        return True
    return actor.role in ACTION_MIN_ROLES.get(action, frozenset())


def _check_sensitivity(
    actor: Actor, subject: Subject, override: bool,
) -> bool:
    if subject.sensitivity != "sensitive":
        return True
    if actor.role in ELEVATED_ROLES or override:
        return True
    if subject.task_id is not None and actor.current_task == subject.task_id:
        return True
    return False


__all__ = ["DEFAULT_OVERRIDE_TTL_SECONDS", "ABACEngine"]
