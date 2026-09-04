# ResQNet-SAGE Contract Map

## Purpose

This document tells agents where contract authority lives. It does not duplicate every field from executable schemas.

Evidence baseline: `main` at `8ab15daf5c2a42f407b6d0ed75c3a8762fa13a3c`.

## Contract ownership

| Contract | Canonical executable owner | Semantic documentation | Verification |
|---|---|---|---|
| Durable event/provenance | `backend/app/models/events.py`, canonical JSON/hash helpers | `DESIGN.md` §13+, rules/invariants | event/idempotency/audit/replay tests |
| Observation persistence | SQLAlchemy models + Alembic migrations | architecture + rules | DB/integration tests |
| HTTP API | FastAPI route decorators + Pydantic request/response models | product/rules + route-specific docs | pytest API tests, Playwright for user flows |
| Realtime | `backend/app/realtime/` | security/offline/system architecture | realtime auth/filter/reconnect tests |
| ML registry/serving | `backend/data/models/manifests.json`, `backend/app/perception/serving*` | model licensing + product/rules | manifest/contract/inference tests |
| Offline replay | `frontend/src/lib/outbox.ts`, outbox policy/hooks, API client | `docs/OFFLINE_OPERATION.md`, rules | frontend/unit/E2E tests |
| Auth/RBAC/ABAC | `backend/app/auth/`, `backend/app/deps.py`, route dependencies | `docs/SECURITY_MODEL.md`, rules | auth hardening + cross-tenant tests |
| Database evolution | `backend/alembic/versions/` | architecture/current state | migration/backup/restore checks |
| Sensor source | sensor source interfaces + MQTT/serial adapters | hardware specification | adapter/source tests |
| Load/SLO measurement | `tests/load/locustfile.py`, `tests/load/combine_report.py` | verification strategy | evidence/load artifacts |
| Release/evidence claims | verifier scripts + evidence schemas | SOTA plan/current state | final verification/release gates |

## API semantics

New/changed APIs must define, in code/tests where applicable:
- authentication and tenant scope;
- actor/role/ABAC permission;
- request validation and geometry rules;
- response semantics and effective readiness/status state;
- error semantics;
- persistent and external side effects;
- idempotency requirements;
- concurrency/conflict behavior;
- pagination/query limits where applicable;
- compatibility impact on frontend/integrations.

Do not treat a route path list in an old document as stronger authority than current FastAPI registration.

## Event and job semantics

Canonical transport/application rules:
- transport may be at least once;
- idempotent application is scoped by `(org_id, source, external_id)` for the canonical external-event path;
- identical replay is a no-op rather than a duplicate effect;
- same idempotency identity with different canonical payload is a conflict;
- worker retry/DLQ/replay behavior must preserve tenant and provenance scope;
- replay cannot bypass current authorization for administrative replay operations.

Any new event contract must specify producer, consumer, schema/version, ordering scope, retry/dedup behavior, poison-message handling, replay behavior, and completion semantics.

## Data contract

Accepted data invariants:
- durable IDs are uppercase 26-character ULIDs unless explicitly migrated;
- durable canonical times are UTC epoch milliseconds;
- external geometry is GeoJSON; spatial storage uses SRID 4326 where applicable;
- tenant-owned data carries/derives `org_id` scope;
- schema evolution is forward Alembic migration;
- raw canonical/audit history is not silently rewritten to repair derived-state errors.

Indexes should be justified by current access patterns or measured performance rather than copied from old plans.

## Inference contract

The canonical inference contract distinguishes:
- `available` — contract/artifact prerequisites permit inference;
- `abstain` — model exists but required safety evidence such as calibration is unavailable or threshold policy requires abstention;
- `unavailable` — registry/artifact/dependency is missing/unverifiable;
- `incompatible` — supplied/required contract versions or shapes are incompatible.

The model manifest pins model/artifact identity, SHA-256 checksum, source, dataset metadata, versioned preprocessing/input/output contract, validation and calibration state.

### Current compatibility concern

`GET /api/capabilities` currently exposes generic feature statuses and reports `onnx_models`/`model_weights` as `available` when all manifests are `validated` and signed. That is runtime/artifact availability, not production/safety readiness. Serving may simultaneously resolve a model to `abstain` because calibration is unavailable.

**Proposed compatibility approach:** retain the existing top-level status fields for current consumers during transition, then add structured ML readiness fields. Do not redefine `available` in-place without checking frontend/tests/integrations.

Suggested new per-model semantics:

```json
{
  "model_id": "building-damage",
  "runtime_state": "available",
  "artifact_state": "trained",
  "contract_state": "validated",
  "calibration_state": "unavailable",
  "regional_validation_state": "unvalidated",
  "production_approval_state": "not_approved",
  "effective_inference_state": "abstain"
}
```

Names are proposed, not yet accepted executable contract.

## High-consequence command contract

Current later security contract requires stronger semantics than ordinary CRUD:
- authenticated active human principals;
- required distinct roles/approvers;
- exact signed command payload under the canonical framing/signature scheme;
- freshness/clock-skew bound;
- nonce uniqueness/replay rejection;
- durable organization key/JWKS trust;
- atomic approval + effect persistence;
- complete audit trail.

Any endpoint that begins producing a task/resource/public-warning/high-consequence effect must use this contract rather than a generic single-user mutation path.

## Offline contract

Offline mutations:
- preserve original tenant/user/device/idempotency context;
- revalidate authorization/freshness on replay;
- distinguish accepted, retryable, rejected, and conflict outcomes;
- never silently last-write-wins safety-critical conflicts;
- expose stale/offline state to the user.

## Compatibility procedure

Before an incompatible contract change:
1. identify callers/consumers in backend, frontend, tests, scripts, and external fixtures;
2. define old and new semantics explicitly;
3. decide whether additive coexistence is possible;
4. add characterization/contract tests for behavior that must remain compatible;
5. use a forward migration or staged API transition where data/consumer coexistence requires it;
6. record removal criteria for temporary compatibility mechanisms;
7. update this map only after the executable source of truth is updated.

## Historical contract caution

`DESIGN.md` began as a frozen parallel-implementation contract and contains older UUID, APScheduler, route-layout, and early API assumptions. Its later canonical event/provenance sections supersede some earlier material, and current implementation supersedes stale descriptive sections. Preserve it as decision/history evidence; do not use contradictory old text to overwrite working current behavior.

## Update triggers

Update this document when canonical schema owners move, compatibility policy changes, a new contract class is introduced, or an existing contract changes meaning.