# ResQNet-SAGE Verification Strategy

## Purpose

This document maps important requirements/invariants to concrete checks and defines what evidence is required before a capability claim changes.

Evidence baseline: `main` at `8ab15daf5c2a42f407b6d0ed75c3a8762fa13a3c`.

## General rules

1. Distinguish **inspected**, **proposed**, **executed**, and **passed**.
2. Record exact revision for release/capability evidence.
3. Prefer deterministic tests and isolated fixtures.
4. Do not suppress flaky/environment-dependent failures without identifying the dependency and controlling it.
5. Safety, tenant, idempotency, replay, and migration failures must have negative-path tests.
6. A local machine PASS cannot satisfy external hardware/agency/field prerequisites.
7. Historical evidence does not automatically apply to a changed HEAD.

## Verification layers

| Layer | Primary use |
|---|---|
| Static analysis | lint/type correctness and obvious contract misuse |
| Unit tests | deterministic rules, serializers, policy functions, pure calculations |
| Integration tests | database, auth, streaming, model registry, storage interactions |
| Contract tests | API/event/inference compatibility and failure semantics |
| End-to-end tests | user-visible workflows, frontend/backend integration, offline/reconnect behavior |
| Replay/property tests | idempotency, canonicalization, deterministic derived state |
| Load/soak tests | throughput, latency, connection/queue pressure, memory/restart behavior |
| Chaos/resilience tests | dependency loss, recovery, overlapping failures, data integrity |
| Backup/restore tests | RPO/RTO mechanics, corruption handling, recovery integrity |
| External validation | regional datasets, validators, production telemetry, hardware/field protocols |

## Requirement-to-check map

### REQ-001 / INV-001 — Human authority and no autonomous dispatch
Checks:
- ML output defaults to draft/non-authoritative state;
- model/LLM principal cannot create high-consequence effect alone;
- high-consequence command requires applicable human approval/dual control;
- audit records identify approvers and effect.

Negative paths:
- one approver only;
- duplicate approver identity;
- invalid/expired signature;
- stale command/nonce replay;
- attempted ML-direct dispatch.

### REQ-002 / INV-002 — Tenant isolation
Checks:
- REST cross-tenant reads/writes denied or filtered;
- realtime never emits another tenant's protected payload;
- event replay/idempotency keys include tenant scope;
- offline replay cannot change tenant scope;
- viewer visibility filters remain enforced.

### REQ-003 / INV-008 — Audit/provenance
Checks:
- state-changing operations emit audit entries;
- hash-chain verification detects payload mutation, deletion, reorder, predecessor mismatch;
- chain-head mismatch fails verification;
- canonical raw/provenance links remain reconstructable.

### REQ-004/005 / ML readiness
Checks:
- placeholder/synthetic fixture cannot report trained/production-ready;
- installed trained weights may report runtime/artifact availability;
- unavailable calibration causes effective `abstain` where required;
- missing artifact => unavailable;
- incompatible version/schema => incompatible/422 where contract defines it;
- production approval defaults false unless explicit evidence/authority sets it;
- regional validation defaults unvalidated unless corresponding evidence exists.

### REQ-006 — Idempotent ingestion
Checks:
- identical repeated external event produces one application effect;
- same idempotency key + changed canonical payload is a conflict;
- consumer retry after partial processing does not duplicate durable effect;
- tenant/source scope prevents collisions across organizations.

### REQ-007/008 — Throughput and responsiveness
Use the existing Locust/combine-report harness.

Minimum bounded targets currently relevant:
- 50 concurrent operators;
- ingest >=100 observations/events per second;
- dashboard p95 <=2 s;
- API read p95 <=500 ms;
- request-success/availability threshold according to the active bounded policy;
- zero unacceptable data loss/tenant leakage/duplicate application.

Evidence must include:
- exact duration and profile;
- revision;
- request/observation counts;
- success/failure rate;
- latency percentiles;
- queue/DB/restart observations where collected;
- any host resource limitation.

### REQ-009/010 — Degraded auth/offline behavior
Redis loss:
- protected access fails closed when revocation cannot be verified;
- refresh validation/consumption fails;
- health/capability reports dependency degradation;
- durable credential state remains authoritative where designed.

Streaming loss:
- direct/core paths degrade according to documented semantics;
- acknowledged canonical events are not silently discarded;
- recovery/replay does not duplicate effects.

Offline:
- queued mutation replay uses idempotency;
- stale/conflict state is visible;
- safety-critical conflict does not auto-overwrite;
- current authorization is rechecked.

### REQ-011 — Migrations
For every schema migration:
- preflight against representative existing schema/data;
- `alembic upgrade` from supported predecessor;
- application compatibility during required coexistence window;
- integrity assertions after migration;
- interrupted/backfill recovery if applicable;
- backup/restore or forward-recovery plan for irreversible changes.

Do not infer that `downgrade` reverses external effects or canonical history.

### REQ-014/015 — Hardware/claim boundaries
Machine verification can check:
- adapter contract;
- provenance labels;
- deterministic simulator behavior;
- no-actuation policy;
- field-harness mechanics.

It cannot verify:
- actual floodwater motion;
- thermal human-detection performance;
- sensor calibration;
- RF reliability;
- field responder workload/effectiveness;
- agency acceptance.

Those remain external protocol checks.

## Current verified commands and prerequisites

The following commands exist in current repository instructions/Makefile. Their result is not claimed by this documentation pass unless separately executed.

```bash
make test
make lint
make typecheck
make build
make verify
make e2e
make load-test PROFILE=full SOAK_DURATION=<seconds>
make backup-restore-verify
```

Backend direct suite:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Frontend:

```bash
cd frontend && npm run test
cd frontend && npm run build
cd frontend && npx playwright test
```

Operational prerequisites differ by command. Full backend integration/E2E/load work generally requires the Docker services, database migrations, seed state, topics/services, and fresh data where freshness-sensitive tests depend on seed age.

## Determinism requirements for environment-dependent tests

Kafka/Redis/database integration tests should explicitly control:
- service startup and health readiness;
- required topic creation;
- unique consumer groups/topic/test data where isolation requires it;
- teardown/cleanup;
- timeouts bounded with clear failure;
- test-order independence unless an ordering rule is itself intentionally part of the harness.

If a dependency is intentionally optional, the test must distinguish “dependency unavailable by fixture” from an uncontrolled local-environment accident.

## Evidence record minimum

For consequential executed checks record:
- command;
- working directory/environment/profile;
- code revision;
- start/end timestamps when relevant;
- inputs/fixture identifiers;
- exit code/status;
- key metrics/assertions;
- cleanup;
- material limitations.

Use the repository's existing evidence formats/scripts rather than inventing parallel formats where possible.

## Release claim gates

Keep claim classes independent:
- software correctness;
- research/ML evidence;
- bounded production parity;
- production readiness;
- shadow readiness;
- field readiness.

Any required `FAIL` blocks the corresponding claim. A required missing external prerequisite produces `DEFERRED_EXTERNAL`, not a local substitute PASS.

## Verification for the next executable task

For TASK-PR-001 (ML readiness reporting), the minimum gate is:
1. focused capability/serving contract tests;
2. full backend suite;
3. frontend tests if response consumers change;
4. Playwright only if user-visible behavior changes;
5. lint/typecheck for touched languages;
6. response snapshots/examples for trained+uncalibrated, missing, placeholder, incompatible, calibrated fixture;
7. documentation update and revision-bound evidence.

No load/soak or physical test is required unless the implementation unexpectedly changes runtime performance or hardware paths.

## Update triggers

Update this document when test architecture, release gates, SLO definitions, evidence schemas, migration verification requirements, or claim classes change.