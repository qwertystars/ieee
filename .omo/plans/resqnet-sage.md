# resqnet-sage - Work Plan

## TL;DR (For humans)

**What you'll get:** A tested, reproducible, software-first ResQNet-SAGE disaster-response system. The backend engine layer is already ~60 REAL files (fusion, perception, optimizer, twin, knowledge, sensing, eval, streaming, realtime, auth, ABAC). This plan wires those engines to real API routes, reconciles the drifted database schema with forward-only Alembic migrations, builds a deterministic rescue-ball simulator, implements the complete Phase 1 sensing-to-response loop (telemetry → ingestion → confidence → hypothesis → alert → human approval → task → map), builds a full React frontend with offline PWA support, continues the SOTA research plan (including privacy/ABAC wiring and fairness reporting — both required for Gate E), and adds comprehensive testing, automation, and documentation.

**Why this approach:** The engine layer is remarkably complete but completely disconnected from the API surface (5 of 9 routes are stubs returning `{"status":"ok"}`). The highest-leverage work is integration wiring, not new engine development. Foundation repair comes first because the migration drift (13 entity tables missing columns, 8+ runtime-created tables, orphaned `sources` table) makes every higher layer fragile.

**What it will NOT do:** Will not extend the Cloudflare Workers `platform/` codebase. Will not use an unconstrained LLM or RL controller for field commands. Will not fabricate model accuracy or hardware capabilities. Will not push to main. Will not download huge datasets into Git.

**Effort:** Large — 41 implementation todos across 5 gate-ordered waves plus 4 final verification tasks. Each todo is scoped to 1-3 tool calls with exhaustive references. Includes social media ingestion adapters (X/Twitter, Reddit, Instagram, YouTube), event detection (Event Registry), and unified communication (Ayrshare outbound, Unipile inbound DMs).

**Risk:** Migration reconciliation is the highest-risk area (must not break existing tests or lose data). The enum type mismatch (native PG ENUM vs VARCHAR) requires careful migration. The frontend is a near-total rebuild. The simulator is entirely new code.

**Decisions:** Dedicated worker container (prompt's preferred option). VARCHAR for all enums (matches ORM's `native_enum=False`). New Incident table (preserving Event as audit log). Local PMTiles with OSM fallback. PostgreSQL/PostGIS test DB (not SQLite-only). Alert thresholds: s ≥ 0.5 AND C ≥ 0.2 (reasonable defaults, documented as configurable). Travel cost via `RouteReliabilityEngine.compute_cost()` (validated to exist at `routing.py:130`). Reconcile ORG_ID: `seed/ids.py` uses `"demo_org"` but `auth/seed.py` uses `"org_demo"` — pick `"org_demo"` and update `seed/ids.py` to match.

## Scope

The entire 17-section execution prompt: implementation audit, foundation repair (migrations, incident domain, config hardening, worker lifecycle), rescue-ball simulator, Phase 1 vertical slice (auth, observation API, confidence/hypothesis, alerts/approval, tasks/assignment, realtime, seed, situation report), frontend (8 pages, map, action cards, offline states), offline PWA, SOTA plan continuation (fusion, perception, twin, optimizer, active sensing, privacy/ABAC, fairness, evaluation), testing hierarchy, phase gates A-E, automation commands, documentation, commit discipline, blocker handling, final report.

## Verification strategy

- **Gate A (Foundation):** `docker compose exec backend alembic upgrade head` succeeds from empty DB and from 0001; ORM/migration schema check passes; no `create_all()` or `ensure_table()` in production code paths; backend + worker start; health endpoints don't leak secrets; full backend test suite passes (with PostgreSQL test DB).
- **Gate B (Phase 1 API):** Seed is idempotent; login + /me + logout work; observation filters work; simulator publishes through ingestion; observation reaches PostgreSQL; confidence vector exists on observations; trapped-person hypothesis/alert produced; operator approval creates a task; audit + provenance present.
- **Gate C (Frontend):** `npm run build` succeeds; login flow works; map renders seeded data; simulator moves; alert appears; operator approves it; task appears in field responder view; task update reaches command centre; WebSocket + polling fallback both work.
- **Gate D (Offline):** Core stack boots without cloud; field PWA loads from cache; offline mutation enters outbox; reconnect syncs exactly once; stale/degraded indicators appear.
- **Gate E (SOTA):** All fusion/perception/twin/optimizer/sensing/privacy/ABAC/fairness/eval engine tests pass with real PostgreSQL integration.
- **Final verification wave:** F1 plan compliance audit, F2 code quality review, F3 real manual QA (Playwright-asserted), F4 scope fidelity.

## Execution strategy

Five gate-ordered waves, each gated before the next starts. Each wave ends with a gate-checkpoint verification todo. Within each wave, todos are dependency-ordered. Every todo carries exhaustive file references (the executor has no interview context), agent-executable acceptance criteria, happy + failure QA scenarios with evidence paths, and a conventional commit line. Files created must stay under 250 pure LOC — split by responsibility if exceeded. All interactive elements must have ARIA labels. Pre-commit: run relevant focused tests + type checks + inspect diff for secrets/large files.

## Todos

### Wave 1 — Gate A: Foundation

- [x] 1. Create working branch and implementation audit docs
  - **References:** prompt §4 (audit requirements), `evidence/baseline/` (new dir), all findings from `.omo/drafts/resqnet-sage.md`
  - **Acceptance:** (a) `git checkout -b codex/resqnet-phase1-completion` creates the branch; (b) `docs/IMPLEMENTATION_AUDIT.md` exists with a capability table (capability, authoritative requirement, relevant files, actual implementation status, test status, defects/risds, dependency, recommended action) covering ALL items from prompt §4; each classified as verified working / implemented but unverified / partial / stub / broken / missing / historical; (c) `docs/EXECUTION_PLAN.md` exists with milestone ordering and gate definitions; (d) `evidence/baseline/` contains dated baseline command outputs (docker compose config output, alembic current, test count). Do NOT delete or overwrite existing evidence files — use dated/milestone-specific filenames.
  - **QA happy:** Branch exists (`git branch --list codex/resqnet-phase1-completion`); audit covers all §4 capabilities (verify each: Docker stack, DB extensions, Alembic, ORM-schema, auth, tenant isolation, audit chain, idempotency, observation schema, source registry, all 5 ingestion adapters, Redpanda/Benthos, consumer lifecycle, knowledge graph, hypotheses, source reliability, freshness, confidence vector, world-state estimation, model calibration, perception modules, scenarios/digital twin, optimization, active sensing, privacy/ABAC, fairness, APIs, WebSockets, frontend, map, PWA/offline, seed data, evaluation framework, observability, documentation, test coverage, security weaknesses).
  - **QA failure:** Branch not created → fail; any §4 capability missing from audit → fail.
  - **Commit:** `docs(audit): add implementation audit and execution plan`

- [x] 2. Migration 0002a: add missing entity columns + fix enum types
  - **References:** `backend/app/seed/db_setup.py:16-43` (list of 26 missing columns — NOTE: list is incomplete, missing `hazards.hazard_type`, `hazards.severity`, `bridges.name`, `bridges.status`, `operational_tasks.title`, `operational_tasks.status`, `operational_tasks.priority` — cross-reference against entities.py to find ALL missing columns), `backend/app/models/entities.py:29-186` (ORM model definitions — cross-reference every model field against this list)
  - **Acceptance:** New `backend/alembic/versions/0002a_entity_columns.py`. For each of the 13 entity tables, `op.add_column()` for every ORM-defined field not in migration 0001 (cross-reference entities.py:29-186 against db_setup.py:16-43 — verify db_setup.py list is complete; if ORM has fields not in db_setup.py, add those too). Drop the 6 native PG ENUM types (`sourcetype`, `corroborationstate`, `accesspolicy`, `hypothesisstatus`, `scenariolabel`, `scenariostatus`) and alter columns to VARCHAR. Add tenant-aware composite indexes on `(org_id, incident_id)` for all entity tables. Add time-series index on `observations(observed_at, org_id)`. Downgrade reverses all. `alembic upgrade head` from empty DB and from 0001 both succeed.
  - **QA happy:** `docker compose exec backend alembic upgrade head` exits 0 from fresh DB; `docker compose exec backend python -c "from app.db import Base; from app.models import *; Base.metadata.create_all(bind=None)"` doesn't raise (metadata consistent); ORM field count matches DB column count for each entity table.
  - **QA failure:** Migration fails on DB with existing data → fail; ORM field missing from migration → fail; enum drop fails → fail.
  - **Commit:** `fix(db): add missing entity columns and fix enum types`

- [x] 3. Migration 0002b: add missing tables (users, sources, idempotency, reliability, sync, h3, provenance)
  - **References:** `backend/app/models/user.py:9-19`, `backend/app/models/source.py:51-78`, `backend/app/lib/idempotency.py:33-46`, `backend/app/fusion/reliability.py:44-59`, `backend/app/ingestion/federation.py` (federation_outbox), `backend/app/realtime/edge_sync.py` (edge_sync tables), `backend/app/realtime/sync.py` (sync tables), `backend/app/perception/models.py:80-95`, `backend/app/perception/llm_types.py` (llm_call_log), `backend/app/audit/provenance_types.py` (decision_provenance), prompt §5.1 (h3_geo_index table)
  - **Acceptance:** New `backend/alembic/versions/0002b_missing_tables.py` creates: `users` (matching User model), `sources` (matching Source model), `idempotency_keys` (with unique constraint `uq_idempotency_source_external`), `source_reliability` (with unique constraint `(source_id, phenomenon_type)`), `federation_outbox`, `edge_sync_applied`, `edge_sync_state`, `sync_conflict`, `sync_applied`, `perception_models`, `prompt_records`, `llm_call_log`, `decision_provenance`, `h3_geo_index` (id BigInteger PK, entity_type String, entity_id String(26), h3 String, org_id String, incident_id String, unique constraint on `(entity_type, entity_id, h3)`). All with appropriate indexes. Downgrade drops all. After this migration, remove all `ensure_table()` / `ensure_tables()` function definitions AND calls from production code (idempotency.py:49-58, reliability.py:61-70, federation.py, edge_sync.py, sync.py, perception/models.py, llm_types.py, provenance_types.py). Remove `Base.metadata.create_all()` from `main.py:25` and `auth/seed.py:57`.
  - **QA happy:** `grep -rn "ensure_table\|create_all" backend/app/ --include="*.py" | grep -v test | grep -v __pycache__ | grep -v ".pyc"` returns zero results; `alembic upgrade head` creates all tables.
  - **QA failure:** Any `ensure_table()` or `create_all()` in non-test production code → fail; table missing from migration → fail.
  - **Commit:** `fix(db): add missing tables and remove ensure_table workarounds`

- [x] 4. Add Incident, Alert, and Recommendation models + migration 0003
  - **References:** prompt §5.2 (incident fields), prompt §7.4 (alert fields), `backend/app/models/events.py:14-29` (Event=audit — preserve, do NOT modify), `backend/app/models/__init__.py:28-49` (exports)
  - **Acceptance:** New files: `backend/app/models/incident.py` (`Incident`: ULID id, org_id, title, disaster_type, severity, status, declaration_level, description Text, geometry GEOMETRY SRID 4326, start_time BigInteger, expected_end BigInteger nullable, config JSONB, created_at, updated_at); `backend/app/models/alert.py` (`Alert`: ULID id, org_id, incident_id FK→incidents, alert_type, title, message Text, area GEOMETRY nullable, severity, recommended_action Text, confidence_vector JSONB, status default 'draft', created_by, created_at, updated_at, reviewed_by nullable, review_rationale Text nullable, reviewed_at BigInteger nullable); `backend/app/models/recommendation.py` (`Recommendation`: ULID id, org_id, incident_id, alert_id FK nullable, recommendation_type, title, description, reasoning Text, supporting_evidence JSONB, contradicting_evidence JSONB, confidence_vector JSONB, urgency, status default 'draft', assigned_team_id String nullable, created_at, updated_at). Migration `0003_incidents_alerts.py` creates all 3 tables with GiST geometry indexes, org_id+incident_id composite indexes. All exported from `__init__.py`. Event table untouched.
  - **QA happy:** `alembic upgrade head` creates 3 new tables; `from app.models.incident import Incident; from app.models.alert import Alert; from app.models.recommendation import Recommendation` works; `alembic downgrade -1` drops all 3.
  - **QA failure:** Event table modified → fail; missing GiST index → fail; missing FK alert→incident → fail.
  - **Commit:** `feat(domain): add incident, alert, and recommendation models`

- [x] 5. Expand OperationalTask model + migration 0004
  - **References:** `backend/app/models/entities.py:167-177` (current minimal OperationalTask), prompt §7.5 (task fields)
  - **Acceptance:** Migration `0004_task_expansion.py` adds to `operational_tasks`: `assigned_team_id` String nullable, `required_capability` String nullable, `assignment_history` JSONB nullable. Update `entities.py` OperationalTask class to match.
  - **QA happy:** `alembic upgrade head` succeeds; `SELECT column_name FROM information_schema.columns WHERE table_name='operational_tasks'` includes assigned_team_id, required_capability, assignment_history.
  - **QA failure:** Column missing → fail.
  - **Commit:** `feat(tasks): expand operational task model with assignment fields`

- [x] 6. Harden configuration: safe health, CORS, JWT, test endpoint
  - **References:** `backend/app/main.py:100-113` (healthz leaks DATABASE_URL), `backend/app/main.py:160-163` (test error unrestricted), `backend/app/main.py:68-77` (CORS wildcard+credentials), `.env.example:24` (JWT_SECRET), `backend/app/config.py:1-44`
  - **Acceptance:** (a) `/healthz` returns service names without full URLs (`"database": "connected"` not connection string); (b) `/healthz/deep` returns ok/false per service without credentials; (c) `/api/_test/error` returns 404 when `ENVIRONMENT != "development"`; (d) CORS: if `CORS_ORIGINS == "*"`, set `allow_credentials=False` and log warning; (e) `JWT_SECRET` must be ≥32 chars when `ENVIRONMENT != "development"` or app refuses to start (add validator to Settings); (f) MinIO credentials already aligned (minio/minio123) — verify consistency.
  - **QA happy:** `curl /healthz` returns no DATABASE_URL; `ENVIRONMENT=production curl /api/_test/error` returns 404; `ENVIRONMENT=production JWT_SECRET=short` fails to start.
  - **QA failure:** Secret in health → fail; test endpoint in prod → fail; wildcard CORS + credentials → fail.
  - **Commit:** `fix(config): harden health, cors, jwt, and test endpoints`

- [x] 7. Implement dedicated worker container with retry and topic creation
  - **References:** `backend/app/streaming/consumer.py:28-171` (ConsumerManager), `backend/app/streaming/consumer.py:18` (import of `ensure_table` — remove after migration 0002b), `docker-compose.yml:139-180` (backend service), `benthos/disaster_pipeline.yaml`, prompt §5.4 (worker requirements including retry)
  - **Acceptance:** (a) New `backend/app/worker/main.py` entry point: instantiates `ConsumerManager`, calls `start(["observations.normalized"])`, runs `consume()` with graceful SIGTERM/SIGINT shutdown; (b) `docker-compose.yml` adds `worker` service (build `./backend`, command `python -m app.worker.main`, depends_on db healthy + redpanda started, resource limits 1CPU/1G); (c) `scripts/create_topics.sh` creates `observations.raw`, `observations.normalized`, `observations.dlq` via `rpk topic create` (idempotent); (d) **Add retry logic to consumer**: transient errors (DB connection, timeout) retried 3x with exponential backoff (1s, 2s, 4s) before DLQ; permanent errors (ValueError, schema) go directly to DLQ; (e) worker healthcheck via process check (`pgrep -f app.worker.main`); (f) worker exposes Prometheus metrics on port 8001; (g) remove `ensure_table()` call from `consumer.py:59` AND remove `ensure_table` from the import on `consumer.py:18` (change to `from app.lib.idempotency import check_and_record`); (h) add confidence vector computation call after insert (wired in todo 13).
  - **QA happy:** `docker compose up -d --build --wait` starts worker; `docker compose logs worker` shows "Consumer started"; test message to `observations.raw` appears in `observations` table within 10s; sending malformed message goes to DLQ; stopping DB briefly then restarting → consumer retries, doesn't crash.
  - **QA failure:** Worker crashes on startup → fail; transient error goes to DLQ without retry → fail; worker doesn't shutdown on SIGTERM → fail.
  - **Commit:** `feat(streaming): run normalized observation consumer in dedicated worker with retry`

- [x] 8. Gate A checkpoint — verify foundation
  - **References:** All Wave 1 todos, prompt §12 Gate A
  - **Acceptance:** Run: `docker compose config` (valid); `docker compose up -d --build --wait` (all core services start); `docker compose exec backend alembic upgrade head` (from fresh DB); `docker compose exec backend python -c "from app.db import Base; from app.models import *; print(len(Base.metadata.tables))"` (matches expected count); `grep -rn "create_all\|ensure_table" backend/app/ --include="*.py" | grep -v test | grep -v __pycache__` (zero results); `curl http://localhost:8000/healthz` (no secrets); `docker compose exec backend pytest -q` (all existing tests pass — tests may need PostgreSQL, see todo 28 for test infra fix; for Gate A, run with `DATABASE_URL` pointing to Docker DB). Record evidence in `evidence/gate-a/`.
  - **QA happy:** All checks pass; `evidence/gate-a/` contains dated outputs.
  - **QA failure:** Any check fails → block Wave 2.
  - **Commit:** `test(gate-a): verify foundation gate`

### Wave 2 — Gate B: Phase 1 API

- [x] 9. Build rescue-ball simulator core: device model and scenarios
  - **References:** prompt §6 (simulator spec), `backend/app/lib/ulid.py:37-58`, `backend/app/seed/ids.py:1-41` (deterministic ID pattern), `backend/app/fusion/freshness.py:1-113` (phenomenon tau values)
  - **Acceptance:** New `backend/app/simulator/rescue_ball.py` (<250 LOC) — `RescueBallDevice` dataclass with: device_id (ULID), org_id, incident_id, lon, lat, altitude, deployment_state, velocity, heading, battery_pct, estimated_remaining_runtime, link_type, signal_quality, packet_loss, device_temperature, enclosure_status, camera_status, thermal_sensor_status, imu_reading, acoustic_reading, last_seen_ts, health_flags. `step(delta_ms, rng)` advances state deterministically (seedable `random.Random`). New `backend/app/simulator/scenarios.py` (<250 LOC) — predefined Rivertown flood path (waypoints), fault injection functions (battery_drain, sensor_degradation, connectivity_loss, blocked_route, thermal_hotspot, human_heat_signature, water_depth, motion, vibration, environmental_temp). Prominent docstring: "DIGITAL SIMULATION — physical rescue ball, mobility, communications, thermal accuracy, and landing mechanism have NOT been validated."
  - **QA happy:** `from app.simulator.rescue_ball import RescueBallDevice; d = RescueBallDevice(...); d.step(1000, random.Random(42))` produces deterministic output; running with seed 42 twice gives identical state.
  - **QA failure:** Non-deterministic with same seed → fail; missing simulation disclaimer → fail; file >250 LOC → fail.
  - **Commit:** `feat(simulator): add deterministic rescue-ball device model and scenarios`

- [x] 10. Build simulator engine, API, and CLI — publishes through ingestion
  - **References:** `backend/app/streaming/producer.py:19-68` (ProducerManager), `backend/app/streaming/consumer.py:114-147` (_build_observation payload format — simulator must produce matching fields), prompt §6 (start/pause/resume/stop/replay/speed)
  - **Acceptance:** New `backend/app/simulator/engine.py` (<250 LOC) — `SimulationEngine` with start/pause/resume/stop/replay, configurable speed, deterministic seed, publishes observations through `ProducerManager.send("observations.raw", payload)` where payload contains: `observation_id` (ULID), `event_type`, `phenomenon`, `geometry` (GeoJSON Point), `observed_at`, `source_id`, `source_type`, `org_id`, `incident_id`, `value`, `unit`, `provenance_chain` (includes `{"simulated": true}`), `raw_data_hash`. Large artifacts (thermal frames) stored in MinIO, observation contains `quality_flags.artifact_ref` pointing to MinIO object. New `backend/app/api/routes/simulator.py` — `POST /api/simulator/start`, `POST /api/simulator/stop`, `GET /api/simulator/status`, `POST /api/simulator/inject-fault`. New `scripts/run_rescue_ball_demo.py` — CLI runner with `--seed` flag.
  - **QA happy:** `python -m scripts.run_rescue_ball_demo --seed 42` twice → identical observation_ids and values; `rpk topic consume observations.raw` shows messages with `"simulated": true` in provenance; `POST /api/simulator/start` returns 202 with device IDs.
  - **QA failure:** Simulator writes directly to DB → fail; payload missing `observation_id` → fail; no simulated flag → fail.
  - **Commit:** `feat(simulator): add engine, api, and cli publishing through ingestion`

- [x] 11. Complete auth API: login, /me, logout, role enforcement, tenant isolation
  - **References:** `backend/app/api/routes/auth.py:19-37` (login only), `backend/app/auth/jwt.py:1-23`, `backend/app/auth/roles.py:1-38`, `backend/app/auth/abac.py:1-229`, `backend/app/middleware/org_context.py:1-39`, `backend/app/deps.py:1-55`, `backend/app/auth/seed.py:1-83`
  - **Acceptance:** (a) `GET /api/auth/me` returns user from JWT; (b) `POST /api/auth/logout` adds JWT to Redis denylist (`revoked_tokens` SET with TTL = remaining token lifetime); if Redis unavailable, log warning and still return 204 (best-effort); (c) `get_current_user` checks Redis denylist before accepting token; (d) `require_roles(*roles)` applied to all state-changing endpoints; (e) `OrgContextMiddleware` already extracts org_id from JWT only (`org_context.py:31` — already implemented, no change needed); (f) demo users with `demo1234` only when `ENVIRONMENT=development`.
  - **QA happy:** Login → JWT; /me → user info; logout → 204; subsequent /me → 401; org A user → empty result for org B observations; viewer POST → 403.
  - **QA failure:** org_id from request body accepted → fail; viewer can POST → fail; revoked token works → fail.
  - **Commit:** `feat(auth): complete login, me, logout with token revocation`

- [x] 12. Implement real Observation API (replace stub)
  - **References:** `backend/app/api/routes/observations.py:1-14` (STUB), `backend/app/models/observation.py:16-104` (23-field model), `backend/app/fusion/confidence.py:140-284` (ConfidenceVectorCalculator), `backend/app/lib/ulid.py:37-58`, `backend/app/lib/audit.py:1-120`
  - **Acceptance:** Replace stub with: (a) `POST /api/observations` — create from GeoJSON, generate ULID, compute confidence vector via `ConfidenceVectorCalculator.compute_vector()`, `attach_to_observation()`, write audit, return GeoJSON Feature; (b) `GET /api/observations` — list with pagination + filters: incident_id, source_id, phenomenon, time range, bbox (ST_MakeEnvelope + ST_Intersects), freshness threshold, confidence dimension filters (quality_flags->confidence_vector->s >= X), visibility (access_policy by role); (c) `GET /api/observations/{id}` — detail as GeoJSON; (d) all responses are GeoJSON Feature/FeatureCollection, never WKT; (e) `require_roles()` applied; (f) org_id from `request.state.org_id`. If file exceeds 250 LOC, split into `observations.py` (routes) + `observations_queries.py` (filter logic).
  - **QA happy:** POST returns 201 with ULID + confidence_vector; GET with bbox excludes out-of-bounds; org B user → empty for org A.
  - **QA failure:** WKT in response → fail; org_id from client → fail; no confidence_vector → fail.
  - **Commit:** `feat(observations): implement real observation api with filters and geojson`

- [x] 13. Wire confidence vector and hypothesis engine to API and streaming
  - **References:** `backend/app/fusion/confidence.py:140-284` (REAL), `backend/app/knowledge/graph.py:1-262` (REAL), `backend/app/api/routes/hypotheses.py:1-14` (STUB), `backend/app/streaming/consumer.py:80-112` (_process — add confidence call), `backend/app/models/hypotheses.py:1-29`
  - **Acceptance:** (a) After consumer inserts observation, call `ConfidenceVectorCalculator.compute_vector()` + `attach_to_observation()` before commit; (b) POST /api/observations also computes; (c) Replace hypotheses stub: `GET /api/incidents/{incident_id}/hypotheses` (list with supporting_evidence, contradicting_evidence, probability, status, data_age); `POST /api/incidents/{incident_id}/hypotheses` (create); (d) After new observation, if corroborates/contradicts existing hypothesis, update evidence arrays + probability; (e) contradictory hypotheses remain stored and visible; (f) scalar display confidence available but 6D vector is source of truth.
  - **QA happy:** 2 same-phenomenon observations near same location → both have confidence_vector with C > 0; GET hypotheses returns supporting + contradicting evidence.
  - **QA failure:** Vector missing → fail; contradicting hypothesis deleted → fail; scalar used for reasoning → fail.
  - **Commit:** `feat(fusion): wire confidence vector and hypothesis engine to api`

- [x] 14. Implement alert and human-approval workflow
  - **References:** prompt §7.4, `backend/app/models/alert.py` (todo 4), `backend/app/audit/provenance.py:1-194` (ProvenanceChain), `backend/app/lib/audit.py:1-120`, `backend/app/realtime/manager.py:1-172`
  - **Acceptance:** (a) New `backend/app/alerts/rules.py` (<250 LOC) — `evaluate_alerts(db, incident_id)`: if thermal human-detection observation has `confidence_vector.s >= 0.5` AND `C >= 0.2` (documented as configurable thresholds), create draft Alert; (b) `GET /api/incidents/{incident_id}/alerts` — list with status filter; (c) `POST /api/incidents/{incident_id}/alerts/{id}/approve` — admin/emergency_manager only: sets status='approved', reviewed_by, reviewed_at, rationale; creates audit + provenance; triggers task creation; (d) `POST .../alerts/{id}/dismiss` — dismiss with rationale; (e) `POST .../alerts/{id}/modify` — modify recommended_action before approving; (f) system NEVER auto-dispatches; (g) all changes broadcast via WebSocketManager.
  - **QA happy:** Corroborated thermal observation → draft alert appears; approve with admin token → status='approved', audit entry exists, task created.
  - **QA failure:** Auto-dispatch without approval → fail; viewer can approve → fail; no audit → fail.
  - **Commit:** `feat(alerts): implement human-approved alert workflow`

- [x] 15. Implement response tasks and deterministic team assignment
  - **References:** `backend/app/models/entities.py:167-177` (OperationalTask expanded in todo 5), `backend/app/optimizer/routing.py:130-145` (compute_cost method — verified at line 130, NOT 210), `backend/app/optimizer/routing.py:1-260` (RouteReliabilityEngine), prompt §7.5 (must include workload factor)
  - **Acceptance:** (a) `GET /api/incidents/{incident_id}/tasks` — list with status filter; (b) `POST /api/incidents/{incident_id}/tasks` — create task; (c) `PATCH /api/tasks/{id}` — update status (field responder); (d) `POST /api/incidents/{incident_id}/tasks/{id}/assign` — deterministic assignment: query eligible teams (matching capability, status='available'), compute travel cost via `RouteReliabilityEngine.compute_cost()`, exclude teams behind blocked/dangerous roads, **factor in workload** (teams with fewer active assignments preferred), pick lowest combined cost+workload team; (e) assignment creates audit entry + assignment_history entry; (f) documented as initial deterministic method, separate from CVaR optimizer.
  - **QA happy:** Create task → assign → nearest available team with matching capability + lowest workload assigned; team status → 'assigned'; audit entry exists.
  - **QA failure:** No workload factor → fail; assigned team doesn't match capability → fail; no audit → fail.
  - **Commit:** `feat(response): add rescue task workflow with deterministic assignment`

- [x] 16. Wire realtime WebSocket broadcasts and polling fallback
  - **References:** `backend/app/api/routes/ws.py:1-32` (ping/pong), `backend/app/realtime/manager.py:1-172` (REAL WebSocketManager + polling endpoint), prompt §7.6 (event types)
  - **Acceptance:** (a) Replace ws.py: on connect, validate JWT, subscribe to incident_id channel via `manager.connect()`; (b) After observation insert → `manager.broadcast_observation()`; (c) After hypothesis update → `manager.broadcast_hypothesis()`; (d) After alert created/approved/dismissed → broadcast; (e) After task assigned/status changed → broadcast; (f) After team location updated → broadcast; (g) After road status changed → broadcast; (h) Feed degradation → broadcast; (i) `GET /api/incidents/{incident_id}/events?since={ts}` polling endpoint returns events since timestamp; (j) **Register `manager.router` in `main.py`** — the WebSocketManager's router (containing `/ws/realtime/{incident_id}` and `/api/incidents/{incident_id}/updates` polling endpoint) is currently NOT included in `main.py`; add `from app.realtime.manager import router as realtime_router` and `app.include_router(realtime_router)` to `main.py`.
  - **QA happy:** WebSocket with JWT → insert observation → client receives `{"type":"new_observation"}` within 2s; polling endpoint returns same event.
  - **QA failure:** No JWT validation → fail; no polling fallback → fail.
  - **Commit:** `feat(realtime): wire websocket broadcasts and polling fallback`

- [x] 17. Implement idempotent seed scenario with full demo data
  - **References:** `backend/app/seed/seed_demo.py:34-59` (remove ensure_columns call), `backend/app/seed/db_setup.py:16-79` (remove — migration handles columns), `backend/app/seed/entities.py:1-227`, `backend/app/seed/observations.py:1-239`, `backend/app/seed/hypotheses.py:1-122`, `backend/app/seed/scenarios.py:1-94`, `backend/app/seed/ids.py:1-41`, `backend/app/auth/seed.py:1-83` (6 users), prompt §7.7
  - **Acceptance:** (a) Remove `ensure_columns()` call from seed_demo.py; (b) **Reconcile ORG_ID**: `seed/ids.py:39` has `ORG_ID = "demo_org"` but `auth/seed.py:18` has `DEMO_ORG_ID = "org_demo"` — change `seed/ids.py` to use `ORG_ID = "org_demo"` so demo users and demo observations share the same org; (c) Add rescue-ball device seed (2 simulated devices as Sensor rows); (d) Ensure 6 demo users seeded; (e) Add 1 draft trapped-person alert; (f) Add 1 proposed action (recommendation); (g) Add 1 assigned task; (h) Add population/vulnerability data to zone properties; (i) Running twice → identical row counts (delete-then-insert by org_id+incident_id); (j) `clean_demo_data` deletes from all tables including new ones (alerts, recommendations, incidents if demo-scoped).
  - **QA happy:** `python -m app.seed.seed_demo` twice → identical counts; `SELECT count(*) FROM observations WHERE org_id='org_demo'` = 50 both times; rescue-ball devices in sensors table; alert + task exist.
  - **QA failure:** Second run doubles counts → fail; ensure_columns still called → fail; no alert/task → fail.
  - **Commit:** `feat(seed): idempotent demo scenario with rescue-ball devices and alerts`

- [x] 18. Implement situation report, incident, entity, and audit API routes
  - **References:** `backend/app/models/incident.py` (todo 4), `backend/app/audit/provenance.py:1-194` (REAL), `backend/app/lib/audit.py:1-120` (REAL), `backend/app/models/entities.py:29-186`, `backend/app/perception/llm.py:1-276` (LLM for prose), prompt §7.8, prompt §7.1
  - **Acceptance:** (a) `GET /api/incidents/{id}/situation-report?format=text|json` — JSON includes: incident status, data freshness, active hazards, hypotheses, contradictions, affected infrastructure, shelters, open tasks, alerts, resource status, known unknowns, provenance links; LLM prose has `review_status: draft` + evidence links; LLM disabled → structured data only; (b) Incident CRUD: `GET /api/incidents`, `POST /api/incidents`, `GET /api/incidents/{id}`, `PATCH /api/incidents/{id}` (geometry as GeoJSON); (c) Entity routes: `GET /api/incidents/{id}/entities?type=zones|roads|shelters|hospitals|teams|vehicles|sensors` (GeoJSON FeatureCollection, bbox filter); `PATCH /api/entities/{type}/{id}` (status/location update, broadcast); (d) Audit: `GET /api/incidents/{id}/audit-logs` (paginated), `GET /api/decisions/{rec_id}/provenance`, `GET /api/audit/verify?incident_id=X` (hash chain verification). All org_id+incident_id tenancy enforced. Split into separate route files if >250 LOC each.
  - **QA happy:** Situation report JSON has all fields; LLM-disabled report still works; entity routes return GeoJSON; audit verify returns valid.
  - **QA failure:** LLM prose without evidence → fail; WKT in response → fail; cross-org visible → fail.
  - **Commit:** `feat(api): implement situation report, incident, entity, and audit routes`

- [x] 19. Gate B checkpoint — verify Phase 1 API
  - **References:** All Wave 2 todos, prompt §12 Gate B
  - **Acceptance:** Run: `docker compose exec backend python -m app.seed.seed_demo` (idempotent); `curl -X POST /api/auth/login -d "username=admin@demo.disaster&password=demo1234"` (JWT); `curl /api/auth/me` (user); `curl /api/incidents` (incidents); `curl '/api/observations?incident_id=X&bbox=...'` (filtered); start simulator → `rpk topic consume observations.raw` (messages); wait 10s → `SELECT count(*) FROM observations` (increased); `GET /api/incidents/X/hypotheses` (hypotheses with confidence); insert corroborated thermal observation → `GET /api/incidents/X/alerts` (draft alert); `POST .../alerts/{id}/approve` → task created; `GET /api/incidents/X/audit-logs` (audit entry). Record evidence in `evidence/gate-b/`.
  - **QA happy:** All checks pass.
  - **QA failure:** Any check fails → block Wave 3.
  - **Commit:** `test(gate-b): verify phase one api gate`

### Wave 3 — Gate C: Frontend

- [x] 20. Build frontend: routing, auth context, typed API client, TanStack Query
  - **References:** `frontend/src/App.tsx:1-5`, `frontend/src/main.tsx:1-10`, `frontend/package.json:11-31` (react-router-dom + @tanstack/react-query unused), `frontend/vite.config.ts:1-11`
  - **Acceptance:** (a) `main.tsx` wraps app in `BrowserRouter` + `QueryClientProvider`; (b) `src/api/client.ts` — typed API client with baseURL from `VITE_API_BASE`, JWT in memory + localStorage, typed methods for all endpoints (generate types from FastAPI `/openapi.json` or hand-type matching backend schemas); (c) `src/auth/AuthContext.tsx` — `user`, `login()`, `logout()`, `isAuthenticated`; (d) `App.tsx` — React Router with routes: `/login`, `/dashboard`, `/hypotheses`, `/planning`, `/simulation`, `/field`, `/devices/:id`, `/audit`; (e) protected routes redirect to `/login`; (f) reusable `LoadingState`, `EmptyState`, `ErrorState`, `StaleState`, `OfflineState` components; (g) all interactive elements have ARIA labels; (h) `npm run build` succeeds.
  - **QA happy:** Build succeeds; unauthenticated `/dashboard` → redirect to `/login`; after login → dashboard loads.
  - **QA failure:** Build fails → fail; unauthenticated access → fail; no ARIA labels → fail.
  - **Commit:** `feat(ui): add routing, auth context, typed api client, tanstack query`

- [x] 21. Build situation dashboard with map
  - **References:** `frontend/src/components/MapView.tsx:1-198` (enhance), `frontend/src/components/mapLayers.ts:1-238`, `frontend/src/hooks/useMapLayers.ts:1-207` (replace mock with real API), `frontend/src/types/map.ts:1-224`, `scripts/offline_prep.sh:44-70` (PMTiles)
  - **Acceptance:** (a) Dashboard renders MapView with all layers: incident boundary, flood/hazard, rescue-ball path + current location, thermal detections, observations, blocked/dangerous roads, shelters + capacity, hospitals, teams, tasks, alerts, infrastructure; (b) Replace mock data with real API via TanStack Query; (c) Try local PMTiles (`/basemaps/rivertown.pmtiles`), fallback to simple vector style (background color + labels) if PMTiles unavailable — run `scripts/offline_prep.sh` step 2 as part of `make bootstrap`; (d) Stale layers visually distinct (grayscale/opacity); (e) Conflicting observations visible separately; (f) uncertainty + data-age indicators; (g) no commercial map key required.
  - **QA happy:** Dashboard shows seeded data from real API; stale observations visually distinct; no external map tiles loaded (check Network tab).
  - **QA failure:** Online tiles used → fail; stale looks same as fresh → fail; conflicts merged → fail.
  - **Commit:** `feat(ui): implement command center map with real data and local basemap`

- [x] 22. Build action cards, hypothesis view, and planning view
  - **References:** `frontend/src/components/ActionCard.tsx:1-250` (enhance), prompt §8 (action card fields), prompt §7.3 (hypothesis display)
  - **Acceptance:** (a) ActionCard shows: proposed action, objective, benefit range, urgency, required resources, supporting evidence, contradicting evidence, assumptions, uncertainty, alternatives, failure contingency, equity impact, approve/modify/dismiss controls — all from real API; (b) Hypothesis page: list with supporting/contradicting evidence, data age, uncertainty; (c) Planning page: action proposals with approve/modify/dismiss; (d) approve/dismiss calls real API; (e) success toast after approval; (f) task appears in task list.
  - **QA happy:** Planning page shows seeded alert; approve calls API; task appears.
  - **QA failure:** Missing equity impact → fail; approve doesn't call API → fail.
  - **Commit:** `feat(ui): implement action cards, hypothesis and planning views`

- [x] 23. Build simulation, field responder, device detail, and audit views
  - **References:** prompt §8 (pages), prompt §7.6 (field responder)
  - **Acceptance:** (a) Simulation page: start/stop/pause/resume, speed slider, device list, telemetry display, fault injection buttons, "SIMULATED DATA" banner; (b) Field responder: mobile-first (renders correctly at 375px, touch targets ≥44px, no horizontal scroll), assigned tasks, quick report form (category, geolocate, urgency, description, optional photo/water_depth/people), mark road blocked/open, update task status, optimistic UI; (c) Device detail: device state, battery, signal, sensor status, path history, last-seen, "SIMULATED DATA" label; (d) Audit: hash-chained event log, provenance chain viewer, verify chain button; (e) all pages have loading/empty/error/stale/offline states.
  - **QA happy:** Simulation starts via API; field responder at 375px renders correctly; task status update reflects on dashboard via WebSocket.
  - **QA failure:** Missing simulation banner → fail; field responder not mobile-first → fail; no offline state → fail.
  - **Commit:** `feat(ui): implement simulation, field responder, device, and audit views`

- [x] 24. Gate C checkpoint — verify frontend
  - **References:** All Wave 3 todos, prompt §12 Gate C
  - **Acceptance:** `cd frontend && npm ci && npm run build` (build); Playwright login flow; map renders seeded data (check for deck.gl canvas + layer elements); simulator moves (device position changes on map); alert appears (check for alert element); operator approves (click approve button); task appears in field view; task update reaches command centre (WebSocket event received); polling fallback works (disable WebSocket, verify polling gets events). Record Playwright screenshots in `evidence/gate-c/`.
  - **QA happy:** All checks pass.
  - **QA failure:** Any check fails → block Wave 4.
  - **Commit:** `test(gate-c): verify frontend gate`

### Wave 4 — Gate D: Offline

- [x] 25. Implement PWA manifest, service worker, and app-shell caching
  - **References:** prompt §9, `frontend/index.html:1-12`, `frontend/vite.config.ts:1-11`
  - **Acceptance:** (a) `frontend/public/manifest.json` — PWA manifest (name, icons, theme_color, display: standalone); (b) Service worker registered in `main.tsx`, caches app shell (HTML/CSS/JS) on install, serves from cache offline; (c) local basemap cached by SW; (d) `npm run build` generates SW + manifest.
  - **QA happy:** DevTools > Application > Service Workers shows SW; DevTools > Network > Offline → app shell loads from cache.
  - **QA failure:** No manifest → fail; app doesn't load offline → fail.
  - **Commit:** `feat(offline): add pwa manifest, service worker, and app-shell caching`

- [x] 26. Implement IndexedDB outbox and conflict-aware replay
  - **References:** prompt §9, `backend/app/realtime/edge_sync.py:1-267` (REAL), `backend/app/realtime/sync.py:1-275` (REAL), `backend/app/lib/idempotency.py:61-74`
  - **Acceptance:** (a) `frontend/src/lib/outbox.ts` — IndexedDB outbox storing pending mutations with content hash, timestamp, priority; (b) online → direct API; offline → outbox; (c) pending count badge in UI; (d) on reconnect → sync in priority order (text > coordinates > task_state > imagery); (e) idempotency key per item; (f) conflict policy: last-write-wins for non-critical, manual resolution for critical — audit the resolution; (g) no silent discard.
  - **QA happy:** Offline → create observation + update task → both "pending"; online → both sync; observation on dashboard; task updated; re-sync → no duplicate.
  - **QA failure:** Offline mutation lost → fail; duplicate on re-sync → fail; conflict silently overwritten → fail.
  - **Commit:** `feat(offline): add indexeddb outbox and conflict-aware replay`

- [x] 27. Implement feed-health tracking and low-bandwidth mode
  - **References:** `backend/app/api/routes/health.py:44-226` (REAL FeedHealthTracker), `backend/app/comms/fallback.py:1-289` (REAL), prompt §9 step 8 (data age shown during outage)
  - **Acceptance:** (a) Dashboard shows feed-health indicators per source (healthy/degraded/down with data age); (b) Low-bandwidth toggle: reduces polling from 2s to 30s, strips map imagery, text-first payloads; (c) Stale/degraded visually distinct on map; (d) During outage: dashboard shows "data stale" or "unavailable" indicators, not current timestamps pretending to be fresh; (e) **Register `health.router` in `main.py`** — the FeedHealthTracker endpoints (`/api/incidents/{id}/feed-health`, `/api/incidents/{id}/degradation-summary`) in `backend/app/api/routes/health.py` are currently NOT included in `main.py`; add `from app.api.routes.health import router as health_router` and `api_router.include_router(health_router)` to `main.py`.
  - **QA happy:** No observations for 60s (tau=60s phenomenon) → "degraded"; low-bandwidth reduces requests; outage shows stale indicator.
  - **QA failure:** Stale data displayed as current → fail; low-bandwidth toggle missing → fail.
  - **Commit:** `feat(offline): add feed-health tracking and low-bandwidth mode`

- [x] 28. Gate D checkpoint — verify offline
  - **References:** All Wave 4 todos, prompt §12 Gate D, prompt §9 (8-step demonstration)
  - **Acceptance:** Run the 8-step offline demonstration: (1) responder opens field interface online; (2) connectivity disabled; (3) responder records observation + changes task status; (4) changes show as "pending"; (5) connectivity returns; (6) outbox syncs without duplication; (7) command centre receives updates; (8) data age + unavailable capabilities shown during outage. Record evidence in `evidence/gate-d/`. Also: `docker compose down` for ollama/prometheus/grafana → core stack still boots.
  - **QA happy:** All 8 steps pass.
  - **QA failure:** Any step fails → block Wave 5.
  - **Commit:** `test(gate-d): verify offline gate`

### Wave 5 — Gate E: SOTA, Testing, Automation, Docs

- [x] 29. Replace SQLite test infrastructure with PostgreSQL/PostGIS
  - **References:** `backend/tests/conftest.py:14` (SQLite), `backend/tests/test_ogc_adapter.py:33-53` (ALTER TABLE), prompt §11
  - **Acceptance:** (a) `conftest.py` — use `DATABASE_URL` env var pointing to Docker PostgreSQL test DB; (b) `alembic upgrade head` in test setup (not `create_all`); (c) remove all `ALTER TABLE` workarounds from test files; (d) remove `ensure_table()` calls from tests; (e) fresh schema per test session; (f) `pytest-asyncio` configured.
  - **QA happy:** `pytest -q` runs against PostgreSQL; `grep -r "create_all\|ensure_table\|ALTER TABLE" backend/tests/` → zero.
  - **QA failure:** SQLite used → fail; ALTER TABLE remains → fail.
  - **Commit:** `test(infra): replace sqlite with postgresql postgis integration tests`

- [x] 30. Add Phase 1 integration tests
  - **References:** prompt §11 (test list)
  - **Acceptance:** New test files: `test_tenant_isolation.py`, `test_role_denial.py`, `test_geometry_roundtrip.py`, `test_invalid_bbox.py`, `test_concurrent_idempotency.py`, `test_migration_correctness.py`, `test_audit_tampering.py`, `test_stale_data.py`, `test_contradictions.py`, `test_worker_restart.py`, `test_dlq.py`, `test_websocket_fallback.py`, `test_seed_idempotency.py`, `test_simulator_determinism.py`, `test_low_connectivity.py` (degraded mode when Redpanda/Redis unavailable). All real assertions, no `assert True`, no mocking SUT.
  - **QA happy:** `pytest backend/tests/test_tenant_isolation.py backend/tests/test_role_denial.py backend/tests/test_geometry_roundtrip.py backend/tests/test_invalid_bbox.py backend/tests/test_concurrent_idempotency.py backend/tests/test_migration_correctness.py backend/tests/test_audit_tampering.py backend/tests/test_stale_data.py backend/tests/test_contradictions.py backend/tests/test_worker_restart.py backend/tests/test_dlq.py backend/tests/test_websocket_fallback.py backend/tests/test_seed_idempotency.py backend/tests/test_simulator_determinism.py backend/tests/test_low_connectivity.py -v` all pass.
  - **QA failure:** Any test is fake/tautological → fail.
  - **Commit:** `test(phase1): add integration tests for all phase one scenarios`

- [x] 31. Add frontend testing: typecheck, lint, unit, Playwright e2e
  - **References:** `frontend/package.json:6-9`, `frontend/playwright.config.ts:1-27`, prompt §11, prompt §12 Gate C
  - **Acceptance:** (a) `package.json` scripts: `typecheck` (`tsc --noEmit`), `lint` (`eslint src/`), `test` (`vitest run`); (b) Install eslint, @typescript-eslint/*, vitest, @testing-library/react, jsdom; (c) Unit tests for API client, auth context, outbox; (d) Playwright e2e: login, dashboard map renders seeded data, simulator moves, alert appears, operator approves, task in field view, task update reaches command centre (WebSocket), polling fallback. Prerequisite: `docker compose up -d --build --wait && docker compose exec backend python -m app.seed.seed_demo` before Playwright (NOT `make bootstrap` — the Makefile is created in todo 37). (e) `npm run typecheck && npm run lint && npm run test && npm run build` all pass. (f) `npx playwright test` passes. (g) No test uses mock data exclusively.
  - **QA happy:** `cd frontend && npm run typecheck && npm run lint && npm run test && npm run build && npx playwright test` all exit 0.
  - **QA failure:** TypeScript errors → fail; test uses mock exclusively → fail.
  - **Commit:** `test(frontend): add typecheck, lint, vitest, and playwright e2e`

- [x] 32. Wire SOTA fusion and perception to API routes
  - **References:** `backend/app/fusion/world_state.py:1-265` (REAL DBN), `backend/app/fusion/calibration.py:1-292` (REAL MAPIE), `backend/app/perception/serving.py:1-258` (REAL ONNX), `backend/app/perception/flood_mapping.py:1-292`, `backend/app/perception/ensemble.py:1-228`, `backend/app/perception/nlp.py:1-280`, `backend/app/perception/damage.py:1-321`, `backend/app/api/routes/scenarios.py:1-14` (STUB), `backend/app/api/routes/sensing.py:1-14` (STUB), `backend/app/api/routes/eval.py:1-14` (STUB)
  - **Acceptance:** (a) Replace scenarios stub: `GET /api/incidents/{id}/scenarios` (best/expected/worst from ScenarioGenerator); (b) Replace sensing stub: `GET /api/incidents/{id}/sensing-actions` (EVI-ranked), `POST .../sensing-actions/{id}/dispatch` (pending task); (c) Replace eval stub: `POST /api/eval/run` (testbed), `GET /api/eval/results/{task_id}`; (d) `GET /api/incidents/{id}/world-state` (DBN state); (e) `GET /api/incidents/{id}/calibration` (Brier/ECE/coverage); (f) **Heavy ML features**: deterministic fixture tests, cached sample data in `backend/data/`, optional model packs via download script, "model unavailable" degraded behavior for ALL ML features (flood mapping, ensemble, damage, NLP) — not just one; (g) rescue ball added as sensing resource in `SensingActionCatalog`.
  - **QA happy:** Scenarios endpoint returns 3 scenarios; sensing-actions returns ranked actions; all ML endpoints degrade gracefully when weights missing (test each: flood_mapping, ensemble, damage, nlp).
  - **QA failure:** Stub remains → fail; missing model crashes → fail; rescue ball not in catalog → fail.
  - **Commit:** `feat(sota): wire fusion and perception engines to api`

- [x] 33. Wire SOTA optimizer, twin, evaluation, privacy/ABAC, and fairness to API
  - **References:** `backend/app/optimizer/engine.py:58-278`, `backend/app/optimizer/api.py:1-138` (existing optimize route at `/api/optimize` — already included in `main.py:180`), `backend/app/api/routes/optimize.py:1-9` (re-exports optimizer router), `backend/app/optimizer/fairness.py:1-190`, `backend/app/twin/cascading.py:1-190`, `backend/app/twin/silence.py:1-146`, `backend/app/auth/abac.py:1-229` (REAL ABAC), `backend/app/lib/privacy.py` (REAL progressive precision), `backend/app/audit/provenance.py:1-194`
  - **Acceptance:** (a) Modify existing `/api/optimize` route (or add `/api/incidents/{id}/optimize`) to return assignments + alternatives + trade-offs (not opaque command); infeasible → explanation; (b) `GET /api/incidents/{id}/cascade` (blast radius); (c) `GET /api/incidents/{id}/silence` (telecom silence); (d) `GET /api/incidents/{id}/fairness-report` (equity report from `FairnessEngine.compute_equity_report()`); (e) ABAC enforcement: `GET /api/incidents/{id}/access-check?action=X&resource=Y` returns allowed/denied with jurisdiction/sensitivity/override reasoning; (f) Progressive precision: coordinates rounded by user role (viewer → ~1km, field_responder → ~100m, admin → exact); (g) Privacy: PII redaction on citizen reports by default; (h) Eval: ablation endpoint (`POST /api/eval/ablation`), baselines (`POST /api/eval/baselines`); (i) Tests do NOT guarantee system wins by construction — use meaningful scenarios with transparent assumptions.
  - **QA happy:** Optimize returns alternatives + trade-offs; infeasible returns explanation; fairness-report returns equity data; access-check returns ABAC reasoning; viewer sees ~1km-precision coordinates.
  - **QA failure:** Opaque single command → fail; no fairness endpoint → fail; no ABAC endpoint → fail; tests tautological → fail.
  - **Commit:** `feat(sota): wire optimizer, twin, privacy, fairness to api`

- [x] 34. Add social media ingestion adapters (X/Twitter, Reddit, Instagram, YouTube)
  - **References:** Existing adapter pattern: `backend/app/ingestion/adapters/sensorthings.py:30-60` (SensorThingsClient pattern), `backend/app/models/enums.py:6-16` (SourceType.social_media already exists), `backend/app/models/source.py:22-33` (SourceKind.social_media already exists), `backend/app/streaming/producer.py:19-68` (ProducerManager for publishing), `backend/app/perception/nlp.py:1-280` (NLP pipeline for text processing), `backend/app/perception/llm_safety.py:1-305` (PII redaction), `backend/app/lib/idempotency.py:61-74` (check_and_record). API research: X API v2 uses Bearer Token auth, `GET /2/tweets/search/stream` with `point_radius`/`bounding_box` geo operators, place-level bounding boxes (no exact lat/lon), `tweepy` SDK, $0.005/post read. Reddit uses OAuth2, PRAW library, 100 QPM, NO geolocation. Instagram Graph API uses OAuth2 via Facebook Login, hashtag search only (`GET /ig_hashtag_search` + `GET /{id}/recent_media`), NO geolocation (removed v22 May 2025), `facebook-business` SDK. YouTube Data API v3 uses API key, `search.list` with `location`+`locationRadius`, `recordingDetails` deprecated, `google-api-python-client`, 10,000 units/day.
  - **Acceptance:** New adapter files under `backend/app/ingestion/adapters/` (each <250 LOC). NOTE: these adapters follow a publish-to-Kafka pattern (via `ProducerManager.send`), NOT the direct-DB-insert pattern used by `sensorthings.py`. (a) `twitter.py` — `TwitterAdapter` with `TwitterClient` class: Bearer Token auth from `Source.config["bearer_token"]`, `pull_observations()` uses tweepy `StreamingClient` or `GET /2/tweets/search/recent`, filters by keywords + `point_radius`/`bounding_box` from incident geometry, maps tweets to observations with `source_type=social_media`, `geometry` from Place bounding box centroid, `provenance_chain={"platform":"twitter","tweet_id":...}`, `access_policy=sensitive`, `corroboration_state=uncorroborated`; idempotency via tweet ID; degrades gracefully (returns empty, logs warning) when bearer token missing; (b) `reddit.py` — `RedditAdapter` with PRAW: OAuth2 from `Source.config`, monitors disaster subreddits (`r/emergency+r/weather+...`), `subreddit.stream.submissions()`, maps posts to observations with `geometry=None` (no geo — NLP extracts location from text), same provenance/access/corroboration pattern; idempotency via post ID; (c) `instagram.py` — `InstagramAdapter` with `facebook-business` SDK or `requests`: OAuth2 from `Source.config`, hashtag search (`GET /ig_hashtag_search` + `GET /{id}/recent_media`), maps posts to observations with `geometry=None` (geo removed v22), processes caption through NLP for location extraction; idempotency via media ID; (d) `youtube.py` — `YouTubeAdapter` with `google-api-python-client`: API key from `Source.config`, `search.list` with `location`+`locationRadius` from incident geometry + `publishedAfter` for recent disasters, `videos.list` with `recordingDetails` for geo (partial), maps videos to observations; idempotency via video ID; (e) All adapters publish to `observations.raw` via `ProducerManager`; (f) All text content processed through `perception/nlp.py` for urgency, category, PII redaction before storage; (g) `GET /api/sources` lists registered social media sources with status; (h) `POST /api/incidents/{id}/ingest/social-media` triggers manual pull; (i) Add `tweepy`, `praw`, `facebook-business`, `google-api-python-client` to `requirements.txt` (optional — adapters degrade without them); (j) Each adapter has fixture-based tests with mock HTTP responses (no real API calls in tests).
  - **QA happy:** Register a Twitter source with a mock bearer token → `POST /api/incidents/X/ingest/social-media?source_type=twitter` returns 202; mock tweet fixture produces an observation with `source_type=social_media` and `access_policy=sensitive`; PII in tweet text is redacted before storage; adapter returns empty gracefully when credentials missing.
  - **QA failure:** Adapter crashes when API key missing → fail; PII not redacted → fail; observation has `access_policy=public` → fail; file >250 LOC → fail.
  - **Commit:** `feat(ingestion): add social media adapters for twitter, reddit, instagram, youtube`

- [x] 35. Add event detection and unified communication adapters (Event Registry, Ayrshare, Unipile)
  - **References:** Same adapter pattern as todo 34. Event Registry API: API key auth, `GET /api/v1/minuteStreamArticles` (poll 1/min for real-time), `GET /api/v1/minuteStreamEvents`, `locationUri` for geo filtering, `sentiment` field, `eventregistry` Python SDK, free 2,000 tokens. Ayrshare API: Bearer token, `POST /api/post` (publish to 13 networks), `social-post-api` Python package, $149/month min. Unipile API: `X-API-KEY` header + DSN, `POST /api/v1/chats/{id}/messages` (send), webhook `message.new` (receive), REST only (no Python SDK), €49/month min. `backend/app/comms/fallback.py:1-289` (existing low-bandwidth fallback), `backend/app/realtime/manager.py:1-172` (broadcast).
  - **Acceptance:** New adapter files under `backend/app/ingestion/adapters/` (each <250 LOC): (a) `event_registry.py` — `EventRegistryAdapter` with `eventregistry` SDK: API key from `Source.config`, `GetRecentArticles` polled every 60s, `mandatorySourceLocation=True` for geo-located articles, `keywords` filter for disaster terms, maps articles to observations with `source_type=official_feed`, `geometry` from article location, `quality_flags.sentiment` from article sentiment score; idempotency via article URI; (b) `ayrshare.py` — `AyrshareClient` (outbound): Bearer token from `Source.config`, `POST /api/post` to broadcast emergency alerts to 13 social networks simultaneously, `POST /api/comments` for community engagement, `GET /api/analytics/{id}` for engagement metrics; used by alert workflow (todo 14) to broadcast approved alerts; (c) `unipile.py` — `UnipileClient` (inbound messaging): `X-API-KEY` from `Source.config`, webhook endpoint `POST /api/webhooks/unipile` receives `message.new` events, maps incoming DMs to observations with `source_type=citizen_report`, `geometry=None` (no geo — NLP extracts from text), `access_policy=sensitive`; `POST /api/incidents/{id}/messages/send` sends targeted response messages via WhatsApp/Telegram; (d) All adapters degrade gracefully when credentials unavailable; (e) Add `eventregistry`, `social-post-api` to `requirements.txt` (optional); (f) Fixture-based tests with mock responses.
  - **QA happy:** Register Event Registry source → `POST /api/incidents/X/ingest/event-registry` returns 202; mock article fixture produces observation with sentiment; Ayrshare `POST /api/alerts/{id}/broadcast` publishes to configured platforms; Unipile webhook receives mock DM → observation created with `source_type=citizen_report`; all degrade gracefully without credentials.
  - **QA failure:** Adapter crashes without credentials → fail; Unipile DM not PII-redacted → fail; file >250 LOC → fail.
  - **Commit:** `feat(ingestion): add event registry, ayrshare, and unipile adapters`

- [x] 36. Add structured logging, OpenTelemetry, and dependency locks
  - **References:** `backend/app/lib/telemetry.py`, `backend/app/middleware/request_id.py:1-33`, `backend/app/middleware/org_context.py:1-39`, `backend/requirements.txt:1-40` (>= pins), `frontend/package-lock.json` (exists), prompt §5.3
  - **Acceptance:** (a) Structured JSON logging with: timestamp, level, request_id, trace_id, org_id, incident_id, message, safe_error_context; (b) context vars from middleware; (c) OpenTelemetry traces (exporter from env or `OTEL_EXPORTER=none`); (d) no secrets logged (`grep -r "password\|secret\|token" backend/app/ --include="*.py" | grep "logger\.\|log\."` → zero); (e) `backend/requirements.lock` with pinned `==` versions (or `pip-compile` output); (f) `backend/Dockerfile` uses lock file; (g) `frontend/Dockerfile` uses `npm ci`; (h) run `pip-audit` and `npm audit` (where locally available).
  - **QA happy:** API request logs contain request_id + org_id; no secrets; `docker compose build` deterministic; `pip-audit` runs (warnings OK, no crashes).
  - **QA failure:** Secret in logs → fail; npm install instead of npm ci → fail.
  - **Commit:** `feat(observability): add structured logging, otel, and dependency locks`

- [x] 37. Add Makefile, automation scripts, and reduced-resource profile
  - **References:** prompt §13, `scripts/offline_prep.sh`, `docker-compose.yml:103-229` (ollama/prometheus/grafana), `grafana/provisioning/` (exists)
  - **Acceptance:** (a) `Makefile` with targets: `bootstrap`, `migrate`, `seed`, `test`, `lint`, `typecheck`, `build` (`cd frontend && npm run build`), `demo`, `verify`; (b) `scripts/demo_phase1.sh`: reset demo state, seed, start simulator, wait for observations, validate draft alert, call demo approval endpoint, validate task, print URLs + IDs, exit nonzero on failure; (c) docker-compose: `ollama`, `prometheus`, `grafana` have `profiles: ["full"]`; `docker compose up` starts 8 core services; `docker compose --profile full up` starts 11; (d) Grafana provisioning mounted and verified (dashboard loads).
  - **QA happy:** `make bootstrap && make migrate && make seed && make test && make build && make demo` all succeed; `docker compose up -d` starts 8 services; Grafana shows dashboard.
  - **QA failure:** Any target fails → fail; ollama starts without profile → fail.
  - **Commit:** `feat(automation): add makefile, demo script, and reduced-resource profile`

- [x] 38. Update documentation: README, env, architecture, security, limitations
  - **References:** `README.md:1-49`, `.env.example:1-38`, prompt §14
  - **Acceptance:** (a) `README.md` updated (quick start, architecture, testing, demo); (b) `.env.example` updated with all new vars; (c) `docs/PHASE1_DEMO.md` (step-by-step demo); (d) `docs/SIMULATOR.md` (usage, CLI, API, seed, fault injection, simulation disclaimer); (e) `docs/OFFLINE_OPERATION.md` (PWA, outbox, reconciliation, conflict policy); (f) `docs/SECURITY_MODEL.md` (auth, RBAC, ABAC, tenancy, JWT, emergency override, PII redaction); (g) `docs/KNOWN_LIMITATIONS.md` with ALL 6 required disclaimers as separate sections: (1) rescue ball is simulated, (2) physical deployment/landing not validated, (3) simulated thermal not certified human detection, (4) no medical/emergency authority reliance, (5) ML depends on available weights/calibration, (6) local demo ≠ real disaster performance.
  - **QA happy:** All 6 docs exist with substantive content; KNOWN_LIMITATIONS has all 6 disclaimers as separate sections; README has working quick start.
  - **QA failure:** Any doc missing → fail; KNOWN_LIMITATIONS missing any disclaimer → fail.
  - **Commit:** `docs: update readme, add all required documentation`

- [x] 39. Implement blocker handling protocol
  - **References:** prompt §16 (6-step protocol), `backend/app/perception/serving.py:1-258` (model availability), `backend/app/perception/llm.py:1-276` (LLM availability)
  - **Acceptance:** (a) Each external dependency (ONNX models, Ollama LLM, PMTiles basemap, model weights) has a `GET /api/capabilities` endpoint returning `{"feature": "...", "status": "available|degraded|unavailable", "activation_steps": "..."}`; (b) Safe degraded behavior implemented for each: ONNX → "model_unavailable" response, LLM → structured-data-only report, PMTiles → vector fallback; (c) `scripts/download_models.py` (already exists) documented with licensing; (d) blockers documented in `docs/KNOWN_LIMITATIONS.md`; (e) system continues with unblocked work when a blocker is hit.
  - **QA happy:** `GET /api/capabilities` returns status for each feature; stopping Ollama → LLM features degrade gracefully; system doesn't crash.
  - **QA failure:** Missing model crashes → fail; no capabilities endpoint → fail.
  - **Commit:** `feat(resilience): implement blocker handling protocol with capability status`

- [x] 40. Produce final report and reconcile active-plan checkboxes
  - **References:** prompt §17 (10-item final report), prompt §4 (active-plan reconciliation)
  - **Acceptance:** `docs/FINAL_REPORT.md` containing: (1) branch + commit list (`git log --oneline codex/resqnet-phase1-completion`); (2) implemented milestones; (3) architecture decisions; (4) database revisions added (list migrations 0002a, 0002b, 0003, 0004); (5) exact verification commands + results; (6) Phase 1 demo steps; (7) Playwright evidence paths (`evidence/gate-c/`); (8) test + coverage summaries (`pytest --tb=short -q` output, `npm run test` output); (9) remaining optional dependencies (model weights, Ollama, PMTiles); (10) incomplete features with reasons. Reconcile active-plan checkboxes against fresh evidence (rerun relevant tests, don't trust stale state).
  - **QA happy:** All 10 items present in FINAL_REPORT.md; active-plan checkboxes match fresh test evidence.
  - **QA failure:** Missing any of 10 items → fail; checkboxes not reconciled → fail.
  - **Commit:** `docs(report): add final report and reconcile plan checkboxes`

- [x] 41. Gate E checkpoint — verify SOTA
  - **References:** All Wave 5 todos, prompt §12 Gate E
  - **Acceptance:** Run: all fusion tests pass (confidence_vector, reliability, calibration, world_state, freshness); all perception tests pass (llm, nlp, flood_mapping, damage, ensemble, serving); all twin tests pass (scenarios, cascading, silence); all optimizer tests pass (engine, constraints, fairness, routing, replan); all sensing tests pass (evi, catalog); all privacy tests pass (abac, privacy, llm_safety); all eval tests pass (testbed, metrics, failures, baselines, ablation). All against PostgreSQL. Record evidence in `evidence/gate-e/`.
  - **QA happy:** All SOTA tests pass.
  - **QA failure:** Any SOTA test fails → block.
  - **Commit:** `test(gate-e): verify sota gate`

## Final verification wave

- [x] F1. Plan compliance audit — verify every §1-17 requirement has a completed todo; verify no stub API responses remain; verify all gates A-E pass.
  - **References:** This plan, prompt §1-17. Depends on: all todos including 39.
  - **Acceptance:** `grep -r "status.*ok.*endpoint\|stub\|placeholder\|not implemented" backend/app/api/routes/ --include="*.py"` → zero; all gate evidence files exist in `evidence/`.
  - **QA:** Run `make verify`; nonzero exit → fail.
  - **Commit:** `verify(compliance): audit all requirements against completed todos`

- [x] F2. Code quality review — ruff + mypy + eslint + tsc strict on all changed code.
  - **References:** `backend/`, `frontend/`
  - **Acceptance:** `cd backend && ruff check . && mypy app/` exits 0; `cd frontend && npm run typecheck && npm run lint` exits 0. No type weakening (check diff for `any` additions).
  - **QA:** Any error → fail.
  - **Commit:** `verify(quality): code quality review passes`

- [x] F3. Real manual QA via Playwright — run full demo with assertions.
  - **References:** `scripts/demo_phase1.sh`, `docs/PHASE1_DEMO.md`. Prerequisite: `make bootstrap && make seed`.
  - **Acceptance:** `make demo` succeeds; Playwright asserts: `expect(page.locator('[data-testid="observation-marker"]')).toBeVisible()` (observations on map); `expect(page.locator('[data-testid="alert-card"]')).toBeVisible()` (alert appears); `page.click('[data-testid="approve-button"]')` (operator approves); `expect(page.locator('[data-testid="task-card"]')).toBeVisible()` (task in field view); offline: `page.context.setOffline(true)` → `expect(page.locator('[data-testid="pending-badge"]')).toBeVisible()` → `page.context.setOffline(false)` → `expect(page.locator('[data-testid="synced-badge"]')).toBeVisible()`.
  - **QA:** Any assertion fails → fail.
  - **Commit:** `verify(qa): manual qa passes via playwright assertions`

- [x] F4. Scope fidelity — verify no unrequested features; Must-NOT-Have respected.
  - **References:** This plan's Scope OUT section
  - **Acceptance:** `git diff main -- platform/` empty; `grep -r "random\." backend/app/ --include="*.py" | grep -v test | grep -v simulator | grep -v eval | grep -v __pycache__` → zero; no LLM dispatches commands autonomously; no fabricated accuracy claims.
  - **QA:** Any violation → fail.
  - **Commit:** `verify(scope): scope fidelity check passes`

## Commit strategy

Conventional commits, one per todo. Branch: `codex/resqnet-phase1-completion`. Do NOT push to main. Push branch and open draft PR only after all Phase 1 gates pass. If GitHub credentials unavailable: leave branch + commits locally, report that publishing was unavailable. Pre-commit: run relevant focused tests + type checks + inspect diff for secrets/large files.

## Success criteria

- `docker compose up -d --build --wait` starts all core services reproducibly
- `alembic upgrade head` succeeds from empty DB and from 0001
- No `create_all()` or `ensure_table()` in production code paths
- All API routes return real data (no stubs)
- `make demo` runs the full Phase 1 loop: seed → simulator → observations → confidence → hypothesis → alert → approval → task → map
- Frontend `npm run build` + `npx playwright test` pass
- Offline PWA loads from cache, outbox syncs on reconnect
- All backend tests pass against PostgreSQL/PostGIS
- Documentation reflects actual implementation
- `KNOWN_LIMITATIONS.md` honestly states simulation boundaries
- Privacy/ABAC and fairness endpoints exist (Gate E requirement)
- Active-plan checkboxes reconciled only after fresh evidence
- Final report (§17) produced with all 10 items
