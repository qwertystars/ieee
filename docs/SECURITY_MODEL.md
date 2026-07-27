# Security Model

The platform implements layered access control: JWT authentication, role-based
access control (RBAC) with 6 roles, attribute-based access control (ABAC) for
fine-grained policy, org-level tenancy, emergency override, and progressive
precision PII redaction.

## Authentication

### JWT-based auth

Authentication uses JSON Web Tokens (HS256). The login endpoint accepts
`username` and `password` as form-encoded fields and returns a JWT:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@demo.disaster&password=demo1234"
```

The JWT payload carries:

- `sub` — user ID (ULID)
- `email` — user email
- `role` — one of the 6 roles (see below)
- `org_id` — tenant ID (server-side, never client-supplied)
- `exp` — expiry (default 12 hours, configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)

### Password hashing

Passwords are hashed with bcrypt (direct, not passlib). The `bcrypt` package
is used directly because passlib 1.7.x is incompatible with bcrypt 4.x
(passlib's `detect_wrap_bug()` triggers bcrypt 4.x's strict 72-byte limit).

### Token revocation

When Redis is available, the token denylist checks revoked tokens on every
protected request. When Redis is down, the denylist fails open: revoked
tokens remain valid until their natural expiry. This is a deliberate
trade-off for availability over security in degraded conditions.

### Passkey support

The platform is designed for better-auth + passkeys + RBAC. The current
implementation uses JWT with bcrypt password hashing. Passkey support is
planned for a future phase.

## RBAC: 6 roles

Role-based access control gates endpoints by role. The `require_roles(*roles)`
dependency factory returns a FastAPI dependency that checks the current user
has one of the allowed roles.

### Role hierarchy

| Role | Capabilities |
|---|---|
| `admin` | Full access. Emergency override grantor. Audit trail access. |
| `emergency_manager` | Approve alerts, dispatch tasks, access sensitive data. |
| `responder_coordinator` | Dispatch tasks, access operational data. |
| `field_responder` | Execute tasks, access exact rescue locations for assigned tasks. |
| `shelter_manager` | Shelter operations, assigned-person info (name, phone). |
| `viewer` | Ward-level aggregation only. No PII. No write access. |

### Action minimum roles

| Action | Allowed roles |
|---|---|
| `read` | All 6 roles |
| `write` | admin, emergency_manager, responder_coordinator, field_responder, shelter_manager |
| `delete` | admin, emergency_manager |
| `approve` | admin, emergency_manager |
| `dispatch` | admin, emergency_manager, responder_coordinator |
| `override` | admin only |

## ABAC: attribute-based access control

Beyond role-based checks, the ABAC engine (`app.auth.abac.ABACEngine`)
evaluates multiple attributes before granting access. The `can(actor,
action, subject, context)` method returns `True` only if every applicable
rule passes.

### Attributes evaluated

1. **Org tenancy** — `actor.org_id` must match `subject.org_id` and
   `context.current_org_id`. Cross-org access is denied.
2. **Jurisdiction** — `actor.jurisdiction` must cover `subject.jurisdiction`.
   Admins and actors with `jurisdiction="all"` bypass this check.
3. **Incident assignment** — `subject.incident_id` must be in
   `actor.incident_assignments`. Elevated roles (admin, emergency_manager)
   bypass this check.
4. **Action role** — `actor.role` must be in `ACTION_MIN_ROLES[action]`.
5. **Data sensitivity** — If `subject.sensitivity == "sensitive"`, only
   elevated roles or actors whose `current_task` matches `subject.task_id`
   can access it.

### Emergency override

Admins can grant temporary elevated access to a user during a crisis. The
override:

- Is logged to the hash-chained audit log on grant and revoke
- Expires after a configurable TTL (default 1 hour)
- Bypasses jurisdiction, incident, action-role, and sensitivity checks
- An expired override is treated as if it does not exist

```python
engine.grant_emergency_override(
    db, admin_actor, target_user_id="01J...",
    reason="Cyclone landfall — rescue team needs cross-ward access",
    ttl_seconds=3600,
)
```

Only `admin` can grant or revoke overrides. The reason is required and
non-empty.

## Org tenancy

Every table carries an `org_id` column. The `OrgContextMiddleware` resolves
`org_id` from the signed JWT on every request and stores it in
`request.state.org_id`. The org_id is **never** trusted from the client body
or query params.

All queries are scoped by `org_id` at the ORM layer. Cross-org data access
is structurally prevented: a query for org A cannot return rows belonging to
org B because the `WHERE org_id = :org_id` filter is applied by the
dependency-injected session.

## Progressive precision PII redaction

The `ProgressivePrecision` serializer (`app.lib.privacy`) controls how
entities are serialized based on the viewer's role and task assignment.
The same entity produces different JSON for different viewers.

### Precision levels

| Level | Viewer | Coordinates | PII | Audit fields |
|---|---|---|---|---|
| `public` | viewer | Ward centroid only | None | None |
| `shelter_operator` | shelter_manager | ~11m (4 decimals) | name, phone | None |
| `dispatcher` | responder_coordinator, emergency_manager | ~111m (3 decimals) | None | None |
| `rescue_team` | field_responder (assigned task) | Exact | name, medical_info | None |
| `auditor` | admin | Exact | All PII | All audit fields |

### Coordinate precision

Coordinates are rounded to a number of decimal places based on the viewer's
level:

- 3 decimals ~ 111 meters (dispatcher level)
- 4 decimals ~ 11 meters (shelter operator level)
- None = exact (rescue team, auditor)

A `viewer` sees only the ward centroid, not individual coordinates. A
`field_responder` sees exact coordinates only for entities on tasks they are
assigned to. For all other entities, they get dispatcher-level precision.

### PII fields

PII fields are stripped unless the level explicitly grants visibility:

- `public`: no PII
- `shelter_operator`: name, phone
- `dispatcher`: no PII
- `rescue_team`: name, medical_info
- `auditor`: all PII fields

### Task assignment override

A `field_responder` assigned to a task gets `rescue_team` precision for
entities on that task (exact coordinates, name, medical_info). For all other
entities, they get `dispatcher` precision (~111m, no PII). This ensures
responders have the exact location they need for their assigned rescue
without exposing exact locations of unrelated entities.

## Audit trail

All security-relevant actions are logged to the hash-chained audit trail
(`events` table). Each event carries:

- `prev_hash` — SHA-256 of the previous event in the chain
- `hash` — SHA-256 of this event's content
- `actor` — user ID of the actor
- `action` — what was done (e.g., `emergency_override_grant`)
- `entity` — what was acted upon (e.g., `user:01J...`)
- `before` / `after` — state change payload

Tampering with any middle row breaks the chain. The `verify_chain()`
function detects the first mismatch and returns its index.

## Middleware stack

Middleware execution order (outermost first):

1. **RequestIDMiddleware** — generates UUID4, sets `X-Request-Id` header,
   binds to logging context
2. **OrgContextMiddleware** — resolves `org_id` from JWT, stores in
   `request.state.org_id`, binds to logging context
3. **CORSMiddleware** — CORS handling (credentials disabled when
   `CORS_ORIGINS=*`)
4. **Router** — route handlers with dependency-injected auth

The `register_error_handlers` function adds global exception handlers that
catch `HTTPException`, `RequestValidationError`, and `Exception`, returning
a uniform `{error: {code, message, request_id}}` response.

## Demo users

Six demo users are seeded on startup when `ENVIRONMENT=development`. All use
password `demo1234` and belong to `org_id=org_demo`:

| Email | Role |
|---|---|
| `admin@demo.disaster` | admin |
| `emergency_manager@demo.disaster` | emergency_manager |
| `responder_coordinator@demo.disaster` | responder_coordinator |
| `field_responder@demo.disaster` | field_responder |
| `shelter_manager@demo.disaster` | shelter_manager |
| `viewer@demo.disaster` | viewer |

Demo user seeding is skipped entirely when `ENVIRONMENT != "development"`.
