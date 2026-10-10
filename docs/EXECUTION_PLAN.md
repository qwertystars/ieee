# Execution Plan — ResQNet-SAGE Phase 1

**Branch:** `codex/resqnet-phase1-completion`
**Plan date:** 2026-07-26
**Source plan:** `.omo/plans/resqnet-sage.md` (41 todos + 4 final verification tasks)

## Overview

Five gate-ordered waves, each gated before the next starts. Within each wave,
todos are dependency-ordered. Every todo carries exhaustive file references,
agent-executable acceptance criteria, happy + failure QA scenarios with evidence
paths, and a conventional commit line. Files created must stay under 250 pure
LOC. All interactive elements must have ARIA labels.

The engine layer (~60 REAL files) is remarkably complete but disconnected from
the API surface. The highest-leverage work is integration wiring, not new engine
development. Foundation repair comes first because migration drift makes every
higher layer fragile.

## Gate definitions

### Gate A — Foundation

**Goal:** Database schema is the sole authority; no runtime table creation;
core stack boots.

**Verification commands:**
```bash
docker compose config                                          # valid config
docker compose up -d --build --wait                             # all core services start
docker compose exec backend alembic upgrade head                # from fresh DB
docker compose exec backend python -c "from app.db import Base; from app.models import *; print(len(Base.metadata.tables))"
grep -rn "create_all\|ensure_table" backend/app/ --include="*.py" | grep -v test | grep -v __pycache__  # zero results
curl http://localhost:8000/healthz                             # no secrets
docker compose exec backend pytest -q                          # all existing tests pass
```

**Evidence:** `evidence/gate-a/` (dated outputs)

**Blocking:** Wave 2 cannot start until Gate A passes.

### Gate B — Phase 1 API

**Goal:** Full vertical slice works: auth → observation → confidence →
hypothesis → alert → approval → task → audit.

**Verification commands:**
```bash
docker compose exec backend python -m app.seed.seed_demo        # idempotent
curl -X POST /api/auth/login -d "username=admin@demo.disaster&password=demo1234"  # JWT
curl /api/auth/me                                               # user info
curl /api/incidents                                             # incidents
curl '/api/observations?incident_id=X&bbox=...'                 # filtered
# start simulator → rpk topic consume observations.raw          # messages
# wait 10s → SELECT count(*) FROM observations                  # increased
GET /api/incidents/X/hypotheses                                 # hypotheses with confidence
# insert corroborated thermal observation → GET /api/incidents/X/alerts  # draft alert
POST /api/incidents/X/alerts/{id}/approve                       # task created
GET /api/incidents/X/audit-logs                                 # audit entry
```

**Evidence:** `evidence/gate-b/` (dated outputs)

**Blocking:** Wave 3 cannot start until Gate B passes.

### Gate C — Frontend

**Goal:** React app builds; login flow works; map renders real data;
simulator moves; alert appears; operator approves; task appears; WebSocket +
polling both work.

**Verification commands:**
```bash
cd frontend && npm ci && npm run build                           # build succeeds
npx playwright test                                              # e2e passes
```

**Playwright assertions:**
- `[data-testid="observation-marker"]` visible
- `[data-testid="alert-card"]` visible
- click `[data-testid="approve-button"]`
- `[data-testid="task-card"]` visible
- offline: `[data-testid="pending-badge"]` → online: `[data-testid="synced-badge"]`

**Evidence:** `evidence/gate-c/` (Playwright screenshots)

**Blocking:** Wave 4 cannot start until Gate C passes.

### Gate D — Offline

**Goal:** Core stack boots without cloud; field PWA loads from cache; offline
mutation enters outbox; reconnect syncs exactly once; stale indicators appear.

**8-step offline demonstration:**
1. Responder opens field interface online
2. Connectivity disabled
3. Responder records observation + changes task status
4. Changes show as "pending"
5. Connectivity returns
6. Outbox syncs without duplication
7. Command centre receives updates
8. Data age + unavailable capabilities shown during outage

**Evidence:** `evidence/gate-d/` (dated outputs)

**Blocking:** Wave 5 cannot start until Gate D passes.

### Gate E — SOTA

**Goal:** All fusion/perception/twin/optimizer/sensing/privacy/ABAC/fairness/eval
engine tests pass with real PostgreSQL integration.

**Verification:**
```bash
# All engine test suites pass against PostgreSQL:
pytest backend/tests/test_confidence_vector.py backend/tests/test_reliability.py \
       backend/tests/test_calibration.py backend/tests/test_world_state.py \
       backend/tests/test_freshness.py backend/tests/test_llm.py \
       backend/tests/test_nlp.py backend/tests/test_flood_mapping.py \
       backend/tests/test_damage.py backend/tests/test_ensemble.py \
       backend/tests/test_serving.py backend/tests/test_scenarios.py \
       backend/tests/test_cascading.py backend/tests/test_silence.py \
       backend/tests/test_optimizer.py backend/tests/test_routing.py \
       backend/tests/test_replan.py backend/tests/test_fairness.py \
       backend/tests/test_evi.py backend/tests/test_sensing_catalog.py \
       backend/tests/test_abac.py backend/tests/test_privacy.py \
       backend/tests/test_provenance.py backend/tests/test_testbed.py \
       backend/tests/test_metrics.py backend/tests/test_failures.py \
       backend/tests/test_baselines.py backend/tests/test_ablation.py -v
```

**Evidence:** `evidence/gate-e/` (dated outputs)

**Blocking:** Final verification wave cannot start until Gate E passes.

## Milestone ordering

### Wave 1 — Gate A: Foundation (todos 1-8)

| Todo | Description | Commit | Key deliverable |
|------|-------------|--------|-----------------|
| 1 | Create working branch and implementation audit docs | `docs(audit): add implementation audit and execution plan` | This file + IMPLEMENTATION_AUDIT.md + evidence/baseline/ |
| 2 | Migration 0002a: add missing entity columns + fix enum types | `fix(db): add missing entity columns and fix enum types` | `backend/alembic/versions/0002a_entity_columns.py` |
| 3 | Migration 0002b: add missing tables + remove ensure_table | `fix(db): add missing tables and remove ensure_table workarounds` | `backend/alembic/versions/0002b_missing_tables.py`; zero `ensure_table`/`create_all` in production code |
| 4 | Add Incident, Alert, Recommendation models + migration 0003 | `feat(domain): add incident, alert, and recommendation models` | 3 new model files + migration |
| 5 | Expand OperationalTask model + migration 0004 | `feat(tasks): expand operational task model with assignment fields` | Migration 0004 |
| 6 | Harden configuration: health, CORS, JWT, test endpoint | `fix(config): harden health, cors, jwt, and test endpoints` | No secrets in /healthz; JWT validator; CORS fix |
| 7 | Dedicated worker container with retry and topic creation | `feat(streaming): run normalized observation consumer in dedicated worker with retry` | `backend/app/worker/main.py`; worker service in docker-compose |
| 8 | Gate A checkpoint | `test(gate-a): verify foundation gate` | `evidence/gate-a/` |

**Dependency order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
(Migrations must be sequential: 0002a before 0002b before 0003 before 0004.
Config hardening and worker are independent of migrations but must complete
before Gate A verification.)

### Wave 2 — Gate B: Phase 1 API (todos 9-19)

| Todo | Description | Commit | Key deliverable |
|------|-------------|--------|-----------------|
| 9 | Rescue-ball simulator core: device model and scenarios | `feat(simulator): add deterministic rescue-ball device model and scenarios` | `backend/app/simulator/rescue_ball.py`, `scenarios.py` |
| 10 | Simulator engine, API, and CLI — publishes through ingestion | `feat(simulator): add engine, api, and cli publishing through ingestion` | `backend/app/simulator/engine.py`, `api/routes/simulator.py`, `scripts/run_rescue_ball_demo.py` |
| 11 | Complete auth API: login, /me, logout, role enforcement | `feat(auth): complete login, me, logout with token revocation` | /me, /logout endpoints; Redis denylist |
| 12 | Real Observation API (replace stub) | `feat(observations): implement real observation api with filters and geojson` | POST/GET /api/observations with GeoJSON |
| 13 | Wire confidence vector and hypothesis engine to API + streaming | `feat(fusion): wire confidence vector and hypothesis engine to api` | Confidence computed on insert; hypotheses API |
| 14 | Alert and human-approval workflow | `feat(alerts): implement human-approved alert workflow` | Alert model, rules, approve/dismiss/modify endpoints |
| 15 | Response tasks and deterministic team assignment | `feat(response): add rescue task workflow with deterministic assignment` | Task API with workload-aware assignment |
| 16 | Realtime WebSocket broadcasts and polling fallback | `feat(realtime): wire websocket broadcasts and polling fallback` | manager.router registered; JWT on WS; broadcasts wired |
| 17 | Idempotent seed scenario with full demo data | `feat(seed): idempotent demo scenario with rescue-ball devices and alerts` | ORG_ID reconciled; devices, alerts, tasks, recommendations |
| 18 | Situation report, incident, entity, and audit API routes | `feat(api): implement situation report, incident, entity, and audit routes` | Situation report (text+JSON); incident CRUD; entity routes; audit verify |
| 19 | Gate B checkpoint | `test(gate-b): verify phase one api gate` | `evidence/gate-b/` |

**Dependency order:** 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19
(Simulator before API because API needs to trigger it. Auth before observations
because observations need role enforcement. Confidence before hypotheses
because hypotheses need the vector. Alerts before tasks because alert approval
creates tasks. Realtime after all event sources exist. Seed after all models
exist. Situation report last because it aggregates everything.)

### Wave 3 — Gate C: Frontend (todos 20-24)

| Todo | Description | Commit | Key deliverable |
|------|-------------|--------|-----------------|
| 20 | Frontend routing, auth context, typed API client, TanStack Query | `feat(ui): add routing, auth context, typed api client, tanstack query` | main.tsx with providers; App.tsx with routes; API client |
| 21 | Situation dashboard with map | `feat(ui): implement command center map with real data and local basemap` | MapView with real API data; local PMTiles |
| 22 | Action cards, hypothesis view, planning view | `feat(ui): implement action cards, hypothesis and planning views` | ActionCard with real API; hypothesis + planning pages |
| 23 | Simulation, field responder, device detail, audit views | `feat(ui): implement simulation, field responder, device, and audit views` | 4 new pages with loading/empty/error/stale/offline states |
| 24 | Gate C checkpoint | `test(gate-c): verify frontend gate` | `evidence/gate-c/` (Playwright) |

**Dependency order:** 20 → 21 → 22 → 23 → 24
(Infrastructure before dashboard. Dashboard before action cards. Action cards
before remaining views. All views before Gate C verification.)

### Wave 4 — Gate D: Offline (todos 25-28)

| Todo | Description | Commit | Key deliverable |
|------|-------------|--------|-----------------|
| 25 | PWA manifest, service worker, app-shell caching | `feat(offline): add pwa manifest, service worker, and app-shell caching` | manifest.json; SW registered; app shell cached |
| 26 | IndexedDB outbox and conflict-aware replay | `feat(offline): add indexeddb outbox and conflict-aware replay` | `frontend/src/lib/outbox.ts`; sync on reconnect |
| 27 | Feed-health tracking and low-bandwidth mode | `feat(offline): add feed-health tracking and low-bandwidth mode` | health.router registered; feed indicators; low-BW toggle |
| 28 | Gate D checkpoint | `test(gate-d): verify offline gate` | `evidence/gate-d/` (8-step demo) |

**Dependency order:** 25 → 26 → 27 → 28
(PWA shell before outbox. Outbox before feed-health. Feed-health before Gate D.)

### Wave 5 — Gate E: SOTA, Testing, Automation, Docs (todos 29-41)

| Todo | Description | Commit | Key deliverable |
|------|-------------|--------|-----------------|
| 29 | Replace SQLite test infrastructure with PostgreSQL/PostGIS | `test(infra): replace sqlite with postgresql postgis integration tests` | conftest.py with PostgreSQL; no ALTER TABLE workarounds |
| 30 | Phase 1 integration tests | `test(phase1): add integration tests for all phase one scenarios` | 15 new test files |
| 31 | Frontend testing: typecheck, lint, unit, Playwright e2e | `test(frontend): add typecheck, lint, vitest, and playwright e2e` | package.json scripts; vitest + Playwright |
| 32 | Wire SOTA fusion and perception to API routes | `feat(sota): wire fusion and perception engines to api` | Replace scenarios/sensing/eval stubs; world-state + calibration routes |
| 33 | Wire SOTA optimizer, twin, privacy/ABAC, fairness to API | `feat(sota): wire optimizer, twin, privacy, fairness to api` | Optimize with alternatives; cascade/silence/fairness/ABAC endpoints |
| 34 | Social media ingestion adapters (X, Reddit, Instagram, YouTube) | `feat(ingestion): add social media adapters for twitter, reddit, instagram, youtube` | 4 new adapter files |
| 35 | Event detection + unified comms (Event Registry, Ayrshare, Unipile) | `feat(ingestion): add event registry, ayrshare, and unipile adapters` | 3 new adapter files |
| 36 | Structured logging, OpenTelemetry, dependency locks | `feat(observability): add structured logging, otel, and dependency locks` | JSON logging; OTel exporter; requirements.lock |
| 37 | Makefile, automation scripts, reduced-resource profile | `feat(automation): add makefile, demo script, and reduced-resource profile` | Makefile; demo_phase1.sh; docker-compose profiles |
| 38 | Documentation: README, env, architecture, security, limitations | `docs: update readme, add all required documentation` | 6+ new doc files including KNOWN_LIMITATIONS |
| 39 | Blocker handling protocol | `feat(resilience): implement blocker handling protocol with capability status` | `/api/capabilities` endpoint; degraded behavior |
| 40 | Final report and reconcile active-plan checkboxes | `docs(report): add final report and reconcile plan checkboxes` | `docs/FINAL_REPORT.md` |
| 41 | Gate E checkpoint | `test(gate-e): verify sota gate` | `evidence/gate-e/` |

**Dependency order:** 29 → 30 → 31 → 32 → 33 → 34 → 35 → 36 → 37 → 38 → 39 → 40 → 41
(Test infrastructure before integration tests. Integration tests before frontend
tests. Tests before SOTA wiring (so wired engines can be tested immediately).
SOTA wiring before social media adapters. Adapters before observability.
Observability before automation. Automation before docs. Docs before blocker
handling. Blocker handling before final report. Final report before Gate E.)

### Final verification wave (F1-F4)

| Task | Description | Commit |
|------|-------------|--------|
| F1 | Plan compliance audit | `verify(compliance): audit all requirements against completed todos` |
| F2 | Code quality review (ruff + mypy + eslint + tsc strict) | `verify(quality): code quality review passes` |
| F3 | Real manual QA via Playwright | `verify(qa): manual qa passes via playwright assertions` |
| F4 | Scope fidelity check | `verify(scope): scope fidelity check passes` |

**Dependency order:** F1 → F2 → F3 → F4
(Compliance before quality. Quality before manual QA. Manual QA before scope
fidelity — scope fidelity is the final gate.)

## Commit strategy

- **Branch:** `codex/resqnet-phase1-completion`
- **One commit per todo** — conventional commits, matching repo style
- **Do NOT push to main** — push branch and open draft PR only after all Phase 1
  gates pass
- **If GitHub credentials unavailable:** leave branch + commits locally, report
  that publishing was unavailable
- **Pre-commit:** run relevant focused tests + type checks + inspect diff for
  secrets/large files
- **Commit message format:** `type(scope): description` (e.g., `feat(auth):`,
  `fix(db):`, `docs(audit):`, `test(gate-a):`)

## Success criteria

- `docker compose up -d --build --wait` starts all core services reproducibly
- `alembic upgrade head` succeeds from empty DB and from 0001
- No `create_all()` or `ensure_table()` in production code paths
- All API routes return real data (no stubs)
- `make demo` runs the full Phase 1 loop: seed → simulator → observations →
  confidence → hypothesis → alert → approval → task → map
- Frontend `npm run build` + `npx playwright test` pass
- Offline PWA loads from cache, outbox syncs on reconnect
- All backend tests pass against PostgreSQL/PostGIS
- Documentation reflects actual implementation
- `KNOWN_LIMITATIONS.md` honestly states simulation boundaries
- Privacy/ABAC and fairness endpoints exist (Gate E requirement)
- Active-plan checkboxes reconciled only after fresh evidence
- Final report (§17) produced with all 10 items

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Migration reconciliation breaks existing tests | High | High | Run full test suite after each migration; fix forward |
| Enum type mismatch (native PG ENUM vs VARCHAR) | High | High | Drop native ENUMs in 0002a; use VARCHAR everywhere |
| Frontend rebuild is large effort | High | Medium | Build around existing MapView + ActionCard components |
| Simulator is entirely new code | Medium | Medium | Deterministic seed; prominent simulation disclaimer |
| Docker unavailable in dev environment | Medium | High | Document clearly; use local PostgreSQL for testing |
| Model weights not available | Medium | Medium | Degraded behavior for all ML features; download script |
| ORG_ID mismatch breaks demo | High | Medium | Reconcile to "org_demo" in todo 17 |
