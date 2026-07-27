---
slug: resqnet-sage
status: review-complete
intent: clear
review_required: true
pending-action: none (plan ready for execution)
review:
  momus:
    status: approved
    target: .omo/plans/resqnet-sage.md
    verdict: OKAY — 2 minor non-blocking notes (routing.py line number, column count)
  independent:
    status: approved-after-fixes
    target: .omo/plans/resqnet-sage.md
    verdict: CHANGES_REQUESTED → all 9 issues fixed (4 critical + 5 moderate)
    fixes_applied:
      - C1: Reconciled ORG_ID mismatch (seed/ids.py demo_org → org_demo)
      - C2: Fixed routing.py:210 → routing.py:130 for compute_cost
      - C3: Added step to register manager.router in main.py (todo 16)
      - C4: Added step to register health.router in main.py (todo 27)
      - M1: Replaced make bootstrap prerequisite with raw commands (todo 31)
      - M2: Fixed column count 25→26, noted missing hazards/bridges/operational_tasks
      - M3: Referenced existing optimizer/api.py route (todo 33)
      - M4: Added step to remove ensure_table import from consumer.py:18 (todo 7)
      - M5: Confirmed acceptance criteria complete; added adapter pattern note
approach: |
  Foundation-first, gate-ordered completion plan. The engine layer is ~60 REAL
  files but the API surface, migrations, frontend, simulator, and worker are
  incomplete. The plan repairs the DB foundation (migration reconciliation),
  wires the real engines to real API routes, builds the rescue-ball simulator,
  implements the Phase 1 vertical slice (auth→telemetry→confidence→hypothesis→
  alert→approval→task→map), builds the full frontend, adds offline/PWA, then
  continues the SOTA plan (fusion, perception, twin, optimizer, EVI, privacy,
  evaluation) where local resources permit.
---

# Draft: resqnet-sage

## Components (topology ledger)

| id | outcome (one line) | status | evidence path |
|----|-------------------|--------|----------------|
| C1-migrations | Alembic is sole schema authority; all ORM models reconciled with forward-only migrations; no create_all/ensure_table in production | active | `backend/alembic/versions/0001_init_schema.py`, `backend/app/lib/idempotency.py:49-58`, `backend/app/main.py:25`, `backend/app/seed/db_setup.py:68-79`, `backend/app/fusion/reliability.py:61-70` |
| C2-incident-domain | Explicit Incident model (not Event audit log); alerts, recommendations, task assignment as migration-backed tables | active | `backend/app/models/events.py:14-29` (Event=audit), `backend/app/models/entities.py:167-177` (OperationalTask), missing Incident/Alert/Recommendation models |
| C3-config-hardening | Safe health endpoints, no secret leaks, restricted test endpoints, non-default JWT in prod, structured logging | active | `backend/app/main.py:100-163` (healthz leaks DATABASE_URL), `.env.example:24` (JWT_SECRET=dev-secret-change-me), `backend/app/main.py:160-163` (test error endpoint unrestricted) |
| C4-worker-lifecycle | Dedicated worker container consuming observations.normalized → PostgreSQL → audit → realtime; graceful startup/shutdown; DLQ; health/metrics | active | `backend/app/streaming/consumer.py:28-171` (real ConsumerManager), `backend/app/streaming/producer.py:19-68` (real ProducerManager), no docker-compose worker service, `docker-compose.yml` has no worker service |
| C5-simulator | Deterministic rescue-ball simulator publishing through real ingestion path (Redpanda/SensorThings); start/pause/resume/stop/replay; fault injection; API + CLI | active | no simulator exists anywhere in codebase; `backend/app/eval/testbed.py:1-128` has DigitalTwinTestbed (different concept) |
| C6-auth-tenancy | Login, /me, logout/token-invalidation, role enforcement, org isolation, incident assignment checks | active | `backend/app/api/routes/auth.py:19-37` (login only), missing /me and logout, `backend/app/auth/roles.py:1-38`, `backend/app/auth/abac.py:1-229`, `backend/app/middleware/org_context.py:1-39` |
| C7-observation-api | Real observation endpoints: create, list, detail, pagination, filters (incident, source, phenomenon, time, bbox, freshness, confidence, visibility), GeoJSON output | active | `backend/app/api/routes/observations.py:1-14` (STUB returning {"status":"ok"}), `backend/app/models/observation.py:16-104` (real 23-field model) |
| C8-confidence-hypothesis | Wire the existing 6D confidence vector + hypothesis engine to API routes and streaming pipeline; create/update hypotheses with supporting/contradicting evidence | active | `backend/app/fusion/confidence.py:140-284` (REAL 6D vector), `backend/app/knowledge/graph.py:1-262` (REAL), `backend/app/api/routes/hypotheses.py:1-14` (STUB) |
| C9-alerts-approval | Draft alerts/proposed actions when rules satisfied; human approve/modify/dismiss with rationale; audit+provenance per action | active | no Alert model or route exists, `backend/app/sensing/catalog.py:195-240` dispatch creates pending tasks, `backend/app/audit/provenance.py:1-194` (REAL provenance) |
| C10-tasks-assignment | Task creation, priority, location, capability, team assignment, state transitions, assignment history, blocked/cancelled; deterministic assignment method | active | `backend/app/models/entities.py:167-177` (OperationalTask minimal), `backend/app/optimizer/engine.py:58-278` (REAL CVaR optimizer), no task API route |
| C11-realtime | Incident-scoped WebSocket broadcasts for all event types; polling fallback | active | `backend/app/realtime/manager.py:1-172` (REAL WebSocketManager), `backend/app/api/routes/ws.py:1-32` (ping/pong only, not wired to manager) |
| C12-seed-scenario | Idempotent local seed: org, 6 users, incident, zones, roads, buildings, shelters, hospitals, substations, cell towers, teams, vehicles, sensors, rescue-ball devices, observations, contradictory hypotheses, alert, action, task, population data | active | `backend/app/seed/seed_demo.py:34-59` (REAL but uses ensure_columns workaround), `backend/app/seed/db_setup.py:16-43` (ALTER TABLE workaround) |
| C13-situation-report | Text + JSON situation report from structured data; LLM prose as draft with evidence links | active | no report route exists, `backend/app/perception/llm.py:1-276` (REAL LLM), `backend/app/comms/fallback.py:1-289` (REAL compression) |
| C14-frontend | Functional React app: Login, Dashboard, Hypothesis, Planning, Simulation, FieldResponder, DeviceDetail, AuditProvenance pages; typed API client, auth context, router, TanStack Query, loading/empty/error/stale/offline states | active | `frontend/src/App.tsx:1-5` (just `<MapView/>`), `frontend/src/components/MapView.tsx:1-198` (REAL map), `frontend/src/components/ActionCard.tsx:1-250` (REAL card), react-router-dom + @tanstack/react-query in deps but unused |
| C15-map | MapLibre + deck.gl: incident boundary, flood/hazard, rescue-ball path, thermal detections, observations, blocked roads, shelters, hospitals, teams, tasks, alerts, infrastructure, uncertainty/age indicators; local PMTiles basemap | active | `frontend/src/components/MapView.tsx:43-56` (uses OSM online tiles, not local PMTiles), `frontend/src/components/mapLayers.ts:1-238` (11 layer types), `scripts/offline_prep.sh:44-70` (PMTiles generation) |
| C16-offline-pwa | PWA manifest, service worker, app-shell caching, IndexedDB outbox, queued field reports/task updates/location updates, conflict-aware replay, idempotent reconciliation, local basemap, feed-health tracking, low-bandwidth mode | active | no PWA manifest or service worker exists, `backend/app/realtime/edge_sync.py:1-267` (REAL EdgeSync), `backend/app/realtime/sync.py:1-275` (REAL StoreAndForwardSync), `backend/app/comms/fallback.py:1-289` (REAL low-bandwidth) |
| C17-testing | pytest with PostgreSQL/PostGIS integration; unit tests for math engines; FastAPI TestClient; migration tests; worker/streaming tests; tenant isolation; role denial; geometry round-trips; idempotency; audit tampering; stale data; contradictions; seed idempotency; simulator determinism; frontend typecheck/lint/unit/e2e Playwright | active | `backend/tests/conftest.py:14` (SQLite only), `backend/tests/test_ogc_adapter.py:33-53` (ALTER TABLE workaround), ~48 test files (~235 test functions, mostly REAL), `frontend/tests/` (2 files, 14 tests, REAL) |
| C18-automation | Makefile with bootstrap/migrate/seed/test/lint/typecheck/build/demo/verify targets; scripts/demo_phase1.sh | active | no Makefile exists, `scripts/offline_prep.sh` exists, `scripts/download_models.py` exists |
| C19-docs | README, .env.example, architecture, migration, API, offline, simulator, demo, testing, model/data licence, security, known limitations docs | active | `README.md` (basic), `DESIGN.md` (frozen contract, partially historical), `docs/db-extensions.md`, `docs/offline-prep.md`, `docs/cloudflare-reference/` (historical) |
| C20-sota-fusion | Dynamic Bayesian world-state estimation, conformal calibration, Brier/ECE/coverage, reliability data — all exist as REAL engines, need API wiring and integration tests | active | `backend/app/fusion/world_state.py:1-265` (REAL DBN), `backend/app/fusion/calibration.py:1-292` (REAL MAPIE) |
| C21-sota-perception | Model-serving abstraction, ONNX Runtime, fixture-based SAR flood mapping, ensemble disagreement, building/road damage, multilingual NLP, degraded fallback | active | `backend/app/perception/serving.py:1-258` (REAL ONNX), `backend/app/perception/flood_mapping.py:1-292` (REAL DOFA), `backend/app/perception/ensemble.py:1-228` (REAL), `backend/app/perception/nlp.py:1-280` (REAL), `backend/app/perception/damage.py:1-321` (REAL) |
| C22-sota-twin | Probabilistic best/expected/worst scenarios, infrastructure dependency graph, cascading failure, telecom silence | active | `backend/app/twin/scenarios.py:1-221` (REAL), `backend/app/twin/cascading.py:1-190` (REAL), `backend/app/twin/silence.py:1-146` (REAL) |
| C23-sota-optimizer | Hard constraints, rolling horizon, CVaR, route reliability, replanning stability, fairness, alternatives, infeasibility explanation | active | `backend/app/optimizer/engine.py:58-278` (REAL CVaR), `backend/app/optimizer/replan.py:1-259` (REAL), `backend/app/optimizer/fairness.py:1-190` (REAL), `backend/app/optimizer/routing.py:1-260` (REAL) |
| C24-sota-sensing | EVI computation, sensing action catalogue, human-approved dispatch, operational explanations | active | `backend/app/sensing/evi.py:1-223` (REAL), `backend/app/sensing/catalog.py:1-259` (REAL) |
| C25-sota-privacy | Progressive precision, ABAC, jurisdiction checks, emergency override with expiry, PII redaction, local inference, prompt-injection defense, decision provenance, fairness reporting | active | `backend/app/auth/abac.py:1-229` (REAL), `backend/app/lib/privacy.py` (REAL), `backend/app/perception/llm_safety.py:1-305` (REAL), `backend/app/audit/provenance.py:1-194` (REAL), `backend/app/optimizer/fairness.py:1-190` (REAL fairness engine) |
| C26-sota-evaluation | Deterministic replayable testbed, failure injection, 4 baselines, 6 metric categories, ablation studies | active | `backend/app/eval/testbed.py:1-128` (REAL), `backend/app/eval/failures.py:1-280` (REAL), `backend/app/eval/baselines.py:1-269` (REAL), `backend/app/eval/metrics.py:1-263` (REAL), `backend/app/eval/ablation.py:1-269` (REAL) |

## Open assumptions (announced defaults)

| assumption | adopted default | rationale | reversible? |
|------------|----------------|-----------|-------------|
| Worker container | Dedicated worker container in docker-compose (prompt's preferred option) | Prompt says "preferred for clear lifecycle separation" | Yes — can switch to background task |
| Branch name | `codex/resqnet-phase1-completion` | Prompt suggests this name | Yes |
| PMTiles basemap | Local PMTiles via offline_prep.sh + OSM raster fallback when PMTiles unavailable | Prompt says "local PMTiles or another fully local fallback" | Yes |
| Reduced-resource profile | docker-compose profile `--profile reduced` excluding Ollama, Prometheus, Grafana, heavy ML | Prompt requires documented reduced-resource profile | Yes |
| Test DB | PostgreSQL/PostGIS via testcontainers or shared Docker DB; SQLite only for pure logic | Prompt says "Do not use SQLite as the only database test target for PostGIS" | No — architectural constraint |
| Frontend tooling | Add ESLint, TypeScript strict (already in tsconfig), Vitest for unit tests, Playwright for e2e | Prompt requires typecheck/lint/unit/e2e | No — required by prompt |
| ENUM handling | Reconcile migration to use VARCHAR (native_enum=False) matching ORM, OR update ORM to use native PG enums | Migration creates native PG ENUM types but ORM uses native_enum=False — must pick one. Adopt VARCHAR everywhere for simplicity and migration safety. | Yes but disruptive if wrong |
| H3 geo_index | Add h3_geo_index table to migration (entity_type, entity_id, h3 resolution) | Prompt requires H3 indexing; extension exists but no table | No — architectural |
| Commit granularity | One coherent commit per task/milestone per prompt's conventional commit examples | Prompt specifies commit discipline | No — required |

## Findings (cited - path:lines)

### Backend engine layer is remarkably complete
- `backend/app/fusion/confidence.py:140-284` — REAL 6D confidence vector (S,C,F,G,M,K) with haversine, corroboration, conflict detection
- `backend/app/fusion/reliability.py:73-186` — REAL Beta model source reliability with per-phenomenon conditioning, time decay
- `backend/app/fusion/calibration.py:1-292` — REAL MAPIE conformal calibrator with Brier/ECE/coverage
- `backend/app/fusion/world_state.py:1-265` — REAL DBN world state estimator via pgmpy
- `backend/app/fusion/freshness.py:1-113` — REAL phenomenon-specific exponential decay
- `backend/app/perception/*.py` (15 files) — ALL REAL: LLM, NLP, flood mapping, damage, ensemble, serving, safety
- `backend/app/optimizer/*.py` (10 files) — ALL REAL: CVaR engine, 7 constraint families, fairness, routing, replan
- `backend/app/twin/*.py` (7 files) — ALL REAL: scenarios, cascading, silence
- `backend/app/knowledge/graph.py:1-262` — REAL temporal crisis graph with AGE + recursive CTE fallback
- `backend/app/sensing/*.py` (5 files) — ALL REAL: EVI, catalog, dispatch with human approval
- `backend/app/eval/*.py` (8 files) — ALL REAL: testbed, metrics, failures, baselines, ablation
- `backend/app/ingestion/adapters/*.py` (6 adapters) — ALL REAL: CAP, STAC, SensorThings, OGC Features, HDX
- `backend/app/streaming/consumer.py:28-171` — REAL Kafka consumer with DLQ, dedup, audit
- `backend/app/streaming/producer.py:19-68` — REAL Kafka producer with idempotence
- `backend/app/realtime/manager.py:1-172` — REAL WebSocketManager with broadcast, polling fallback
- `backend/app/realtime/edge_sync.py:1-267` — REAL EdgeSync with dedup, ordering
- `backend/app/realtime/sync.py:1-275` — REAL StoreAndForwardSync with conflict surfacing, CRDT merge
- `backend/app/auth/abac.py:1-229` — REAL ABAC with jurisdiction, emergency override TTL
- `backend/app/audit/provenance.py:1-194` — REAL hash-chained decision provenance
- `backend/app/comms/fallback.py:1-289` — REAL low-bandwidth fallback (SMS stub, cell broadcast, LoRa, DTN)

### API surface is mostly stubs
- `backend/app/api/routes/observations.py:11-14` — STUB: returns `{"status":"ok"}`
- `backend/app/api/routes/hypotheses.py:11-14` — STUB
- `backend/app/api/routes/scenarios.py:11-14` — STUB
- `backend/app/api/routes/sensing.py:11-14` — STUB
- `backend/app/api/routes/eval.py:11-14` — STUB
- `backend/app/api/routes/ws.py:1-32` — PARTIAL: ping/pong only, not wired to WebSocketManager
- Missing routes entirely: incidents, tasks, alerts, recommendations, reports, dashboard, entities (zones/roads/shelters/hospitals/teams/vehicles/sensors), audit logs

### Migration drift is severe
- `backend/alembic/versions/0001_init_schema.py` — single migration, creates 17 tables
- 13 entity tables in migration only have base columns (id, org_id, incident_id, created_at, updated_at, geometry, properties) — ORM models define name, status, capacity, etc. that are missing
- `sources` table: fully defined in `backend/app/models/source.py:51-78` but NOWHERE in migration AND no ensure_table() — completely orphaned
- `users` table: created via `Base.metadata.create_all()` in `backend/app/main.py:25` — not in migration
- `idempotency_keys`: created via `ensure_table()` in `backend/app/lib/idempotency.py:49-58`
- `source_reliability`: created via `ensure_table()` in `backend/app/fusion/reliability.py:61-70`
- Native PG ENUM vs VARCHAR mismatch: migration creates native enums (`sourcetype`, `corroborationstate`, etc.) but ORM uses `native_enum=False` (VARCHAR)
- Missing migration tables: incidents, alerts, recommendations, federation_outbox, edge_sync tables, sync tables, perception_models, llm_call_log, decision_provenance, h3_geo_index

### Frontend is near-empty
- `frontend/src/App.tsx:1-5` — just `<MapView />`
- `frontend/src/components/MapView.tsx:43-56` — uses online OSM tiles, not local PMTiles
- react-router-dom, @tanstack/react-query, i18next in package.json but NEVER imported
- No routing, auth context, API client, PWA, service worker, IndexedDB, offline support
- `frontend/package.json:7-9` — only dev/build/preview scripts; no typecheck/lint/test scripts
- Playwright tests exist (14 tests, REAL) but test mock-data-only app

### Test suite is real but has DB issues
- `backend/tests/conftest.py:14` — SQLite only, `Base.metadata.create_all()`
- `backend/tests/test_ogc_adapter.py:33-53` — 20 ALTER TABLE statements to add missing columns
- ~18 test functions use PostgreSQL via SessionLocal directly
- ~235 test functions across ~48 files, mostly REAL with meaningful assertions
- No fake/counterfeit tests (no `assert True`)

### Infrastructure gaps
- `docker-compose.yml` — no dedicated worker service
- `docker-compose.yml:161` — CORS_ORIGINS defaults to `*` with allow_credentials=True
- `backend/app/main.py:104-113` — healthz leaks full DATABASE_URL
- `backend/app/main.py:160-163` — /api/_test/error unrestricted outside dev
- No Makefile
- `grafana/provisioning/` — has dashboards and datasources (3 files)
- `prometheus.yml` — scrapes backend:8000/metrics
- `backend/Dockerfile:25` — installs torch CPU-only (good)
- `backend/requirements.txt:17-18` — torch + torchgeo (heavy, but CPU-only in Dockerfile)
- No requirements lock file (requirements.txt uses >= pins)

## Decisions (with rationale)

1. **Migrate all ensure_table/create_all tables into Alembic migrations** — The prompt explicitly says "Do not rely on test fixtures that run ALTER TABLE, Base.metadata.create_all() during application startup, module-local ensure_table() calls as permanent production schema management." All 8+ runtime-created tables (users, sources, idempotency_keys, source_reliability, federation_outbox, edge_sync tables, sync tables, perception_models, llm_call_log, decision_provenance) plus missing domain tables (incidents, alerts, recommendations) and missing entity columns will be added in migration 0002+.

2. **Use VARCHAR for all enum columns (native_enum=False)** — The ORM already uses native_enum=False. The migration creates native PG ENUM types which is incompatible. Reconcile by dropping native enums in the migration and using VARCHAR. This is simpler, more portable, and matches the ORM.

3. **Add Incident model as a new table** — The prompt says "The current audit log named Event is not a disaster incident." We preserve the events audit table and add a new incidents table with ULID, org_id, title, disaster_type, severity, status, declaration_level, description, geometry, start_time, expected_end, configuration, timestamps.

4. **Dedicated worker container** — Add a `worker` service to docker-compose that runs the ConsumerManager as a persistent process. This is the prompt's preferred option.

5. **Wire existing engines to API routes** — The engines are REAL but the routes are STUBS. The plan replaces each stub route with a real implementation that calls the existing engine. No new engine logic needed for Phase 1 — just wiring.

6. **Frontend: full rebuild around existing components** — Keep MapView and ActionCard, add routing, auth context, API client, TanStack Query, and 8 required pages. Add PWA manifest, service worker, IndexedDB outbox.

7. **Local PMTiles with OSM fallback** — The offline_prep.sh already generates PMTiles. The frontend will try local PMTiles first, fall back to OSM raster tiles when offline_prep hasn't been run.

8. **PostgreSQL/PostGIS test DB** — Replace SQLite-only conftest with a PostgreSQL test fixture (using the Docker db service or testcontainers). SQLite retained only for pure logic tests.

## Scope IN

Everything in the user's 17-section prompt:
- Section 4: Implementation audit + execution plan docs
- Section 5: Foundation repair (migrations, incident domain, config hardening, worker lifecycle)
- Section 6: Rescue-ball simulator
- Section 7: Phase 1 vertical slice (auth, observation API, confidence/hypothesis, alerts/approval, tasks/assignment, realtime, seed, situation report)
- Section 8: Frontend (all pages, map, action cards, offline states)
- Section 9: Offline and degraded operation (PWA, outbox, reconciliation)
- Section 10: SOTA plan continuation (fusion, perception, twin, optimizer, active sensing, privacy, evaluation)
- Section 11: Testing hierarchy (backend + frontend)
- Section 12: Phase gates A-E
- Section 13: Automation commands (Makefile, demo script)
- Section 14: Documentation
- Section 15: Commit discipline
- Section 16: Blocker handling
- Section 17: Definition of done

## Scope OUT (Must NOT have)

- Do NOT extend or modify the Cloudflare Workers implementation under `platform/`
- Do NOT port Cloudflare Workers code to the Python backend
- Do NOT implement new production behavior under `platform/`
- Do NOT use an unconstrained language model or online RL controller to issue field commands
- Do NOT claim simulated thermal/seismic/vibration capabilities are real hardware
- Do NOT fabricate model accuracy, trained weights, benchmark outcomes, or real-world rescue capability
- Do NOT download huge datasets into Git (use manifests, checksums, download scripts, small fixtures)
- Do NOT push directly to main
- Do NOT weaken type checking to make builds green
- Do NOT use fake tests (assert True, tautological snapshots, mocking the SUT)
- Do NOT replace missing advanced functionality with misleading random values (randomness only in explicitly simulated scenarios, must be seedable)
- Do NOT silently discard conflicting offline edits
- Do NOT display stale information as current

## Open questions

None. The intent is CLEAR — the user's 17-section prompt is a complete specification. Every decision is either explicitly stated in the prompt or resolvable by inspecting the codebase and adopting best-practice defaults.

## Approval gate
status: awaiting-approval
approach: Foundation-first, gate-ordered completion plan spanning all 17 sections of the prompt. The engine layer is ~60 REAL files; the gap is in migrations (drifted), API routes (stubs), frontend (near-empty), simulator (missing), and worker (not running). The plan reconciles migrations, wires real engines to real routes, builds the simulator, implements Phase 1 vertical slice, builds the full frontend with offline support, continues SOTA, and adds testing/automation/docs. ~50-60 todos across 5 gate-ordered waves.
next-action: write .omo/plans/resqnet-sage.md after user approval
