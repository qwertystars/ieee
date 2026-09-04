# Disaster Situational Awareness & Response Platform

ResQNet-SAGE is a brownfield disaster situational-awareness and response-support platform. Canonical runtime: FastAPI backend + aiokafka worker + React/Vite PWA on PostgreSQL (PostGIS + Apache AGE + TimescaleDB + h3), with Redpanda, Redis, MinIO, optional Ollama, and Docker-based integrated verification.

## Start here

1. `docs/INDEX.md` — task-to-context router and authority rules.
2. `docs/execution/current-state.md` — what is actually implemented/verified now.
3. Load only the domain documents needed for the task.

Do not use historical plans/reports as current behavioral authority when they conflict with current code, migrations, runtime configuration, or later canonical contracts.

## Project mode and boundaries

**Mode: BROWNFIELD.** Existing code, migrations, tests, data contracts, evidence, and deployment behavior constrain changes.

The historical Cloudflare `platform/` runtime was removed and is not an active architecture. Do not recreate or extend it unless an explicit accepted architecture decision authorizes that work.

This repository is safety-sensitive decision-support software. Do not fabricate model quality, hardware/field results, production readiness, or certification. AI/ML/optimization must not independently dispatch responders or create high-consequence emergency effects.

## Authority by subject

- Current implemented behavior: current code + migrations/runtime configuration, then executed tests/evidence.
- Product intent: `docs/product/product-spec.md`.
- Business rules/invariants: `docs/domain/rules-and-invariants.md`.
- Architecture: `docs/architecture/system-architecture.md`.
- Contract ownership: `docs/contracts/contract-map.md` plus executable schemas/models/routes.
- Current status/gaps/next work: `docs/execution/`.
- Verification: `docs/quality/verification-strategy.md`.
- Security/offline/hardware/field detail: existing dedicated documents under `docs/`.

If sources conflict, record the conflict and determine whether it concerns desired behavior, observed behavior, or both. Do not silently choose stale prose over current code.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| API routes | `backend/app/api/routes/` | aggregated inline in `main.py` |
| Auth/tenancy | `backend/app/auth/`, `backend/app/deps.py`, middleware | `org_id` server-side; protected revocation fails closed |
| Realtime | `backend/app/realtime/` | authenticated WS/polling + Redis fanout |
| ML serving | `backend/app/perception/` | canonical inference contract; uncalibrated safety output abstains |
| Model registry | `backend/data/models/manifests.json` | checksums, versions, dataset/calibration metadata |
| Canonical events | `backend/app/models/events.py`, `backend/app/lib/canonical_json.py` | frozen event contract and canonical hashing |
| Database | ORM models + `backend/alembic/versions/` | PostgreSQL is system of record; forward migrations |
| Worker | `backend/app/worker/main.py` | `python -m app.worker.main`, aiokafka ConsumerManager |
| Frontend data/offline | `frontend/src/api/client.ts`, `frontend/src/lib/outbox.ts` | encrypted outbox + idempotent replay/conflicts |
| Map | `frontend/src/components/MapView.tsx`, map hooks/types | MapLibre + deck.gl |
| Evidence gates | `scripts/verify_*`, `scripts/run_*`, `evidence/`, `.omo/evidence/` | bind claims to exact evidence/revision |
| Current production gaps | `docs/execution/gap-analysis.md` | do not reopen closed old gaps without reproduction |

## Engineering invariants

- Durable IDs: uppercase 26-char ULIDs.
- Durable canonical time: UTC epoch milliseconds.
- Tenant isolation through authenticated `org_id` scope.
- External geometry: GeoJSON; spatial storage SRID 4326 where applicable.
- PostgreSQL is primary durable authority; schema changes use forward Alembic migrations.
- External delivery may be at least once; application effects must honor canonical idempotency scope.
- Hash-chained append-only audit/provenance must not be silently rewritten.
- AI/ML output is non-authoritative until required human review.
- Placeholder/synthetic/unregistered/incompatible models cannot produce operational safety output.
- Missing required calibration/domain evidence must abstain, not fake readiness.
- Protected authorization fails closed when credential revocation/freshness cannot be verified.
- Offline safety-critical conflicts require explicit resolution; no silent last-write-wins.
- Simulation and field/hardware evidence remain distinguishable.

## Commands

These commands exist in the repository. Do not claim they pass until executed for the relevant revision/environment.

```bash
make bootstrap
make migrate
make seed
make test
make lint
make typecheck
make build
make verify
make docker-up
make docker-up-full
make e2e
make load-test PROFILE=full SOAK_DURATION=<seconds>
make backup-restore-verify
```

Backend direct:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Frontend direct:

```bash
cd frontend && npm run test
cd frontend && npm run build
cd frontend && npx playwright test
```

Some integration/E2E/load checks require Docker services, migrations, seeded data, topics, and health waits. See `docs/quality/verification-strategy.md` before interpreting an environment-dependent failure.

## Hazards

- Never commit secrets or copy credentials into documentation/evidence.
- Never use `create_all()`/`ensure_table()` as production schema authority.
- Never infer production/field readiness from unit/integration tests alone.
- Never weaken tenant/RBAC/ABAC/audit/offline safety rules to make a test/demo pass.
- Never replace a failing safety output with mock/placeholder fallback.
- Do not introduce mandatory cloud dependencies without a requirement that justifies losing local/self-hosted operation.

## Documentation maintenance

After a meaningful change, update the canonical owner rather than duplicating facts:
- behavior/rules → product/rules docs;
- schema/API/event/inference contract → executable source + contract map;
- architecture → architecture doc/ADR if consequential;
- implementation completion/gap → current state, gap analysis, implementation plan;
- verification methodology/result → verification strategy and `evidence/`;
- deployment/operations → relevant runbook/operations doc.

See `backend/AGENTS.md` and `frontend/AGENTS.md` for scoped implementation rules.