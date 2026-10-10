# Disaster Situational Awareness & Response Platform

Real-time situational awareness and response coordination for urban flooding
(demo region: **Rivertown**). Monorepo: FastAPI backend + async Kafka worker +
React/Vite PWA on PostgreSQL (PostGIS + Apache AGE + TimescaleDB + h3).

## Overview
FastAPI serves the API + WebSocket realtime; a separate aiokafka worker
consumes `observations.normalized`; the React PWA is offline-first with an
encrypted IndexedDB outbox. ML (ONNX) serves flood/damage/NLP; a rescue-ball
digital-twin simulator drives scenarios. The repo is evidence-driven: every
SOTA/production claim is backed by normative JSON evidence under
`.omo/evidence/` and `evidence/` (see `scripts/verify_*` / `run_*`).

## Structure
```
backend/        FastAPI app, aiokafka worker, alembic, pytest suite
frontend/       React 18 + Vite PWA, MapLibre + deck.gl, Playwright e2e
scripts/        verify_* gates, run_* drivers (emit evidence), *_contract libs, ops
config/         pinned baselines, parity spec, SLOs, validators.lock
tests/          root integration harness (robustness, shadow replay, parity)
benchmarks/     pinned baseline configs (DEFERRED_EXTERNAL until licensed)
data/datasets/  dataset registry + benchmark manifest (licensed metadata only)
evidence/       RPO/RTO, chaos, load, soak, gates, final-verification, sota
.omo/           work plans (plans/), per-task evidence (evidence/), boulder.json
docs/           runbooks, security model, field trial protocol, final report
deploy/         production-parity HAProxy config; vm/ Caddyfile for single-VM prod
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| API routes | `backend/app/api/routes/` | 30 modules; aggregated inline in `main.py` (no api/router.py) |
| Auth/tenancy | `backend/app/auth/`, `middleware/`, `deps.py` | org_id server-side from JWT, RBAC + ABAC |
| Realtime | `backend/app/realtime/` | WS via `realtime/manager.py` router + Redis fanout |
| ML serving | `backend/app/perception/` | manifest-bound ONNX (serving_runtime/contracts/execution/storage) |
| Canonical data | `backend/app/models/events.py`, `lib/canonical_json.py` | frozen event contract, RFC 8785 hashing |
| Frontend data | `frontend/src/api/client.ts`, `lib/outbox.ts` | fetch wrapper + offline outbox routing |
| Map | `frontend/src/components/MapView.tsx`, `hooks/useMapLayers.ts` | MapLibre + deck.gl, PMTiles basemap |
| Evidence gates | `scripts/verify_plan.py`, `verify_release_gate.py`, `verify_scope.py` | F1-F4 final verification |
| SOTA plan | `.omo/plans/resqnet-sota-roadmap.md` | 27 todos / 7 waves, all `[x]` |

## CONVENTIONS
- Durable IDs: 26-char uppercase ULIDs (`backend/app/lib/ulid.py`, `frontend/src/lib/ulid.ts`); timestamps UTC epoch ms (`lib/time.py`)
- `org_id` tenancy on every table, derived server-side from JWT (never client body)
- `visibility ∈ {public,internal,sensitive}` + `review_status ∈ {draft,reviewed,official}`; all AI output lands as `draft` until human approval
- Hash-chained append-only audit: `events(prev_hash,hash)` with chain verification (`lib/audit.py`)
- Idempotency keys on external/queue/webhook paths, exactly-once per `(org_id, source, external_id)` (`lib/idempotency.py`)
- Geometry: GeoJSON + PostGIS `Geometry(srid=4326)` (canonical contract: DESIGN.md §13)
- Files under 250 LOC; `*_types.py` split convention in domain modules
- Conventional commits: `feat(scope): description`
- Honest boundaries: `DEFERRED_EXTERNAL` marks claims blocked on licensed data / hardware / agency / IRB — never fabricate PASS

## COMMANDS
```bash
make bootstrap     # pip + npm install
make migrate       # alembic upgrade head
make seed          # python -m app.seed.seed_demo (Rivertown demo)
make test          # pytest backend (skips test_seed.py)
make lint          # ruff            make typecheck # mypy
make build         # frontend vite build
make verify        # migrate + seed + test + build
make docker-up     # full stack       make docker-up-full # + observability
make e2e           # compose up + seed + Playwright (needs fresh seed for freshness tiers)
make prod-up       # single-VM production stack (docs/DEPLOY_VM.md)
make load-test     # 2-phase locust    make backup-restore-verify # RPO/RTO proof
```

## ANTI-PATTERNS (THIS PROJECT)
- No unauthenticated realtime path; no cross-tenant access (viewers see only `public` records)
- No silent v1/v2 model routing or mock fallback for safety output — abstain, don't fake
- No `as any` / `@ts-ignore` in frontend; no `type: ignore` sprawl in backend
- No test-order coupling: Playwright map suite must run first (freshness tiers derive from seed age)
- No fabricated metrics: every PASS must have executable evidence with exit code + hashes

## NOTES
- Backend DB is **sync SQLAlchemy** in routes; async only in streaming/realtime/worker (aiokafka/anyio)
- Alembic migrations 0001–0012 (0002a/0002b sub-numbered); never rewrite history, forward-migrate
- README worker description is stale ("APScheduler") — actual worker is `python -m app.worker.main` (aiokafka ConsumerManager)
- `.env` (compose-facing) is git-ignored; host tests use `backend/.env` + process-env fallback
- See `backend/AGENTS.md` and `frontend/AGENTS.md` for domain-specific rules.
