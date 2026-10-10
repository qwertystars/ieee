# Security Model

The platform implements layered access control: JWT authentication, role-based
access control (RBAC) with 6 roles, attribute-based access control (ABAC) for
fine-grained policy, org-level tenancy, emergency override, and progressive
precision PII redaction.

## Canonical event and provenance security

Task 4 establishes the root-of-truth boundary for event data. `RawEvent` values are frozen
Pydantic contracts and require ULID identity, server-captured receipt time, producer source
time, monotonic sequence, `org_id`, `incident_id`, source identity, external identity, and
explicit `visibility` and `review_status`. The raw event is retained; normalized observations,
predictions, and decisions are mutable projections with a `raw_event_id` or source-lineage
reference and cannot silently become a replacement for the raw input.

Prediction provenance is not a free-form model label. It binds model ID/version,
feature-schema version, preprocessing version, calibration version, and output-schema version.
Predictions and AI-derived decisions enter as `review_status=draft`; publication or a
high-consequence action requires the existing role-gated approval path. `public`, `internal`,
and `sensitive` visibility is carried by the contract and redaction remains enforced at the
response boundary.

### Hash-chain verification

New audit rows use RFC 8785-compatible UTF-8 canonical JSON and
`SHA-256(ASCII(prev_hash) || canonical_event_bytes)`. Canonical bytes bind tenant and incident
scope, event identity, sequence, source/receipt times, action/state snapshots, provenance,
visibility, review status, schema version, and `serialization_version`. Legacy rows are marked `legacy-v1` and verified
with their historical serializer, so migration does not discard evidence.

`audit_chain_heads` is a durable per-organization terminal checkpoint. Verification fails for a
changed payload or hash, a missing middle or tail row, a sequence reorder/gap, a forked
predecessor, or a head mismatch. Verification never repairs or reorders audit history. Database
write permissions for production must remain restricted to the append path; direct mutation is
treated as tampering even when the database permits it in development tests.

### Idempotency and tenant isolation

External effects are deduplicated by `(org_id, source, external_id)`. The first canonical
payload is recorded; an identical retry returns a no-op, while a different payload raises a
conflict instead of reporting misleading success. Missing payload versus supplied payload is
also a conflict. The migration backfills the compatibility
tenant for historical unscoped keys and preserves those rows. New boundary callers must supply
the authenticated organization and incident context; client-provided organization values are
never trusted over JWT middleware state.

Raw events are the only rebuild authority. Projection rebuilds must retain source lineage and
versioned model/calibration provenance, and must not overwrite immutable raw events or audit
rows. Malformed provenance, stale review state, duplicate external IDs, interrupted retries,
and failed chain verification are quarantine/error states rather than successful effects.
Migration `0006` has an explicit irreversible downgrade policy: its downgrade entry point fails
before any destructive operation, preserving canonical rows and preventing rollback-based data
loss.

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
protected request. When Redis is down, protected authorization fails closed;
revoked state is never inferred from availability.

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
- `actor` — stable actor ID or salted pseudonym when the source is direct PII
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

## Production secrets handling

The `docker-compose.yml` stack is a development convenience. Production
deployments must not rely on plaintext environment variables in compose files
for secrets. The compose file uses the required-variable form for the JWT
signing key:

```yaml
JWT_SECRET: ${JWT_SECRET:?JWT_SECRET must be set; use .env or export JWT_SECRET}
```

This makes `docker compose up` fail fast if `JWT_SECRET` is missing, instead
of silently falling back to a hardcoded default. The same pattern is applied
to both the `backend` and `worker` services.

### JWT_SECRET

- **Development**: `JWT_SECRET=dev-secret-change-me` (20 chars) is accepted
  only when `ENVIRONMENT=development`. The default is set in
  `backend/app/config.py` and `.env.example`.
- **Production**: `ENVIRONMENT=production` with a `JWT_SECRET` shorter than
  32 characters raises a `ValidationError` at startup
  (`app.config.Settings._validate_jwt_secret`). The process exits before
  binding a port or accepting requests.
- Generate a production secret with: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
  (64+ chars of URL-safe entropy).

### Secret distribution

For production, prefer one of the following, in order of preference:

1. **Docker secrets** (Swarm mode or Compose `secrets:` with `secrets` mount)
   - Mount the secret as a file at `/run/secrets/jwt_secret` and read it in
     the application via a small loader that sets `JWT_SECRET` from the file
     contents. This keeps the secret out of `docker inspect` and `env`.
2. **External secrets manager** (HashiCorp Vault, AWS Secrets Manager, GCP
   Secret Manager, Cloudflare Workers Secrets Store)
   - Fetch the secret at startup and inject it into the process environment.
     Rotate without redeploying where the manager supports it.
3. **`.env` file with strict permissions** (smallest deployments only)
   - `chmod 600 .env`, owner `root`, never committed to git (`.env` is in
     `.gitignore`). Use this only for single-host deployments where a
     secrets manager is not available.

Never check a production `.env` into version control. The `.env.example`
file documents the variable names with development defaults only.

### MinIO credentials

The compose file ships with `MINIO_ROOT_USER=minio` and
`MINIO_ROOT_PASSWORD=minio123` (lines 85-86), and the backend/worker
`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` match. These are **development-only**
defaults that let the stack come up without configuration.

For production:

- Replace both the MinIO root credentials and the application
  `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` with high-entropy values.
- Use MinIO service accounts (not root credentials) for the application,
  with least-privilege buckets scoped to the org.
- Rotate the application access key on a schedule (e.g., quarterly) and on
  personnel turnover. MinIO supports key rotation without downtime via the
  `mc admin user` and `mc admin policy` commands.
- Treat the MinIO secret key as a production secret: distribute it via
  Docker secrets or a secrets manager, not via plaintext compose env.

### Secrets in logs

The application logger never emits secret values. Verified by audit:

- `backend/app/lib/telemetry.py` logs only trace IDs and generic exporter status,
  and generic warning text. No `settings.JWT_SECRET`,
  `settings.MINIO_SECRET_KEY`, or `settings.DATABASE_URL` is ever logged.
- `backend/app/api/routes/service_health.py` reports dependency state as
  `unknown` until a probe runs, never as healthy merely because configuration
  exists, and never returns a connection string or credential.
- Ingestion adapters log `"api_key missing, skipping ..."` when a key is
  absent; they never log the key value itself.
- HTTP `Authorization: Bearer ...` headers are constructed in adapter code
  for outbound requests and are not logged.

A grep for `password|secret|token|jwt|api_key|access_key` across
`logger.*(` and `print(` calls in `backend/app/` returns zero matches that
emit a secret value.

## Task 21 provenance and privacy boundaries

High-consequence dispatch uses exactly one active `emergency_manager` and one
active `responder_coordinator`. Each approval is independently authenticated,
bound to an organization-owned Ed25519 key, signed over the fixed
`RESQNET-SIG-V1 || u32be(length(payload)) || payload || nonce || expires_at_ms`
frame, and rejected when stale, expired, replayed, revoked, over-age, or
outside the 30-second clock-skew window. Emergency overrides never bypass this
quorum. Denials are appended as PII-safe audit events.

Audit reconstruction joins actor, agency, device, authentication, source and
receipt times, sequence, derivation, signature/payload hashes, retention
metadata, command approvals, and offline conflict history. Exported audit
records contain hashes rather than raw signatures or direct identifiers, and
chain verification detects gaps, forks, truncation, and tampering.

Protected API responses use `private, no-store` headers and are bypassed by the
service-worker cache. Logs redact direct identifiers and sensitive fields.
Subject deletion replaces live login PII with a salted non-routable tombstone;
immutable audit retains only the pseudonym and legal retention reason, bounded
by seven years or a shorter tenant policy. External key custody, agency root
authority, and device provisioning remain `DEFERRED_EXTERNAL` prerequisites.
