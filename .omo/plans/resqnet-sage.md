# resqnet-sage - Work Plan

## TL;DR (For humans)

**What you'll get:** A complete disaster-response intelligence system that goes far beyond a dashboard. It builds a continuously updated probabilistic model of a crisis, forecasts plausible hazard and infrastructure scenarios, and uses risk-aware optimization to generate operationally feasible response alternatives. It actively identifies which missing observations should be collected next, preserves the provenance and disagreement of every source, and allows commanders to inspect evidence, assumptions, trade-offs and contingencies before acting. The system runs entirely on local hardware with no internet dependency, supports offline operation with store-and-forward sync, and degrades honestly (showing data age, lost feeds, and widening uncertainty rather than hiding stale data). It includes a replayable evaluation testbed with failure injection, four baselines for comparison, six categories of metrics, and ablation studies that prove which components actually improve outcomes.

**Why this approach:** The user provided an extremely detailed SOTA research synthesis document identifying that the current design is not yet state of the art. The core insight: ResQNet should be redesigned around "Given uncertain, incomplete, delayed and contradictory information, which feasible combination of actions is expected to prevent the most harm over the next operational horizon?" The user chose a full pivot away from Cloudflare Workers to a Python/PostGIS stack because the required capabilities cannot run on Workers. Everything must work on local hardware with low internet connectivity.

**What it will NOT do:** It will not retain the Cloudflare Workers platform. It will not continue the existing platform build plan. It will not auto-publish AI artifacts. It will not use online RL as the sole controller. It will not compress the confidence vector into a single number. It will not silently resolve contradictory hypotheses. It will not require cloud runtime dependencies. It will not vendor the archived pyds library. It will not use DESIGN.md as the interface contract (superseded).

**Effort:** XL — 53 work units across 10 waves + a validation spike + final verification, building 9 SOTA architectural layers plus an evaluation testbed from scratch.

**Risk:** High — (1) PostgreSQL extension coexistence (Apache AGE may not work alongside PostGIS — spike validates first, fallback to recursive CTEs), (2) SAR satellite data and ML model availability on local hardware (requires pre-download + ONNX conversion), (3) pgmpy DBN only supports discrete variables, (4) OR-Tools CP-SAT does not natively support CVaR (requires custom linearization), (5) offline LLM inference quality. Each risk has a stated mitigation.

**Decisions to sanity-check:** (1) Full pivot from Cloudflare to Python/PostGIS. (2) Dempster-Shafer combination implemented directly (~50 LOC) rather than vendoring archived pyds. (3) If Apache AGE is incompatible with PostGIS, graph queries use graph_edges table + recursive CTEs as primary approach. (4) All ML models run locally via ONNX Runtime; satellite data pre-downloaded via sync-when-connected pattern. (5) LLM summarization uses local Ollama for offline, cloud API when connected.

Your next move: approve the plan, or run a high-accuracy review first. Full execution detail follows below.

## Scope
### Must have
- A complete ResQNet-SAGE (Situation-Aware Geospatial Evidence and Action Engine) system built from scratch on a Python/PostGIS stack, implementing all 9 architectural layers from the SOTA research synthesis document.
- **Stack**: Python 3.11+ FastAPI + SQLAlchemy 2.x + GeoAlchemy2 + Alembic + Pydantic v2; PostgreSQL 16 + PostGIS 3.4 + TimescaleDB + Apache AGE (graph); Redpanda (Kafka-compatible streaming) + Benthos (stream processing); PyTorch + TorchGeo + rasterio + GDAL + ONNX Runtime (ML); OR-Tools CP-SAT + Pyomo + HiGHS (optimization); React 18 + Vite + MapLibre GL JS + deck.gl + Tailwind + TanStack Query (frontend); MinIO (S3-compatible object storage); Redis (cache + pub/sub); OpenTelemetry + Prometheus + Grafana (observability).
- **Local-hardware-first deployment**: All services in a single Docker Compose stack runnable on local hardware. No cloud runtime dependencies. ML models pre-downloaded/cached. Satellite data acquisition via "sync when connected" pattern. Frontend is a PWA with offline capabilities. System must operate in degraded mode when internet is unavailable.
- **9 SOTA layers**:
  - Layer 1: Federated emergency-data fabric (23-field observation schema + CAP/SensorThings/OGC API/STAC/HDX HAPI adapters)
  - Layer 2: Multimodal crisis-perception system (SAR flood mapping ensemble, building/road damage assessment, social media NLP pipeline)
  - Layer 3: Temporal crisis knowledge graph (entities, relationships, contradictory hypothesis preservation)
  - Layer 4: Probabilistic evidence fusion (confidence vector [6D], Beta source reliability, phenomenon-specific freshness, Bayesian/DBN world-state P(X_t|O_{1:t}), conformal calibration)
  - Layer 5: Hazard & infrastructure digital twin (scenario ensemble, cascading dependency DAG, telecom silence residual)
  - Layer 6: Decision optimization (rolling-horizon risk-aware CVaR optimizer, constraints, route reliability, stability threshold)
  - Layer 7: Active sensing / expected value of information (EVI computation, sensing action catalog)
  - Layer 8: Human-centered explainable decision support (4 interface modes, action cards with evidence/alternatives/uncertainty)
  - Layer 9: Resilient communications & offline operation (edge-first topology, store-and-forward sync, low-bandwidth fallback, honest degradation)
- **Evaluation testbed**: Replayable cyclone-flood digital twin with failure injection, 4 baselines, 6 metric categories (perception, uncertainty, operational, resilience, human-factors, equity), ablation study runner.
- **Conventions** (carried from existing project, adapted for Python): ULID IDs; UTC epoch ms; `org_id` tenancy on every table; `visibility ∈ {public,internal,sensitive}` + `review_status ∈ {draft,reviewed,official}`; hash-chained append-only audit; idempotency keys on external/queue/webhook paths; all AI output `review_status=draft` until human approval; files under 250 pure LOC; conventional commits `feat(scope): description`.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do NOT retain or extend the Cloudflare Workers platform (`platform/` directory is dead code; no new work there).
- Do NOT continue the existing `disaster-cf-replatform.md` plan or its boulder work.
- Do NOT use the FEATURES.md checkbox catalog as the spec — the SOTA research synthesis document is the sole spec.
- Do NOT auto-publish AI artifacts — always `review_status=draft` until human approval.
- Do NOT use online RL as the sole operational controller — hard constraints always enforced.
- Do NOT treat the evaluation testbed as an afterthought — it is a first-class deliverable.
- Do NOT require cloud runtime dependencies — everything runs on local hardware with low/no internet.
- Do NOT compress the confidence vector into a single scalar — all 6 dimensions must remain available to the reasoning engine.
- Do NOT silently resolve contradictory hypotheses — preserve both supporting and contradicting evidence.
- Do NOT implement during planning — execution starts only on `/start-work`.
- Do NOT use `DESIGN.md` as the interface contract — it is SUPERSEDED by this plan. Where they conflict, this plan wins (ULID not UUID, epoch ms not server-default timestamps, new stack not old).
- Do NOT vendor or depend on `pyds` (reineking/pyds) — it is archived since 2021, not on PyPI (name collision with NASA PDS), and the author recommends "probabilistic alternatives." Implement Dempster-Shafer combination rule directly (~50 LOC) if needed, or use pgmpy Bayesian fusion exclusively.
- Do NOT assume Apache AGE has a SQLAlchemy dialect — graph queries require raw SQL via psycopg3. If AGE+PostGIS+TimescaleDB cannot coexist (AGE v1.8.0 requires PG 18, PostGIS 3.4 may not support PG 18), fall back to `graph_edges` table + recursive CTEs as the PRIMARY approach, not a fallback.
- Do NOT assume pgmpy DBN supports continuous variables — it only accepts `TabularCPD` (discrete). All evidence must be discretized with documented bin boundaries.
- Do NOT assume OR-Tools CP-SAT natively supports CVaR — it requires custom linearization via Rockafellar-Uryasev formulation with auxiliary variables.
- Do NOT assume cloud LLM APIs are available at runtime — provide local LLM (Ollama) for offline inference.

## Verification strategy
> Zero human intervention — all verification is agent-executed.
- **Test decision**: TDD for logic-bearing engines (evidence fusion, optimizer, EVI, knowledge graph queries, freshness decay, Beta updates, conformal calibration) + tests-after for CRUD/plumbing/routes/UI. Framework: `pytest` + `pytest-asyncio` for backend; `vitest` + Playwright for frontend; `docker compose` for integration.
- **ML model verification**: unit tests with fixture tensors (not requiring real satellite data); integration tests with cached sample Sentinel-1 scenes; calibration tests against held-out flood labels.
- **Optimizer verification**: unit tests with small scenario fixtures (2-3 zones, 2-3 teams); constraint violation tests; stability threshold tests; CVaR calculation tests.
- **Evaluation testbed verification**: deterministic seeded runs; ablation comparisons produce different metrics when components are removed.
- **Offline/degraded mode verification**: tests that simulate network partition, feed loss, and verify honest degradation (stale data flagged, uncertainty widens, capabilities reported as unavailable).
- **Per-todo acceptance**: every todo carries References (SOTA spec section + exact files) + agent-executable Acceptance criteria (runnable command with expected output) + happy QA + failure QA + Commit.
- **Evidence**: `.omo/evidence/task-<N>-resqnet-sage.<ext>`

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. The plan is organized by SOTA spec layers (Sections 3-11), respecting dependency chains. ML perception (Layer 2) parallelizes with ingestion/knowledge graph (Layers 1+3). Evidence fusion (Layer 4) depends on both. Optimization (Layer 6) depends on fusion + digital twin (Layer 5). Active sensing (Layer 7) depends on optimization. UI (Layer 8) depends on all compute layers. Evaluation (Section 14) depends on everything.

### Dependency matrix
| Wave / Layer | Depends on | Blocks | Can parallelize with |
|---|---|---|---|
| Wave 0: Spike (T0a) | — | W1 | — |
| Wave 1: Foundation (T1-T5) | T0a | everything | — |
| Wave 2: Ingestion + Knowledge Graph (T6-T12) | W1 | W3, W4 | W4 (ML perception starts in parallel) |
| Wave 3: Evidence Fusion (T13-T17) | W2 | W5, W6 | — |
| Wave 4: ML Perception (T18-T22) | W1 + T9 (STAC) | W5 (scenarios use ML outputs) | W2, W3 |
| Wave 5: Digital Twin (T23-T25) | W3, W4 | W6 | — |
| Wave 6: Optimization + Active Sensing (T26-T31) | W3, W5 | W7 | — |
| Wave 7: Decision Support UI (T32-T36) | W6 | W8 | — |
| Wave 8: Resilient Comms (T37-T40) | W7 | W9 | — |
| Wave 9: Evaluation Testbed (T41-T45) | all layers | W10 | — |
| Wave 10: Privacy/Security/Integration (T46-T50) | cross-cutting | final verification | — |
| Final verification (F1-F4) | all | — | — |

> Metis-folded: Wave 4 depends on T9 (STAC adapter), not just W1 — SAR pipeline needs STAC for imagery indexing. Redpanda minimum memory is 4GB, not 1GB. Apache AGE may not coexist with PostGIS — graph_edges + recursive CTEs is the primary approach, AGE is optional. pyds is dropped — implement DS combination directly or use pgmpy exclusively.

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
<!-- Each todo references the SOTA spec section it implements. -->

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 0: SPIKE — Validate PostgreSQL extension coexistence (Metis GAP 3) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [x] 51. Spike: Validate PostgreSQL + PostGIS + Apache AGE + TimescaleDB coexistence
  What to do / Must NOT do: Build a custom Docker image (`Dockerfile.db`) based on `postgres:16` (or `postgres:18` if AGE requires it). Install PostGIS 3.4, Apache AGE (latest), and TimescaleDB extensions. Verify all four `CREATE EXTENSION` commands succeed in the same database. If any two are incompatible (AGE v1.8.0 requires PG 18; PostGIS 3.4 may not support PG 18), document the incompatibility and choose: (a) drop AGE — use `graph_edges` table + recursive CTEs as primary graph approach (recommended), (b) drop TimescaleDB — use plain PostgreSQL tables for sensor history, (c) use separate PostgreSQL instances. Also verify: `h3` extension availability (or plan for application-layer H3 via Python `h3` package). Output: a working `Dockerfile.db` + documented decision.
  SOTA spec ref: §13.2 (data stores: PostgreSQL/PostGIS, TimescaleDB, graph layer)
  Parallelization: Wave 0 | Blocked by: — | Blocks: T1, T2, T11
  References: Metis GAP 3. Apache AGE META.json: `prereqs.runtime.requires.PostgreSQL: "18.0.0"`. PostGIS 3.4 supports PG 13-17. No pre-built image combining all three. PostGIS+AGE coexistence: open GitHub issues #179, #48.
  Acceptance criteria: `docker build -t resqnet-db .` exits 0; `docker run resqnet-db psql -c "CREATE EXTENSION postgis; CREATE EXTENSION age; CREATE EXTENSION timescaledb;"` succeeds (or documented why one is dropped); decision recorded in `docs/db-extensions.md`.
  QA scenarios:
  ```
  Scenario: all extensions load
    Tool: bash
    Steps: docker build -t resqnet-db -f Dockerfile.db . && docker run --rm resqnet-db psql -U disaster -c "CREATE EXTENSION postgis; CREATE EXTENSION age; CREATE EXTENSION timescaledb; SELECT extname FROM pg_extension;" | tee .omo/evidence/task-0a-resqnet-sage.txt
    Expected: all extensions listed (or documented decision for dropped one)
    Evidence: .omo/evidence/task-0a-resqnet-sage.txt
  ```
  Commit: Y | `chore(spike): validate PG extension coexistence`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 1: FOUNDATION — SOTA spec §3 (event schema), §13 (implementation) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [x] 1. Project skeleton + Docker Compose (all services, local-hardware-first)
  What to do / Must NOT do: Create `backend/` (Python 3.11+ FastAPI + SQLAlchemy 2.x + GeoAlchemy2 + Alembic + Pydantic v2) and `frontend/` (React 18 + Vite + MapLibre GL JS + deck.gl + Tailwind + TanStack Query). Root `docker-compose.yml` with services: `db` (PostGIS 16 + Apache AGE + TimescaleDB via `apache/age` image or postgis+age extension), `redpanda` (single-node, `--mode dev-container`, 4GB RAM minimum — 1GB is below Redpanda minimum), `benthos` (stream processor), `minio` (S3-compatible object storage, self-hosted), `redis` (cache + pub/sub), `ollama` (local LLM for offline inference — llama3.1:8b model, ~5GB RAM, needed for T36/T48 offline LLM), `backend` (uvicorn), `frontend` (Vite dev or static), `prometheus` + `grafana` (observability). `.env.example` with all env vars. `backend/requirements.txt` with: fastapi, uvicorn, sqlalchemy, geoalchemy2, alembic, pydantic, pydantic-settings, shapely, geojson-pydantic, **psycopg[binary]** (psycopg3, NOT psycopg2 — needed for Apache AGE raw SQL), aiokafka, redis, minio, torch, torchgeo, rasterio, gdal, ortools, pyomo, highspy, pgmpy, scikit-learn, mapie, onnxruntime, **faiss-cpu** (vector similarity for dedup — replaces Cloudflare Vectorize), **openai** (OpenAI-compatible client, works with Ollama at localhost:11434), opentelemetry-sdk, opentelemetry-instrumentation-fastapi, prometheus-client. `backend/app/` package structure: `__init__.py`, `main.py`, `config.py`, `db.py`, `deps.py`, `models/`, `schemas/`, `api/routes/`, `fusion/`, `knowledge/`, `twin/`, `optimizer/`, `sensing/`, `perception/`, `ingestion/`, `streaming/`, `eval/`, `lib/`, `auth/`, `audit/`. `frontend/package.json` with: react, vite, maplibre-gl, deck.gl, tailwindcss, @tanstack/react-query, react-router-dom, i18next. Must NOT use any cloud services at runtime — all services self-hosted in Docker Compose. Must NOT carry over any Cloudflare Workers code from `platform/`.
  SOTA spec ref: §13.1 (streaming/ingestion), §13.2 (data stores), §13.3 (geospatial services), §13.4 (ML stack), §13.5 (optimization stack), §13.6 (observability)
  Parallelization: Wave 1 | Blocked by: — | Blocks: T2-T5, all
  References: `docker-compose.yml` (existing, to replace), `DESIGN.md:11-22` (stack), `.env.example` (existing, to update). Redpanda Docker pattern: `--mode dev-container`, `--smp 1`, `--memory 1G`, internal+external addr split (research bg_835b8072). Apache AGE: `apache/age:latest` image or `postgres:16` + `CREATE EXTENSION age`. MinIO: `minio/minio server /data`. Benthos: `jeffail/benthos:latest` with YAML config mount.
  Acceptance criteria (agent-executable): `docker compose up -d` exits 0; `curl -s http://localhost:8000/healthz` returns `{"ok":true}`; `curl -s http://localhost:19092` (Redpanda) responds; `curl -s http://localhost:9000/minio/health/live` returns 200; `curl -s http://localhost:11434/api/tags` (Ollama) responds; **if T51 spike kept Apache AGE**: `docker compose exec db psql -U disaster -c "SELECT * FROM ag_catalog.create_graph('test_graph');"` succeeds; **if T51 dropped AGE**: `docker compose exec db psql -U disaster -c "SELECT count(*) FROM graph_edges;"` succeeds (graph_edges table exists as primary approach); `cd frontend && npm install && npm run build` exits 0.
  QA scenarios:
  ```
  Scenario: full stack boots
    Tool: bash
    Steps: docker compose up -d --wait && curl -s http://localhost:8000/healthz | tee .omo/evidence/task-1-resqnet-sage.txt
    Expected: JSON with ok:true and all service bindings present
    Evidence: .omo/evidence/task-1-resqnet-sage.txt
  Scenario: missing service causes healthz failure
    Tool: bash
    Steps: docker compose stop db && curl -s http://localhost:8000/healthz | tee .omo/evidence/task-1-resqnet-sage-error.txt; docker compose start db
    Expected: healthz returns ok:false with db check failing
    Evidence: .omo/evidence/task-1-resqnet-sage-error.txt
  ```
  Commit: Y | `chore(platform): project skeleton + docker compose stack`

- [x] 2. Rich observation schema (23-field event model) + core DB schema (entities, relationships, hypotheses, scenarios)
  What to do / Must NOT do: Create SQLAlchemy + GeoAlchemy2 models in `backend/app/models/`. Observation schema per SOTA spec §3.3 with ALL 23 fields: `observation_id` (ULID PK), `event_type`, `phenomenon`, `value` (float nullable), `unit`, `geometry` (PostGIS Geometry), `geometry_uncertainty` (float, meters), `observed_at` (bigint, UTC epoch ms), `valid_from` (bigint), `valid_until` (bigint nullable), `received_at` (bigint), `source_id` (text FK), `source_type` (enum), `collection_method` (text), `source_reliability` (float 0-1), `freshness` (float 0-1), `corroboration_state` (enum: uncorroborated/corroborated/contradicted/superseded), `model_uncertainty` (float nullable), `quality_flags` (JSONB), `access_policy` (enum: public/internal/sensitive), `provenance_chain` (JSONB array of source IDs), `raw_data_hash` (text), `model_version` (text nullable), `supersedes` (ULID nullable FK self), `duplicate_group` (ULID nullable). Core entities: `Hazard`, `Zone`, `Building`, `RoadSegment`, `Bridge`, `PowerSubstation`, `CellTower`, `Hospital`, `Shelter`, `Responder`, `Vehicle`, `Sensor`, `OperationalTask`, `Decision`, `Scenario` — each with `id` (ULID), `org_id`, `incident_id`, `geometry` (where applicable), `created_at`, `updated_at`. Relationship table: `graph_edges(source_type, source_id, edge_type, target_type, target_id, properties JSONB, valid_from, valid_until)` for Apache AGE graph. `hypotheses` table: `id`, `org_id`, `incident_id`, `entity_type`, `entity_id`, `claim` (text), `probability` (float 0-1), `supporting_evidence` (JSONB array of obs IDs), `contradicting_evidence` (JSONB), `status` (enum: active/resolved/superseded), `created_at`, `updated_at`. `scenarios` table: `id`, `org_id`, `incident_id`, `label` (enum: best/expected/worst), `probability` (float), `params` (JSONB), `result_geojson` (text nullable), `status` (enum: queued/running/completed/failed), `created_at`, `completed_at`. All tables carry `org_id` + `incident_id` (incident-scoped). `events` table for hash-chained audit: `id`, `org_id`, `actor`, `action`, `entity`, `before` (JSONB), `after` (JSONB), `ts` (bigint), `prev_hash` (text), `hash` (text). Alembic migration `0001_init.sql` creates all tables + PostGIS extension + AGE extension + H3 extension (`h3_postgis`) if available, else H3 via application layer.
  SOTA spec ref: §3.3 (event schema), §5 (knowledge graph entities), §7.1 (scenario ensemble), §12.4 (provenance/auditability)
  Parallelization: Wave 1 | Blocked by: T1 | Blocks: T6-T12, all schema consumers
  References: SOTA spec §3.3 (23-field schema), §5.1 (core entities), §5.2 (relationships), §5.3 (hypotheses), §7.1 (scenarios), §12.4 (audit). `DESIGN.md:95-141` (existing entity list to adapt). Convention: ULID (not UUID), UTC epoch ms, org_id tenancy.
  Acceptance criteria: `cd backend && alembic upgrade head` exits 0; `docker compose exec db psql -U disaster -c "SELECT column_name FROM information_schema.columns WHERE table_name='observations' ORDER BY ordinal_position;"` lists all 23 fields; a pytest inserts an observation and reads it back with geometry round-trip.
  QA scenarios:
  ```
  Scenario: observation schema has all 23 fields
    Tool: bash
    Steps: docker compose up -d db && cd backend && alembic upgrade head && docker compose exec -T db psql -U disaster -c "SELECT count(*) FROM information_schema.columns WHERE table_name='observations';" | tee ../.omo/evidence/task-2-resqnet-sage.txt
    Expected: count = 23 (or 25 including id and org_id)
    Evidence: .omo/evidence/task-2-resqnet-sage.txt
  Scenario: geometry round-trips through PostGIS
    Tool: bash
    Steps: cd backend && pytest tests/test_schema.py::test_observation_geometry_roundtrip -q | tee ../.omo/evidence/task-2-resqnet-sage-error.txt
    Expected: pytest exits 0, GeoJSON Point persists and reads back with correct coordinates
    Evidence: .omo/evidence/task-2-resqnet-sage-error.txt
  ```
  Commit: Y | `feat(schema): rich observation model + knowledge graph entities + audit`

- [x] 3. ULID + timestamp + audit hash-chain + idempotency primitives (Python)
  What to do / Must NOT do: `backend/app/lib/ulid.py` — ULID generation (Crockford base32, monotonic, 26-char). `backend/app/lib/time.py` — `now_ms()` UTC epoch ms, `from_iso()`, `to_iso()`. `backend/app/lib/audit.py` — `write_audit(db, org_id, incident_id, actor, action, entity, before, after)` that appends to `events` table with `hash = sha256(prev_hash + json(payload))` and verifies chain on read. `backend/app/lib/idempotency.py` — dedup by `(source, external_id)` unique constraint + message-id dedup table for queue messages. `backend/app/lib/serialize.py` — visibility serializer: whitelists fields by `visibility ∈ {public,internal,sensitive}` + `review_status ∈ {draft,reviewed,official}`. Must NOT use UUID — ULIDs only. Must NOT trust org_id from client — resolved server-side.
  SOTA spec ref: §12.4 (provenance/auditability), §12.1 (data minimization), §12.2 (access control)
  Parallelization: Wave 1 | Blocked by: T1, T2 | Blocks: all state-changing todos
  References: `platform/worker/src/lib/ulid.ts` (existing pattern to port to Python), `platform/worker/src/lib/audit.ts` (existing hash-chain pattern). SOTA spec §12.4: "hash-chained append-only log is sufficient for tamper evidence".
  Acceptance criteria: `cd backend && pytest tests/test_audit.py -q` passes — inserts 3 events, recomputes hashes, asserts chain validity; tampering middle row → `verify_chain()` returns false at that index. `pytest tests/test_idempotency.py` — insert same `(source, external_id)` twice → second is no-op.
  QA scenarios:
  ```
  Scenario: audit hash-chain verifies
    Tool: bash
    Steps: cd backend && pytest tests/test_audit.py::test_chain_verifies -q | tee ../.omo/evidence/task-3-resqnet-sage.txt
    Expected: exit 0, chain of 3 events verifies
    Evidence: .omo/evidence/task-3-resqnet-sage.txt
  Scenario: tampered chain detected
    Tool: bash
    Steps: cd backend && pytest tests/test_audit.py::test_tamper_detected -q | tee ../.omo/evidence/task-3-resqnet-sage-error.txt
    Expected: exit 0, verify_chain returns false at tampered index
    Evidence: .omo/evidence/task-3-resqnet-sage-error.txt
  ```
  Commit: Y | `feat(lib): ulid + audit hash-chain + idempotency + visibility serializer`

- [x] 4. FastAPI app skeleton: routes, auth, error model, OpenAPI, WebSocket
  What to do / Must NOT do: `backend/app/main.py` — FastAPI app with lifespan (starts Redpanda producer, stops on shutdown). Middleware: request_id (UUID, header `X-Request-Id`), org_context (resolves org_id from auth, never from client), structured JSON logger, global error handler returning `{error:{code,message,request_id}}`. Route groups: `/api/auth`, `/api/observations`, `/api/hypotheses`, `/api/scenarios`, `/api/optimize`, `/api/sensing`, `/api/eval`, `/healthz`, `/healthz/deep`, `/openapi.json`. Auth: JWT (python-jose) + passlib bcrypt, `require_roles(*roles)` dep, seed demo users (admin, emergency_manager, responder_coordinator, field_responder, shelter_manager, viewer) password `demo1234`. WebSocket endpoint `/ws/events/{incident_id}` for real-time updates (Redpanda consumer → WS fanout). Pydantic v2 schemas for all entities with `model_config = ConfigDict(from_attributes=True)`. Must NOT scatter auth/org resolution — one middleware layer.
  SOTA spec ref: §13.1 (FastAPI), §10.2 (evaluative AI interface modes), §8 (API for action portfolios)
  Parallelization: Wave 1 | Blocked by: T1, T2 | Blocks: T6-T12
  References: `DESIGN.md:147-206` (API surface to adapt), `platform/worker/src/index.ts` (existing route structure to mirror). SOTA spec §10 (human-centered decision support). aiokafka lifespan pattern from research bg_835b8072.
  Acceptance criteria: `curl -s http://localhost:8000/openapi.json | python -m json.tool` returns valid OpenAPI 3; `curl -s -X POST http://localhost:8000/api/auth/login -d 'username=admin@demo.disaster&password=demo1234'` returns JWT; WebSocket connect to `/ws/events/test-incident` returns connection accepted.
  QA scenarios:
  ```
  Scenario: auth login returns JWT
    Tool: bash
    Steps: docker compose up -d backend && curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=admin@demo.disaster&password=demo1234' | python -m json.tool | tee .omo/evidence/task-4-resqnet-sage.txt
    Expected: JSON contains access_token
    Evidence: .omo/evidence/task-4-resqnet-sage.txt
  Scenario: invalid credentials rejected
    Tool: bash
    Steps: curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=admin@demo.disaster&password=wrong' | tee .omo/evidence/task-4-resqnet-sage-error.txt
    Expected: HTTP 401
    Evidence: .omo/evidence/task-4-resqnet-sage-error.txt
  ```
  Commit: Y | `feat(api): fastapi skeleton + auth + websocket + openapi`

- [x] 5. OpenTelemetry + Prometheus + Grafana observability
  What to do / Must NOT do: `backend/app/lib/telemetry.py` — OpenTelemetry traces (FastAPI instrumentation, SQLAlchemy instrumentation, Redpafka producer/consumer spans), Prometheus metrics (request count, latency histogram, active WebSocket count, optimization solve time, ML inference time, queue depth). `prometheus.yml` config scraping backend `/metrics` endpoint. `grafana/provisioning/` dashboards: system health, request latency, optimization performance, ML model performance, feed health. Distributed trace IDs propagated from source observation to recommendation (SOTA spec §13.6). Must NOT add observability as an afterthought — wired from T1 onward.
  SOTA spec ref: §13.6 (observability), §14.7 (resilience metrics: p50/p95 latency)
  Parallelization: Wave 1 | Blocked by: T1, T4 | Blocks: all (cross-cutting)
  References: SOTA spec §13.6: "OpenTelemetry; Prometheus; Grafana; distributed trace IDs propagated from source observation to recommendation". Research bg_835b8072 (Prometheus + Grafana Docker setup).
  Acceptance criteria: `curl -s http://localhost:8000/metrics` returns Prometheus format metrics; Grafana at `http://localhost:3001` loads system health dashboard; a request to `/api/observations` produces a trace span visible in logs.
  QA scenarios:
  ```
  Scenario: metrics endpoint returns prometheus format
    Tool: bash
    Steps: curl -s http://localhost:8000/metrics | head -20 | tee .omo/evidence/task-5-resqnet-sage.txt
    Expected: output starts with # HELP / # TYPE / metric_name lines
    Evidence: .omo/evidence/task-5-resqnet-sage.txt
  ```
  Commit: Y | `feat(observability): opentelemetry traces + prometheus metrics + grafana dashboards`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 2: INGESTION + KNOWLEDGE GRAPH — SOTA spec §3 (federated data fabric), §5 (knowledge graph) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [x] 6. CAP 1.2 adapter — parse, validate, ingest CAP alerts
  What to do / Must NOT do: `backend/app/ingestion/adapters/cap.py` — parse OASIS CAP 1.2 XML alerts (from NDMA SACHET, IPAWS, or any CAP feed). Extract: alert info, area descriptions, geometry (polygon/circle), urgency, severity, certainty, effective/expires times, sender, references (for updates/cancellations). Map to observation schema (event_type=`official_alert`, source_type=`cap_feed`). Handle CAP update/cancel by setting `supersedes` field. Idempotent by CAP identifier. Must NOT auto-publish — all alerts land as `review_status=draft` if AI-generated, `official` if from verified official source.
  SOTA spec ref: §3.2 (CAP 1.2 standard), §3.3 (event schema)
  Parallelization: Wave 2 | Blocked by: T2, T4 | Blocks: T10
  References: SOTA spec §3.2: "OASIS CAP 1.2 is a standardized all-hazard format". `platform/worker/src/api/routes/ingestion.ts` (existing CAP route to port). OASIS CAP 1.2 spec: https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html
  Acceptance criteria: `cd backend && pytest tests/test_cap_adapter.py -q` — parses sample CAP XML, extracts geometry + severity, writes observation row, idempotent re-parse produces same observation_id.
  QA scenarios:
  ```
  Scenario: CAP XML parsed into observation
    Tool: bash
    Steps: cd backend && pytest tests/test_cap_adapter.py::test_parse_cap_alert -q | tee ../.omo/evidence/task-6-resqnet-sage.txt
    Expected: exit 0, observation has geometry, observed_at, source_type=cap_feed
    Evidence: .omo/evidence/task-6-resqnet-sage.txt
  ```
  Commit: Y | `feat(ingestion): CAP 1.2 adapter`

- [x] 7. SensorThings API adapter — sensor observations, datastreams
  What to do / Must NOT do: `backend/app/ingestion/adapters/sensorthings.py` — OGC SensorThings API client. Connect to SensorThings endpoints (rain gauges, river gauges, tide gauges, weather stations, air-quality sensors, IoT flood sensors). Pull Datastream → Observations → map to observation schema (event_type=`sensor_reading`, source_type=`sensorthings`). Handle pagination (`@iot.nextLink`), filtering by time range and spatial bbox. Cron-triggered pull + webhook push support. Must NOT assume sensor availability — handle 404/timeout gracefully and log feed health.
  SOTA spec ref: §3.2 (OGC SensorThings API), §4.1 (meteorological/hydrological sources)
  Parallelization: Wave 2 | Blocked by: T2, T4 | Blocks: T10
  References: SOTA spec §3.2: "Use SensorThings for observations from rain gauges, river gauges...". OGC SensorThings API spec: https://docs.ogc.org/is/15-078r6/15-078r6.html
  Acceptance criteria: `pytest tests/test_sensorthings_adapter.py -q` — mocks SensorThings endpoint, pulls 5 observations, maps to observation schema with correct phenomenon/unit/geometry.
  QA scenarios:
  ```
  Scenario: SensorThings observations ingested
    Tool: bash
    Steps: cd backend && pytest tests/test_sensorthings_adapter.py::test_pull_observations -q | tee ../.omo/evidence/task-7-resqnet-sage.txt
    Expected: exit 0, 5 observations created with correct mapping
    Evidence: .omo/evidence/task-7-resqnet-sage.txt
  ```
  Commit: Y | `feat(ingestion): SensorThings API adapter`

- [x] 8. OGC API Features adapter — roads, shelters, hospitals, boundaries
  What to do / Must NOT do: `backend/app/ingestion/adapters/ogc_features.py` — OGC API Features client. Connect to OGC API Features endpoints for vector entities (roads, shelters, hospitals, administrative boundaries, evacuation zones). Pull features by collection + bbox + datetime. Map to core entity tables (RoadSegment, Shelter, Hospital, etc.) with geometry in PostGIS. Support incremental sync (only pull features modified since last sync via `datetime` filter). Must NOT overwrite user-edited data — use upsert with conflict detection.
  SOTA spec ref: §3.2 (OGC API Features), §5.1 (core entities)
  Parallelization: Wave 2 | Blocked by: T2, T4 | Blocks: T10
  References: SOTA spec §3.2: "Use OGC API Features for roads, shelters, hospitals...". OGC API Features spec: https://docs.ogc.org/is/17-069r4/17-069r4.html
  Acceptance criteria: `pytest tests/test_ogc_adapter.py -q` — mocks OGC API Features endpoint, pulls 10 road features, creates RoadSegment rows with PostGIS LINESTRING geometry.
  QA scenarios:
  ```
  Scenario: OGC features ingested as entities
    Tool: bash
    Steps: cd backend && pytest tests/test_ogc_adapter.py::test_pull_roads -q | tee ../.omo/evidence/task-8-resqnet-sage.txt
    Expected: exit 0, road segments created with geometry
    Evidence: .omo/evidence/task-8-resqnet-sage.txt
  ```
  Commit: Y | `feat(ingestion): OGC API Features adapter`

- [x] 9. STAC catalog + HDX HAPI adapter — satellite imagery indexing, humanitarian data
  What to do / Must NOT do: `backend/app/ingestion/adapters/stac.py` — STAC client (pystac-client) for satellite/aerial/drone imagery indexing. Index by location, time, sensor, cloud cover. Store metadata in DB, actual imagery in MinIO (S3-compatible). Support local STAC catalog for offline imagery. `backend/app/ingestion/adapters/hdx.py` — HDX Humanitarian API client for standardized humanitarian indicators and operational datasets. Must NOT require internet at runtime — support cached/pre-downloaded catalogs for offline operation.
  SOTA spec ref: §3.2 (STAC), §3.2 (HDX HAPI), §13.2 (pgSTAC/object storage)
  Parallelization: Wave 2 | Blocked by: T1, T2 | Blocks: T18 (SAR pipeline needs STAC)
  References: SOTA spec §3.2: "Use the SpatioTemporal Asset Catalog specification for satellite, aerial and drone imagery". SOTA spec §3.2: "For standardized humanitarian indicators... use HDX Humanitarian API". Note: "OCHA retired HDX HXL services on January 31, 2026" — use HAPI, not HXL.
  Acceptance criteria: `pytest tests/test_stac_adapter.py -q` — indexes 3 sample STAC items, stores metadata in DB; `pytest tests/test_hdx_adapter.py -q` — pulls 2 humanitarian indicators.
  QA scenarios:
  ```
  Scenario: STAC items indexed
    Tool: bash
    Steps: cd backend && pytest tests/test_stac_adapter.py::test_index_stac_items -q | tee ../.omo/evidence/task-9-resqnet-sage.txt
    Expected: exit 0, 3 STAC items indexed with location/time/sensor metadata
    Evidence: .omo/evidence/task-9-resqnet-sage.txt
  ```
  Commit: Y | `feat(ingestion): STAC catalog + HDX HAPI adapters`

- [x] 10. Event-time processing pipeline — Redpanda + Benthos (normalize → dedup → store with provenance)
  What to do / Must NOT do: `backend/app/streaming/producer.py` — aiokafka async producer writing to Redpanda topic `observations.raw`. `backend/app/streaming/consumer.py` — async consumer reading from `observations.normalized` topic → INSERT to PostgreSQL with provenance. `benthos/disaster_pipeline.yaml` — Benthos config: input from `observations.raw`, normalize (bloblang: timestamp to epoch ms, source_type uppercase, coordinate normalization, metadata target_topic), dedup by observation_id (Redis cache), switch-route to type-specific topics (`observations.sensor`, `observations.citizen`, `observations.satellite`, `alerts.official`), DLQ to `observations.dlq`. Schema registry with Avro. PostgreSQL LISTEN/NOTIFY for instant dashboard updates. Must NOT lose observations on processing failure — DLQ + idempotency keys on every message.
  SOTA spec ref: §3.1 (federated ingestion), §3.3 (three different times: observed/received/valid), §13.1 (Kafka/Redpanda + Benthos)
  Parallelization: Wave 2 | Blocked by: T1, T2, T4 | Blocks: T11
  References: SOTA spec §13.1: "Kafka, Redpanda or Pulsar for event transport... For a smaller prototype, Redpanda plus Benthos or a lightweight stream processor may be sufficient." Research bg_835b8072: Redpanda Docker setup (1GB, dev-container), aiokafka producer/consumer patterns, Benthos YAML pipeline (bloblang + dedup + switch routing), Avro schema registry.
  Acceptance criteria: `docker compose exec redpanda rpk topic list` shows all topics; produce a test observation to `observations.raw` → it appears in `observations.normalized` → INSERT in PostgreSQL; duplicate observation_id is deduped; a malformed message goes to DLQ.
  QA scenarios:
  ```
  Scenario: observation flows through pipeline
    Tool: bash
    Steps: docker compose up -d && python -c "import asyncio; from app.streaming.producer import producer_manager; asyncio.run(producer_manager.start()); asyncio.run(producer_manager.send('observations.raw', {'observation_id':'test1','source_type':'SENSOR','lat':26.0,'lon':-80.0,'timestamp':'2026-01-01T00:00:00Z'}))" && sleep 2 && docker compose exec db psql -U disaster -c "SELECT count(*) FROM observations WHERE observation_id='test1';" | tee .omo/evidence/task-10-resqnet-sage.txt
    Expected: count = 1
    Evidence: .omo/evidence/task-10-resqnet-sage.txt
  Scenario: duplicate observation deduped
    Tool: bash
    Steps: (produce same observation_id twice) && docker compose exec db psql -U disaster -c "SELECT count(*) FROM observations WHERE observation_id='test1';" | tee .omo/evidence/task-10-resqnet-sage-error.txt
    Expected: count = 1 (deduped)
    Evidence: .omo/evidence/task-10-resqnet-sage-error.txt
  ```
  Commit: Y | `feat(streaming): Redpanda + Benthos event-time pipeline`

- [x] 11. Temporal crisis knowledge graph — entities, relationships, contradictory hypotheses (Apache AGE)
  What to do / Must NOT do: `backend/app/knowledge/graph.py` — build and query the temporal crisis knowledge graph using Apache AGE (PostgreSQL extension). Create graph per incident. Vertices: all entities from T2 (hazards, zones, buildings, roads, bridges, substations, towers, hospitals, shelters, responders, vehicles, sensors, tasks, decisions, observations, hypotheses). Edges per SOTA spec §5.2: ROAD passes_through ZONE, ROAD provides_access_to HOSPITAL, SHELTER has_capacity, ZONE affected_by FLOOD, TOWER powered_by SUBSTATION, REPORT refers_to BUILDING, RESPONDER assigned_to TASK, TASK requires VEHICLE_TYPE, HOSPITAL reachable_via ROUTE, OBSERVATION supports HYPOTHESIS, OBSERVATION contradicts HYPOTHESIS, ACTION supersedes ACTION. Each edge carries `valid_from`, `valid_until`, `properties` (JSONB). Queries via Cypher: multi-hop traversal for cascading impact analysis. Must NOT use a separate graph database — AGE runs inside PostgreSQL. Fallback: if AGE not available, use `graph_edges` table + recursive CTEs.
  SOTA spec ref: §5 (temporal crisis knowledge graph), §5.2 (relationships), §5.3 (contradictory hypotheses)
  Parallelization: Wave 2 | Blocked by: T2, T10 | Blocks: T13 (fusion reads from graph)
  References: SOTA spec §5.1 (core entities), §5.2 (relationships list), §5.3 ("Do not silently choose one version and discard the rest"). Research bg_835b8072: Apache AGE setup (`apache/age:latest`), `create_graph()`, Cypher query format (`SELECT * FROM cypher('graph', $$ MATCH ... $$) AS (...)`).
  Acceptance criteria: `pytest tests/test_knowledge_graph.py -q` — creates 5 entities + 5 edges, queries 2-hop neighbors. **If T51 kept AGE**: queries via Cypher (`SELECT * FROM cypher(...)`). **If T51 dropped AGE**: queries via recursive CTE over `graph_edges` table. Both paths must return correct 2-hop results. `pytest tests/test_hypotheses.py` — creates 2 contradictory hypotheses for same entity, both preserved with supporting/contradicting evidence.
  QA scenarios:
  ```
  Scenario: 2-hop graph query returns correct neighbors
    Tool: bash
    Steps: cd backend && pytest tests/test_knowledge_graph.py::test_two_hop_query -q | tee ../.omo/evidence/task-11-resqnet-sage.txt
    Expected: exit 0, query returns entities 2 hops from start node
    Evidence: .omo/evidence/task-11-resqnet-sage.txt
  Scenario: contradictory hypotheses both preserved
    Tool: bash
    Steps: cd backend && pytest tests/test_hypotheses.py::test_contradictory_hypotheses_preserved -q | tee ../.omo/evidence/task-11-resqnet-sage-error.txt
    Expected: exit 0, both H1 (passable) and H2 (impassable) exist with their evidence
    Evidence: .omo/evidence/task-11-resqnet-sage-error.txt
  ```
  Commit: Y | `feat(knowledge): temporal crisis knowledge graph + contradictory hypotheses`

- [x] 12. Federated data fabric — source ownership, policy-controlled sharing, delayed sync
  What to do / Must NOT do: `backend/app/ingestion/federation.py` — support central feeds (full data), federated queries (query remote endpoints, don't copy data), aggregated outputs (receive summaries, not raw data), local edge processing (process locally, sync results). `sources` table: `id`, `org_id`, `name`, `type` (enum), `provider`, `refresh_interval_s`, `last_success_at`, `last_error`, `status`, `config` (JSONB), `access_policy` (enum), `ownership` (enum: owned/federated/aggregated). Delayed sync: outbox table for observations created offline, sync when connectivity restored, dedup by content hash. Must NOT blindly centralize all data — respect source ownership and access policies.
  SOTA spec ref: §3.1 (federated data fabric), §3.2 (standards), §11 (resilient communications)
  Parallelization: Wave 2 | Blocked by: T2, T4 | Blocks: T37 (offline sync)
  References: SOTA spec §3.1: "Utilities, police, hospitals and telecom providers may not permit raw operational data to leave their infrastructure." SOTA spec §3.1: "retain source ownership and provenance instead of copying all data into an unrestricted central database."
  Acceptance criteria: `pytest tests/test_federation.py -q` — registers a federated source, queries it remotely (mocked), receives aggregated output without copying raw data; delayed sync: 3 observations created offline, sync produces 3 inserts + 0 duplicates.
  QA scenarios:
  ```
  Scenario: federated query returns aggregated data
    Tool: bash
    Steps: cd backend && pytest tests/test_federation.py::test_federated_query -q | tee ../.omo/evidence/task-12-resqnet-sage.txt
    Expected: exit 0, aggregated data received without raw data copy
    Evidence: .omo/evidence/task-12-resqnet-sage.txt
  ```
  Commit: Y | `feat(ingestion): federated data fabric + delayed sync`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 3: PROBABILISTIC EVIDENCE FUSION — SOTA spec §6 -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 13. Confidence vector computation (6 dimensions: source reliability, corroboration, freshness, geo precision, model uncertainty, conflict)
  What to do / Must NOT do: `backend/app/fusion/confidence.py` — compute confidence vector `q_i = [S_i, C_i, F_i, G_i, M_i, K_i]` for each observation per SOTA spec §6.1. `S_i` (source reliability): from Beta model (T14). `C_i` (corroboration strength): count of other observations within spatial+temporal window supporting same claim, normalized 0-1. `F_i` (freshness): exponential decay `F_i(t) = exp(-(t-t_i)/tau_k)` per phenomenon type (T15). `G_i` (geographic precision): based on source type (exact GPS=1.0, road segment=0.7, ward=0.3, vague text=0.1). `M_i` (model uncertainty): from ML model confidence or None for direct observations. `K_i` (conflict level): 0 if no contradictions, increases with number/strength of contradicting observations. Store all 6 dimensions per observation in `quality_flags` JSONB. Compute display confidence as weighted sum only for UI, but NEVER compress for the reasoning engine. Must NOT reduce to single scalar internally.
  SOTA spec ref: §6.1 (confidence vector), §6.2 (freshness), §6.3 (source reliability), §6.4 (probabilistic world state)
  Parallelization: Wave 3 | Blocked by: T2, T11 | Blocks: T16, T26
  References: SOTA spec §6.1: "For observation i, retain: q_i = [S_i, C_i, F_i, G_i, M_i, K_i]". `platform/worker/src/lib/scoring/taskPriority.ts` (existing scalar score to replace). Research bg_ba8ac5cb: pgmpy for DBN, analytic Beta updates for source reliability.
  Acceptance criteria: `pytest tests/test_confidence_vector.py -q` — computes all 6 dimensions for 5 test observations; corroboration dimension increases when 2 observations support same claim; conflict dimension increases when contradicting observation added.
  QA scenarios:
  ```
  Scenario: confidence vector has 6 dimensions
    Tool: bash
    Steps: cd backend && pytest tests/test_confidence_vector.py::test_six_dimensions -q | tee ../.omo/evidence/task-13-resqnet-sage.txt
    Expected: exit 0, vector has S, C, F, G, M, K values
    Evidence: .omo/evidence/task-13-resqnet-sage.txt
  ```
  Commit: Y | `feat(fusion): confidence vector computation (6D)`

- [ ] 14. Source reliability Beta model — updates with field verification, conditioned on report type
  What to do / Must NOT do: `backend/app/fusion/reliability.py` — `SourceReliabilityTracker` class with Beta(α, β) per source. Initialize with prior Beta(2, 2). On field verification: `α += 1` if verified correct, `β += 1` if disproved. Apply time decay so old performance doesn't dominate: `α_eff = α * decay_factor`, `β_eff = β * decay_factor`. Condition on report type: a source can be reliable for road observations but poor at flood depth — store separate (α, β) per (source_id, phenomenon_type). Expected reliability = α/(α+β). 95% credible interval via scipy.stats.beta.ppf. Must NOT assign permanent credibility — always updatable.
  SOTA spec ref: §6.3 (source reliability should update over time)
  Parallelization: Wave 3 | Blocked by: T2 | Blocks: T13
  References: SOTA spec §6.3: "A responder, sensor, social account or predictive model should not have a permanently assigned credibility." SOTA spec §6.3: "This should be conditioned on report type." Research bg_ba8ac5cb: "Analytic Beta-Binomial conjugate updates (O(1) per update — perfect for FastAPI)".
  Acceptance criteria: `pytest tests/test_reliability.py -q` — tracker starts at 0.5, 3 correct reports → reliability > 0.6, 2 disproven → reliability < 0.4; conditioned reliability: same source reliable for roads (α=10, β=1) but poor for flood_depth (α=1, β=10).
  QA scenarios:
  ```
  Scenario: reliability updates with verification
    Tool: bash
    Steps: cd backend && pytest tests/test_reliability.py::test_reliability_updates -q | tee ../.omo/evidence/task-14-resqnet-sage.txt
    Expected: exit 0, reliability moves from 0.5 to >0.6 after 3 correct
    Evidence: .omo/evidence/task-14-resqnet-sage.txt
  ```
  Commit: Y | `feat(fusion): Beta-distributed source reliability with type conditioning`

- [ ] 15. Phenomenon-specific freshness decay — per-observation-type τ
  What to do / Must NOT do: `backend/app/fusion/freshness.py` — freshness function `F_i(t) = exp(-(t - t_i) / tau_k)` where τ_k depends on observation type k. Configurable τ per phenomenon: responder_position (τ=60s), road_passability (τ=600s), shelter_capacity (τ=1800s), building_footprint (τ=86400s), demographic_vulnerability (τ=2592000s). Store τ config in `settings` table (tenant-overridable). Compute freshness on read (not write) so it's always current. Must NOT use same expiry for every feed — phenomenon-specific.
  SOTA spec ref: §6.2 (phenomenon-specific freshness)
  Parallelization: Wave 3 | Blocked by: T2 | Blocks: T13
  References: SOTA spec §6.2: "Using the same expiry period for every feed would be incorrect." SOTA spec §6.2 provides τ examples.
  Acceptance criteria: `pytest tests/test_freshness.py -q` — road observation 60s old has F > 0.9 (F=exp(-60/600)=0.905); same observation 2h old has F < 0.01 (F=exp(-7200/600)≈0.000006); building footprint 1h old has F > 0.9 (F=exp(-3600/86400)=0.959, large τ=86400s).
  QA scenarios:
  ```
  Scenario: freshness decays differently per type
    Tool: bash
    Steps: cd backend && pytest tests/test_freshness.py::test_per_type_decay -q | tee ../.omo/evidence/task-15-resqnet-sage.txt
    Expected: exit 0, road F < building F for same age
    Evidence: .omo/evidence/task-15-resqnet-sage.txt
  ```
  Commit: Y | `feat(fusion): phenomenon-specific freshness decay`

- [ ] 16. Probabilistic world state estimation — pgmpy Dynamic Bayesian Network (P(X_t | O_{1:t}))
  What to do / Must NOT do: `backend/app/fusion/world_state.py` — Dynamic Bayesian Network using pgmpy `DynamicBayesianNetwork` + `DBNInference`. Define crisis state nodes per hazard type (e.g., flood_severity ∈ {none, minor, moderate, severe, extreme}). Inter-slice edges: state_t → state_t+1 (transition). Intra-slice edges: state → sensor_reading, state → citizen_report, state → satellite_observation. CPDs: transition matrix (P(state_t+1 | state_t)), sensor model (P(reading | state)), report model (P(report | state)). `forward_inference(variables=[(state, t)], evidence={...})` for filtering P(X_t | O_{1:t}). Wrap in stateful service class with potential caching for rolling window (last N time slices). Convert heterogeneous evidence (sensor readings, citizen reports, ML outputs) to discrete observations for the DBN. Must NOT use MCMC for real-time — use exact inference (pgmpy's junction tree).
  SOTA spec ref: §6.4 (probabilistic world state), §6.4 (implementation options: Bayesian networks, DBNs)
  Parallelization: Wave 3 | Blocked by: T13 | Blocks: T23 (digital twin reads world state)
  References: SOTA spec §6.4: "P(X_t | O_{1:t})". SOTA spec §6.4: "Bayesian networks; dynamic Bayesian networks; factor graphs; particle filters; Dempster-Shafer". Research bg_ba8ac5cb: pgmpy v1.1.2 active, `DBNInference.forward_inference()`, uses `(node, time_slice)` tuples, exact inference via Interface Algorithm. "PyMC's MCMC is too slow for real-time FastAPI request handling (seconds vs milliseconds for pgmpy's exact inference)."
  Acceptance criteria: `pytest tests/test_world_state.py -q` — DBN with 3-state flood severity, 3 time slices, forward inference returns probability distribution summing to 1.0; evidence of severe flood increases P(severe) from prior 0.1 to > 0.5.
  QA scenarios:
  ```
  Scenario: DBN forward inference produces valid distribution
    Tool: bash
    Steps: cd backend && pytest tests/test_world_state.py::test_forward_inference -q | tee ../.omo/evidence/task-16-resqnet-sage.txt
    Expected: exit 0, probabilities sum to 1.0, P(severe) > 0.5 with severe evidence
    Evidence: .omo/evidence/task-16-resqnet-sage.txt
  ```
  Commit: Y | `feat(fusion): pgmpy DBN probabilistic world state estimation`

- [ ] 17. Conformal calibration layer — MAPIE (Brier score, ECE, conformal prediction sets, reliability diagrams)
  What to do / Must NOT do: `backend/app/fusion/calibration.py` — wrap ML model predictions with MAPIE conformal prediction intervals. `MapieTimeSeriesRegressor` for time series (EnbPI, `partial_fit` for streaming). `MapieRegressor` for static calibration. Compute and store: Brier score, expected calibration error (ECE), reliability diagram data, negative log likelihood, conformal coverage, interval width, false-confidence rate. Geographically weighted conformal: calibrate per H3 zone to handle spatial distribution shift. Calibration dashboard endpoint returning all metrics. Must NOT claim calibrated uncertainty without empirical validation — compute actual coverage.
  SOTA spec ref: §6.5 (calibrated uncertainty), §14.5 (uncertainty metrics)
  Parallelization: Wave 3 | Blocked by: T13 | Blocks: T44 (evaluation metrics)
  References: SOTA spec §6.5: "Brier score; expected calibration error; reliability diagrams; negative log likelihood; conformal prediction coverage; selective-risk curves." SOTA spec §6.5: "Conformal prediction is particularly useful because it can produce prediction sets or intervals with statistical coverage guarantees." SOTA spec §6.5: "Geographically weighted conformal methods may improve calibration under spatial distribution shift." Research bg_ba8ac5cb: MAPIE v1.4.1 (June 2026), scikit-learn-contrib, `MapieTimeSeriesRegressor.partial_fit()`.
  Acceptance criteria: `pytest tests/test_calibration.py -q` — wraps a mock classifier, computes Brier score + ECE, conformal coverage >= requested alpha; `partial_fit` updates intervals with new data.
  QA scenarios:
  ```
  Scenario: conformal coverage meets target
    Tool: bash
    Steps: cd backend && pytest tests/test_calibration.py::test_coverage -q | tee ../.omo/evidence/task-17-resqnet-sage.txt
    Expected: exit 0, coverage >= 0.89 for alpha=0.1 (90% target)
    Evidence: .omo/evidence/task-17-resqnet-sage.txt
  ```
  Commit: Y | `feat(fusion): conformal calibration (MAPIE) + uncertainty metrics`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 4: ML PERCEPTION — SOTA spec §4 (multimodal crisis perception) -->
<!-- NOTE: This wave PARALLELIZES with Waves 2-3 (only depends on Wave 1 + T9) -->
<!-- INTRA-WAVE ORDER: T22 (model serving infrastructure) MUST be completed FIRST, then T18-T21 can parallelize. T18-T21 all depend on T22's serving layer. -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 18. SAR flood mapping pipeline — Sentinel-1 acquisition + TorchGeo + DOFA + probabilistic output
  What to do / Must NOT do: `backend/app/perception/flood_mapping.py` — end-to-end SAR flood mapping pipeline. (1) Data acquisition: CDSETool (`from cdsetool.query import query_features; from cdsetool.download import download_features`) for Sentinel-1 GRD products from Copernicus Data Space Ecosystem — NOT sentinelsat (archived/dead). Support "sync when connected" pattern: download available scenes when internet is up, cache in MinIO. (2) Loading: TorchGeo `Sentinel1` dataset class (`from torchgeo.datasets import Sentinel1`, bands=['VV','VH'], separate_files=True) or rasterio for direct file access. (3) Model: DOFA foundation model (`from torchgeo.models import dofa_base_patch16_224, DOFABase16_Weights`) with wavelength=[5.405, 5.405] for C-band SAR. Fine-tune a segmentation head on flood dataset (Sen1Floods11 or WorldFloods). (4) Output: flood probability per pixel (softmax), water depth estimate (DEM fusion via HAND method), uncertainty interval (Monte Carlo Dropout, n=30 samples), model disagreement (ensemble variance), observation time, cloud/sensor quality flag, change from previous observation. Store as COG (Cloud Optimized GeoTIFF) in MinIO via rasterio + rio-cogeo. (5) Copernicus GFM integration: fuse GFM operational product with model output. Must NOT convert to binary flooded/not-flooded immediately — preserve probabilities.
  SOTA spec ref: §4.2 (flood mapping from Earth observation), §4.2 (required outputs), §6.5 (calibrated uncertainty)
  Parallelization: Wave 4 (parallel with W2-W3) | Blocked by: T1, T9 | Blocks: T23
  References: SOTA spec §4.2: "Sentinel-1 synthetic-aperture radar can observe through cloud and at night." SOTA spec §4.2: "The flood model should produce: flood probability per pixel; estimated water depth distribution; uncertainty interval; observation time; model disagreement; cloud or sensor quality flag; change from previous observation." Research bg_bac2773d: CDSETool replaces sentinelsat, DOFA built into TorchGeo, `Sentinel1` dataset class, Monte Carlo Dropout for uncertainty, COG output via rio-cogeo, GFM via Sentinel Hub API.
  Acceptance criteria: `pytest tests/test_flood_mapping.py -q` — loads sample SAR tensor [2, 224, 224], runs DOFA inference, outputs flood probability map [224, 224] in [0,1], uncertainty std map, writes COG to MinIO. (Use fixture tensor, no real satellite data needed for unit test.)
  QA scenarios:
  ```
  Scenario: flood map produced from SAR tensor
    Tool: bash
    Steps: cd backend && pytest tests/test_flood_mapping.py::test_inference -q | tee ../.omo/evidence/task-18-resqnet-sage.txt
    Expected: exit 0, flood_prob shape [224,224], values in [0,1], uncertainty map present
    Evidence: .omo/evidence/task-18-resqnet-sage.txt
  ```
  Commit: Y | `feat(perception): SAR flood mapping pipeline (DOFA + probabilistic output)`

- [ ] 19. Foundation model ensemble + model disagreement tracking
  What to do / Must NOT do: `backend/app/perception/ensemble.py` — ensemble of multiple flood mapping models: (1) DOFA fine-tuned, (2) TorchGeo ResNet50 with SENTINEL1_GRD_MOCO weights + segmentation head, (3) Copernicus GFM operational product. Ensemble output = weighted average of per-pixel probabilities. Model disagreement = variance across ensemble members per pixel (flag high-disagreement zones). Weight models by per-zone calibration performance (from T17). Must NOT hide model disagreement — preserve it as a separate output layer. Must NOT claim one model solves flood mapping universally.
  SOTA spec ref: §4.2 ("the correct choice is an ensemble, not an unsupported claim that one foundation model solves flood mapping universally"), §4.2 ("Copernicus GFM uses multiple independent algorithms and harmonizes their outputs into an ensemble flood likelihood")
  Parallelization: Wave 4 | Blocked by: T18 | Blocks: T23
  References: SOTA spec §4.2: "A strong ensemble would include: a conventional U-Net or SegFormer baseline; a geospatial foundation model such as Clay, Prithvi, DOFA or TerraMind; weakly supervised SAR models; Copernicus Global Flood Monitoring outputs; local hydrodynamic forecasts; terrain and drainage priors." Research bg_bac2773d: DOFA, Tessera, ResNet50 S1 weights all available in TorchGeo. Clay via `claymodel.module.ClayMAEModule`. TerraMind via `rslearn.models.terramind`.
  Acceptance criteria: `pytest tests/test_ensemble.py -q` — 3 models produce different flood maps, ensemble averages them, disagreement map shows non-zero variance where models disagree.
  QA scenarios:
  ```
  Scenario: ensemble produces disagreement map
    Tool: bash
    Steps: cd backend && pytest tests/test_ensemble.py::test_disagreement -q | tee ../.omo/evidence/task-19-resqnet-sage.txt
    Expected: exit 0, disagreement map has non-zero values where models differ
    Evidence: .omo/evidence/task-19-resqnet-sage.txt
  ```
  Commit: Y | `feat(perception): flood mapping ensemble with disagreement tracking`

- [ ] 20. Building & road damage assessment — xBD/xView2 + SpaceNet 8 + road passability probability
  What to do / Must NOT do: `backend/app/perception/damage.py` — (1) Building damage: fine-tune model on xBD/xView2 dataset, classify buildings into {no damage, minor, major, destroyed} from post-event imagery (or pre+post pair when available). Support single-post-event-image models when pre-event imagery is missing. (2) Road network: SpaceNet 8 approach connecting building extraction, road extraction, and flood-status detection. Output per road segment: P(passable for vehicle class), expected traversal speed, expected failure time, last confirmation source, alternate route availability. A road can be passable for a boat while unsafe for an ambulance. (3) Output as GeoJSON features with damage probability + uncertainty. Must NOT output "road segmentation mIoU" — output operational passability.
  SOTA spec ref: §4.3 (building and road damage), §4.3 (required operational output)
  Parallelization: Wave 4 | Blocked by: T1 | Blocks: T28 (route reliability)
  References: SOTA spec §4.3: "SpaceNet 8 is particularly relevant because it connects three tasks: building extraction; road-network extraction; flood-status detection." SOTA spec §4.3: "The operational output should not be 'road segmentation mIoU.' It should be: probability the road is passable for each vehicle class; likely traversal speed; expected failure time; last confirmation source; alternate route availability." Research bg_bac2773d: TorchGeo models available, fine-tune on xBD/SpaceNet 8.
  Acceptance criteria: `pytest tests/test_damage.py -q` — classifies building damage from fixture image, outputs damage probability + class; road segment passability: ambulance P=0.2, boat P=0.9 (different vehicle classes).
  QA scenarios:
  ```
  Scenario: road passability differs by vehicle class
    Tool: bash
    Steps: cd backend && pytest tests/test_damage.py::test_vehicle_class_passability -q | tee ../.omo/evidence/task-20-resqnet-sage.txt
    Expected: exit 0, ambulance passability < boat passability for flooded road
    Evidence: .omo/evidence/task-20-resqnet-sage.txt
  ```
  Commit: Y | `feat(perception): building/road damage assessment + vehicle-class passability`

- [ ] 21. Social media & citizen report NLP pipeline — multilingual ASR, urgency, geolocation
  What to do / Must NOT do: `backend/app/perception/nlp.py` — process citizen reports, social media, helpline calls through: (1) Language identification + multilingual ASR (Whisper or equivalent for speech-to-text). (2) PII detection + access control redaction before any LLM call. (3) Urgency extraction (low/medium/high/critical). (4) Humanitarian category extraction: trapped/missing person, medical emergency, flooding, structural collapse, fire/electrical, blocked route, shelter request, food/water/medication, infrastructure outage, rescue completed, irrelevant. (5) Place-name extraction + geolocation candidate generation: represent as exact coordinate, road segment, building, named place, ward, candidate-location distribution, or uncertainty polygon — NEVER invent exact GPS from vague report. (6) Image/OCR corroboration. (7) Duplicate/near-duplicate clustering (embedding similarity via FAISS). (8) Credibility + uncertainty estimation (feeds confidence vector). (9) Human review queue when operationally consequential. Must NOT send PII to unrestricted third-party models.
  SOTA spec ref: §4.4 (social media, helplines and citizen reports), §4.4 (required humanitarian categories), §4.4 (geolocation), §4.4 (multimodal limitations), §12.3 (LLM isolation)
  Parallelization: Wave 4 | Blocked by: T1, T4 | Blocks: T13 (confidence vector uses NLP output)
  References: SOTA spec §4.4: pipeline: "Speech or text input → Language identification → Multilingual ASR → PII detection → Urgency/category extraction → Place-name extraction → Geolocation candidate generation → Image/OCR corroboration → Duplicate clustering → Credibility estimation → Human review". SOTA spec §4.4: "Never invent an exact GPS point from a vague report." Datasets: CrisisMMD, HumAID, CrisisBench, CrisisNLP.
  Acceptance criteria: `pytest tests/test_nlp.py -q` — processes 5 test reports (mix of English, Hindi, code-mixed), extracts urgency + category + geolocation candidate (distribution, not point), flags PII for redaction, clusters 2 duplicate reports.
  QA scenarios:
  ```
  Scenario: vague geolocation represented as distribution
    Tool: bash
    Steps: cd backend && pytest tests/test_nlp.py::test_vague_geolocation -q | tee ../.omo/evidence/task-21-resqnet-sage.txt
    Expected: exit 0, "near the old market" produces candidate-location distribution, not exact point
    Evidence: .omo/evidence/task-21-resqnet-sage.txt
  ```
  Commit: Y | `feat(perception): multilingual NLP pipeline + geolocation + duplicate clustering`

- [ ] 22. ML model serving infrastructure — ONNX Runtime, model registry, lazy loading for local hardware
  What to do / Must NOT do: `backend/app/perception/serving.py` — model serving layer for local hardware with limited resources. (1) ONNX Runtime for CPU-optimized inference (`onnxruntime.InferenceSession` with CPU execution provider). (2) Model registry: `models` table (`id`, `name`, `version`, `framework` (pytorch/onnx), `task` (flood_mapping/damage/nlp), `r2_key`, `input_schema`, `output_schema`, `calibration_metrics` JSONB, `created_at`). (3) Lazy loading: models loaded on first request, cached in memory, unloaded after idle timeout. (4) Pre-download script: `scripts/download_models.py` — downloads all required model weights + sample SAR data when internet is available, stores in MinIO + local cache. (5) Model versioning: every inference records model_version in observation's `model_version` field for provenance. Must NOT require internet at runtime for model inference — all models cached locally.
  SOTA spec ref: §13.4 (ML stack: ONNX Runtime at edge), §12.4 (model versions in provenance)
  Parallelization: Wave 4 | Blocked by: T1 | Blocks: T18-T21 (all ML todos use serving layer)
  References: SOTA spec §13.4: "ONNX Runtime or TensorRT at edge". SOTA spec §13.4: "MLflow or a similar model registry". SOTA spec §12.4: "Model versions" in provenance. User constraint: "everything must work on local hardware with low internet connectivity."
  Acceptance criteria: `pytest tests/test_serving.py -q` — lazy-loads a mock ONNX model, runs inference, unloads after timeout; `scripts/download_models.py --list` shows all models to pre-cache.
  QA scenarios:
  ```
  Scenario: model lazy-loaded and cached
    Tool: bash
    Steps: cd backend && pytest tests/test_serving.py::test_lazy_loading -q | tee ../.omo/evidence/task-22-resqnet-sage.txt
    Expected: exit 0, model loaded on first call, second call uses cache
    Evidence: .omo/evidence/task-22-resqnet-sage.txt
  ```
  Commit: Y | `feat(perception): ONNX model serving + registry + lazy loading`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 5: HAZARD & INFRASTRUCTURE DIGITAL TWIN — SOTA spec §7 -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 23. Scenario ensemble generator — N scenarios varying rainfall, surge, drainage, road failure
  What to do / Must NOT do: `backend/app/twin/scenarios.py` — generate N scenarios Ω = {ω_1, ..., ω_N}. Each scenario varies: rainfall trajectory, storm-surge height, embankment failure, drainage blockage, road failure, power restoration, shelter inflow, hospital demand, communication availability. Each scenario has probability p_ω (or included in robust uncertainty set when reliable probabilities unavailable). Scenario generator reads current world state from DBN (T16) + flood maps (T18) + infrastructure status. Store scenarios in `scenarios` table. Generate 10-50 scenarios per operational cycle. Must NOT produce one forecast — produce an ensemble.
  SOTA spec ref: §7.1 (scenario ensemble), §7.2 (cascading dependencies)
  Parallelization: Wave 5 | Blocked by: T16 (world state), T18 (flood maps) | Blocks: T26 (optimizer uses scenarios)
  References: SOTA spec §7.1: "Instead of one flood forecast, produce N scenarios: Ω = {ω_1, ω_2, ..., ω_N}. Each scenario has probability p_ω, or is included in a robust uncertainty set when reliable probabilities are unavailable."
  Acceptance criteria: `pytest tests/test_scenarios.py -q` — generates 20 scenarios from mock world state, each has unique params + probability, probabilities sum to ~1.0.
  QA scenarios:
  ```
  Scenario: 20 scenarios generated with probabilities
    Tool: bash
    Steps: cd backend && pytest tests/test_scenarios.py::test_ensemble_generation -q | tee ../.omo/evidence/task-23-resqnet-sage.txt
    Expected: exit 0, 20 scenarios, probabilities sum to ~1.0
    Evidence: .omo/evidence/task-23-resqnet-sage.txt
  ```
  Commit: Y | `feat(twin): scenario ensemble generator`

- [ ] 24. Cascading infrastructure dependency DAG — flooding → substation → tower → comms → observability
  What to do / Must NOT do: `backend/app/twin/cascading.py` — model infrastructure dependencies as a DAG. Nodes: substations, cell towers, hospitals, shelters, roads, bridges, water supply, sewage. Edges: `POWERED_BY`, `PROVIDES_ACCESS_TO`, `DEPENDS_ON`. Cascade simulation: BFS/DFS over DAG when a node fails. Example chains from SOTA spec §7.2: (1) Flooding → substation failure → tower power loss → communication outage → fewer citizen reports → reduced observability. (2) Flooding → road closure → hospital travel-time increase → ambulance availability reduction → higher untreated-casualty risk. (3) Shelter congestion → sanitation/medical pressure → secondary evacuation demand. Track cascade depth + blast radius. Must NOT independently draw power, flood, telecom layers — model their dependencies.
  SOTA spec ref: §7.2 (cascading infrastructure dependencies)
  Parallelization: Wave 5 | Blocked by: T11 (knowledge graph), T16 (world state) | Blocks: T26
  References: SOTA spec §7.2: "This is significantly more insightful than independently drawing power, flood and telecom layers on a map." SOTA spec §7.2 provides 3 example cascade chains. `backend/app/knowledge/graph.py` (T11) provides the graph.
  Acceptance criteria: `pytest tests/test_cascading.py -q` — DAG with 10 nodes + 15 edges, simulate substation failure, verify cascade reaches cell tower (depth 2) + hospital access (depth 3); blast radius = 4 affected nodes.
  QA scenarios:
  ```
  Scenario: cascade reaches expected nodes
    Tool: bash
    Steps: cd backend && pytest tests/test_cascading.py::test_substation_cascade -q | tee ../.omo/evidence/task-24-resqnet-sage.txt
    Expected: exit 0, substation failure cascades to tower + hospital
    Evidence: .omo/evidence/task-24-resqnet-sage.txt
  ```
  Commit: Y | `feat(twin): cascading infrastructure dependency DAG`

- [ ] 25. Telecom silence residual model — expected report rate, residual computation, bias correction
  What to do / Must NOT do: `backend/app/twin/silence.py` — estimate expected report rate `r_hat_{z,t} = f(population, normal_activity, hazard_intensity, historical_reporting, network_availability)`. Compute observed report rate `r_{z,t}^observed` per zone z per time window. Residual = `r_hat - r_observed`. Large residual becomes meaningful when combined with: known tower failure, power outage, failed call attempts, previously active devices becoming unreachable, high vulnerability, increasing hazard. Must correct for areas with historically low smartphone ownership, weak network coverage, limited social-media use — otherwise systematically misrepresents poorer communities. Must NOT implement as "no reports = high danger" — must compare to expected rate.
  SOTA spec ref: §7.3 (telecom silence as residual signal)
  Parallelization: Wave 5 | Blocked by: T11 (graph), T24 (cascade — tower failures reduce observability) | Blocks: T30 (active sensing uses silence residual)
  References: SOTA spec §7.3: "Your 'telecom silence' idea is strong, but it should not be implemented as: No reports = high danger." SOTA spec §7.3: "The model must correct for areas with historically low smartphone ownership, weak network coverage or limited social-media use."
  Acceptance criteria: `pytest tests/test_silence.py -q` — zone with population 1000, expected 5 reports/hr, observed 0 reports, tower failed → residual = 5, flagged as meaningful; zone with population 100, expected 0.5 reports/hr, observed 0 → residual = 0.5, NOT flagged (low-connectivity area).
  QA scenarios:
  ```
  Scenario: silence residual flags meaningful silence
    Tool: bash
    Steps: cd backend && pytest tests/test_silence.py::test_meaningful_silence -q | tee ../.omo/evidence/task-25-resqnet-sage.txt
    Expected: exit 0, high-population zone with tower failure flagged, low-population zone not flagged
    Evidence: .omo/evidence/task-25-resqnet-sage.txt
  ```
  Commit: Y | `feat(twin): telecom silence residual model with bias correction`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 6: DECISION OPTIMIZATION + ACTIVE SENSING — SOTA spec §8 (optimization), §9 (active sensing) -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 26. Rolling-horizon risk-aware CVaR optimizer + constraint modeling — OR-Tools CP-SAT (merged with T27 to resolve circular dependency)
  What to do / Must NOT do: `backend/app/optimizer/engine.py` + `backend/app/optimizer/constraints.py` — `EmergencyResponseOptimizer` class using OR-Tools CP-SAT. This todo MERGES the optimizer engine AND constraint modeling into one unit (they are co-developed — the optimizer cannot be built without constraints and vice versa). Objective: `A* = argmin_A [Σ p_ω L^ω(A) + λ CVaR_α(L^ω(A)) + C(A)]` where first term = expected harm, second = CVaR penalty, third = operational cost, λ controls risk aversion. CVaR via Rockafellar-Uryasev formulation: `theta` is a FREE DECISION VARIABLE (the VaR, not a parameter), `excess_s = max(0, cost_s - theta)` via `model.add_max_equality(a_s, [cost_s - theta, model.new_constant(0)])`, `CVaR = theta + 1/(1-α) * Σ p_s * a_s`. NOTE: all variables must be integer-scaled (CP-SAT is integer-only) — scale costs by 1000 and round. Constraints modeled simultaneously: responder availability (`add_cumulative`), skills (`add_allowed_assignments` + `x[r,t]==0` for incompatible), vehicle-road routing (`add_multiple_circuit` with conditional arcs skipping incompatible roads), shelter/hospital capacity (`add_reservoir_constraint`), shift duration (interval bounds), fairness (`Coverage_z >= C_min`), task precedence. FastAPI endpoint `POST /api/optimize` with BackgroundTasks async solve. Must NOT use online RL as sole controller — hard constraints always enforced.
  SOTA spec ref: §8.1 (optimize prevented harm), §8.2 (constraints), §8.3 (OR-Tools CP-SAT), §8.6 (do not use online RL)
  Parallelization: Wave 6 | Blocked by: T16 (world state), T23 (scenarios) | Blocks: T28 (route reliability), T29 (replan), T30 (EVI), T32 (UI)
  References: SOTA spec §8.1-8.3, §12.5. Research bg_2871bc92: `add_cumulative`, `add_multiple_circuit`, `add_reservoir_constraint`, `add_max_equality`, `add_allowed_assignments`, `add_hint()` warm-start, `solver.parameters.max_time_in_seconds`, `num_search_workers=8`. CVaR: Rockafellar-Uryasev 2000, PyPSA implementation (research bg_2871bc92).
  Acceptance criteria: `pytest tests/test_optimizer.py -q` — 3 zones, 4 responders, 3 scenarios → optimizer returns assignment portfolio with objective value, CVaR component, expected harm; skill gate (unqualified responder rejected); shelter over-capacity → infeasible; vehicle-road incompatibility (boat can't use flooded road → arc skipped); fairness minimum (vulnerable zone gets >= C_min); solve time < 30s; `POST /api/optimize` returns task_id, polling returns result within 30s.
  QA scenarios:
  ```
  Scenario: optimizer produces feasible assignment with constraints
    Tool: bash
    Steps: cd backend && pytest tests/test_optimizer.py::test_feasible_with_constraints -q | tee ../.omo/evidence/task-26-resqnet-sage.txt
    Expected: exit 0, all tasks assigned, skill/capacity/fairness constraints enforced, objective finite, CVaR >= 0
    Evidence: .omo/evidence/task-26-resqnet-sage.txt
  Scenario: infeasible problem (over-capacity) detected
    Tool: bash
    Steps: cd backend && pytest tests/test_optimizer.py::test_infeasible -q | tee ../.omo/evidence/task-26-resqnet-sage-error.txt
    Expected: exit 0, solver returns INFEASIBLE status
    Evidence: .omo/evidence/task-26-resqnet-sage-error.txt
  ```
  Commit: Y | `feat(optimizer): CVaR optimizer + constraint modeling (OR-Tools CP-SAT)`

- [ ] 27. (MERGED into T26 — constraint modeling is co-developed with optimizer engine)

- [ ] 28. Route reliability engine — P(route passable until arrival), travel-time variance, responder risk
  What to do / Must NOT do: `backend/app/optimizer/routing.py` — for route r, maintain `P(route remains passable until arrival)`. Route cost: `Cost(r) = E[T_r] + η Var(T_r) + γ P(route failure) + ρ Risk_responders`. Compute P(passable) from: road damage assessment (T20), flood probability (T18), scenario ensemble (T23). E[T_r] from historical travel times + current road status. Var(T_r) from scenario variance. Risk_responders from hazard exposure along route. Support k-shortest paths for alternate route generation. Must NOT use fastest expected route as sole criterion — must consider safety.
  SOTA spec ref: §8.5 (route reliability)
  Parallelization: Wave 6 | Blocked by: T20 (road passability), T23 (scenarios), T26 | Blocks: T29
  References: SOTA spec §8.5: "The fastest expected route is not necessarily the safest route." SOTA spec §8.5: `Cost(r) = E[T_r] + η Var(T_r) + γ P(route failure) + ρ Risk_responders`. Research bg_2871bc92: `add_multiple_circuit` for VRP in CP-SAT, conditional arcs for road compatibility.
  Acceptance criteria: `pytest tests/test_routing.py -q` — route with 0.9 P(passable) preferred over route with 0.3 P(passable) even if slower; k-shortest paths returns 3 alternatives; responder risk added to flooded route.
  QA scenarios:
  ```
  Scenario: safer route preferred over faster
    Tool: bash
    Steps: cd backend && pytest tests/test_routing.py::test_safety_over_speed -q | tee ../.omo/evidence/task-28-resqnet-sage.txt
    Expected: exit 0, high-P(passable) route selected despite longer E[T]
    Evidence: .omo/evidence/task-28-resqnet-sage.txt
  ```
  Commit: Y | `feat(optimizer): route reliability engine (passability + variance + risk)`

- [ ] 29. Stability threshold replanning — warm-start, deviation penalty, lock in-progress actions
  What to do / Must NOT do: `backend/app/optimizer/replan.py` — rolling-horizon replanning per SOTA spec §8.4. Every operational cycle: (1) receive new observations, (2) update world-state probabilities, (3) generate short-term scenarios, (4) lock actions already in progress, (5) re-optimize remaining tasks, (6) compare new plan with current plan, (7) change assignments only when expected benefit exceeds stability threshold. Implement: `model.add_hint(x[r,t], prev_value)` for warm-start; deviation vars `changed[r,t]` = 1 if assignment differs; `model.add(total_deviations <= stability_threshold)` as hard constraint OR soft penalty in objective. Prevents responder thrashing from small score fluctuations. Must NOT re-route teams for trivial improvements.
  SOTA spec ref: §8.4 (rolling-horizon replanning)
  Parallelization: Wave 6 | Blocked by: T26, T28 | Blocks: T32 (UI shows plan changes)
  References: SOTA spec §8.4: "The stability threshold prevents teams from being repeatedly rerouted because of small score fluctuations." Research bg_2871bc92: `add_hint()` warm-start, deviation penalty pattern, `solver.parameters.max_time_in_seconds` for real-time.
  Acceptance criteria: `pytest tests/test_replan.py -q` — previous plan with 5 assignments, new plan changes only 1 (below threshold of 3); new plan with 6 changes (above threshold) → solver penalizes and finds solution with fewer changes.
  QA scenarios:
  ```
  Scenario: stability threshold limits changes
    Tool: bash
    Steps: cd backend && pytest tests/test_replan.py::test_stability_threshold -q | tee ../.omo/evidence/task-29-resqnet-sage.txt
    Expected: exit 0, deviations <= threshold
    Evidence: .omo/evidence/task-29-resqnet-sage.txt
  ```
  Commit: Y | `feat(optimizer): rolling-horizon replanning with stability threshold`

- [ ] 30. Active sensing / EVI computation — expected value of information for sensing actions
  What to do / Must NOT do: `backend/app/sensing/evi.py` — compute Expected Value of Information for each candidate sensing action y: `EVI(y) = E_y[max_A U(A|y)] - max_A U(A) - Cost(y)`. If EVI > 0, gathering the observation is expected to improve the decision. Candidate sensing actions: ask nearest responder for one-tap verification, task a drone, request geotagged citizen photo, call a shelter, poll a river sensor, request new satellite acquisition, deploy temporary LoRa relay, query traffic-probe data, contact a hospital, ask utility for feeder status, move mobile camera/UAV. Operational display: "Recommended information request: Verify Bridge 4 within eight minutes. Confirmation would change the assignment of two rescue boats and potentially improve expected rescue coverage by 18 people."
  SOTA spec ref: §9 (active sensing and value of information), §9.2 (EVI formula), §9.3 (possible sensing actions), §9.4 (operational display)
  Parallelization: Wave 6 | Blocked by: T26 (optimizer) | Blocks: T32 (UI shows sensing recommendations)
  References: SOTA spec §9: "This can become ResQNet's strongest research contribution." SOTA spec §9.2: `EVI(y) = E_y[max_A U(A|y)] - max_A U(A) - Cost(y)`. SOTA spec §9.4: example operational display.
  Acceptance criteria: `pytest tests/test_evi.py -q` — bridge with 45% P(impassable), Plan A uses bridge (60 people), Plan B avoids (42 people); EVI(verify_bridge) > 0 because resolving uncertainty changes plan; EVI(check_road_with_clear_alternative) ≈ 0 because it doesn't change decision.
  QA scenarios:
  ```
  Scenario: EVI identifies high-value sensing
    Tool: bash
    Steps: cd backend && pytest tests/test_evi.py::test_bridge_verification_evi -q | tee ../.omo/evidence/task-30-resqnet-sage.txt
    Expected: exit 0, EVI(verify_bridge) > 0, EVI(low_impact_check) ≈ 0
    Evidence: .omo/evidence/task-30-resqnet-sage.txt
  ```
  Commit: Y | `feat(sensing): expected value of information (EVI) computation`

- [ ] 31. Sensing action catalog + operational display API
  What to do / Must NOT do: `backend/app/sensing/catalog.py` — catalog of sensing actions with: action_type, cost (time, resource, risk), expected information gain, potential impact on plan. `backend/app/api/routes/sensing.py` — `GET /api/incidents/{id}/sensing-recommendations` returns top-N EVI sensing actions with operational display text. `POST /api/incidents/{id}/sensing/{action_id}/dispatch` creates a task for the sensing action. Must NOT dispatch sensing actions autonomously — human approval required for resource-consuming actions.
  SOTA spec ref: §9.3 (possible sensing actions), §9.4 (operational display)
  Parallelization: Wave 6 | Blocked by: T30 | Blocks: T32 (UI)
  References: SOTA spec §9.3 (full list of sensing actions), §9.4 (operational display example).
  Acceptance criteria: `curl -s http://localhost:8000/api/incidents/test/sensing-recommendations` returns top-3 EVI actions with display text; dispatch creates a task row.
  QA scenarios:
  ```
  Scenario: sensing recommendations returned
    Tool: bash
    Steps: curl -s http://localhost:8000/api/incidents/test/sensing-recommendations | python -m json.tool | tee .omo/evidence/task-31-resqnet-sage.txt
    Expected: JSON with top-3 actions, each with EVI, cost, display text
    Evidence: .omo/evidence/task-31-resqnet-sage.txt
  ```
  Commit: Y | `feat(sensing): action catalog + operational display API`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 7: HUMAN-CENTERED DECISION SUPPORT UI — SOTA spec §10 -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 32. Four interface modes — Situation, Hypothesis, Planning, Simulation
  What to do / Must NOT do: `frontend/src/pages/` — four primary interface modes per SOTA spec §10.2: (1) **Situation mode** ("What is happening?"): current map, trends, unknowns, conflicting evidence, feed health. (2) **Hypothesis mode** ("Is Ward 11 becoming inaccessible?"): evidence supporting, evidence against, forecast, data gaps, suggested verification. (3) **Planning mode** ("How should six available teams be used?"): optimized action portfolios, trade-offs, alternatives, resource conflicts. (4) **Simulation mode** ("What happens if rainfall continues for three hours?"): scenario comparison, predicted closures, hospital accessibility, shelter overflow. Mode switcher in nav bar. Each mode renders relevant panels from API data. Must NOT show only "AI recommendation" — present evidence for and against.
  SOTA spec ref: §10.2 (evaluative AI, 4 interface modes)
  Parallelization: Wave 7 | Blocked by: T26 (optimizer), T30 (sensing), T31 (sensing API) | Blocks: T37
  References: SOTA spec §10.2: "decision support can preserve operator agency by presenting evidence for and against hypotheses rather than asking users to accept or reject an opaque recommendation." SOTA spec §10.2 (4 mode descriptions).
  Acceptance criteria: `cd frontend && npm run build` exits 0; Playwright test: switch between 4 modes, each renders different content; Situation mode shows feed health + conflicting evidence badges; Hypothesis mode shows supporting/against evidence lists.
  QA scenarios:
  ```
  Scenario: all 4 modes render
    Tool: bash
    Steps: cd frontend && npx playwright test tests/modes.spec.ts | tee ../.omo/evidence/task-32-resqnet-sage.txt
    Expected: all 4 mode tests pass
    Evidence: .omo/evidence/task-32-resqnet-sage.txt
  ```
  Commit: Y | `feat(ui): four interface modes (situation/hypothesis/planning/simulation)`

- [ ] 33. Action cards — evidence, alternatives, uncertainty, contingencies, equity impact
  What to do / Must NOT do: `frontend/src/components/ActionCard.tsx` — each action card contains all fields per SOTA spec §10.1: proposed action, operational objective, expected benefit range, time sensitivity, resources required, primary evidence (linked obs IDs), contradicting evidence, assumptions, confidence/calibration, alternative actions, failure contingency, equity impact, operator controls (approve/dismiss/modify). Example card: "Dispatch Boat B3 to Ward 11 via Canal Route C. Expected reach: 31-47 residents within 22 minutes. Evidence: 14 deduplicated distress reports, responder-confirmed 1.2m water depth, cell outage and elderly-resident registry. Uncertainty: exact group size is uncertain; distress locations span a 180m radius. Against: one six-minute-old traffic observation indicates limited vehicle movement. Alternative: Team R2 by high-clearance vehicle, with a 37% route-failure probability. Reassess after: bridge camera verification or ten minutes."
  SOTA spec ref: §10.1 (do not show only AI recommendation), §10.1 (action card fields), §10.1 (example card)
  Parallelization: Wave 7 | Blocked by: T26, T32 | Blocks: T35
  References: SOTA spec §10.1 (full action card specification + example). API from T26 (optimizer) + T30 (sensing).
  Acceptance criteria: Playwright test renders action card with all 13 fields; evidence links navigate to observation detail; uncertainty range displayed as [low, high]; approve/dismiss buttons call API.
  QA scenarios:
  ```
  Scenario: action card shows all fields
    Tool: bash
    Steps: cd frontend && npx playwright test tests/action-card.spec.ts | tee ../.omo/evidence/task-33-resqnet-sage.txt
    Expected: all 13 fields visible, evidence links clickable
    Evidence: .omo/evidence/task-33-resqnet-sage.txt
  ```
  Commit: Y | `feat(ui): action cards with evidence/alternatives/uncertainty/contingencies`

- [ ] 34. Map system — MapLibre GL JS + deck.gl + TiTiler for COGs + PMTiles offline basemaps
  What to do / Must NOT do: `frontend/src/components/MapView.tsx` — MapLibre GL JS operational map with: (1) PMTiles basemap (served from MinIO, offline-capable, Protomaps). (2) deck.gl layers for: flood probability raster (from COG via TiTiler), building footprints, road network with passability coloring, responder locations (live), shelter capacity, hospital status, cell tower status, hazard zones, observations. (3) Layer toggles per SOTA spec (flood, roads, buildings, shelters, hospitals, responders, sensors, alerts). (4) Confidence + data-age badges on all layers (stale data shown in different color). (5) Uncertainty visualization: flood probability as semi-transparent heatmap, hypothesis conflicts as warning icons. (6) Bbox-driven layer fetch. (7) Drawing tools for zones (terra-draw). Must NOT display stale data in normal colors — honest degradation.
  SOTA spec ref: §13.3 (geospatial services: MapLibre, deck.gl, TiTiler, PMTiles, H3), §11.4 (honest degradation: do not display old information in normal colors)
  Parallelization: Wave 7 | Blocked by: T1, T18 (flood COGs) | Blocks: T40
  References: SOTA spec §13.3: "MapLibre GL for the operational map; deck.gl for large visual layers; TiTiler for cloud-optimized GeoTIFFs; PMTiles for offline basemaps." `platform/web/src/App.tsx` (existing React pattern to follow).
  Acceptance criteria: `npm run build` exits 0; Playwright test loads map, toggles layers, flood probability renders as semi-transparent; stale data (>1h old) shown with different color.
  QA scenarios:
  ```
  Scenario: map renders with flood layer
    Tool: bash
    Steps: cd frontend && npx playwright test tests/map.spec.ts | tee ../.omo/evidence/task-34-resqnet-sage.txt
    Expected: map loads, flood layer visible, layer toggle works
    Evidence: .omo/evidence/task-34-resqnet-sage.txt
  ```
  Commit: Y | `feat(ui): MapLibre + deck.gl map with flood/road/shelter layers + offline basemaps`

- [ ] 35. Real-time WebSocket updates — Redpanda consumer → WS fanout + PostgreSQL LISTEN/NOTIFY
  What to do / Must NOT do: `backend/app/realtime/manager.py` — WebSocket connection manager per incident. (1) Redpanda consumer reads from `observations.normalized` topic in background. (2) On new observation → INSERT to PostgreSQL → `NOTIFY observation_created` → WS manager broadcasts `{type: 'new_observation', payload}` to connected clients for that incident. (3) On hypothesis update → broadcast `{type: 'hypothesis_changed'}`. (4) On optimizer result → broadcast `{type: 'plan_updated', payload}`. (5) Polling fallback every 15s for dropped WS connections. (6) Connection presence tracking. Must NOT require WebSocket for basic operation — polling fallback always available.
  SOTA spec ref: §10.2 (real-time updates), §13.1 (event-time processing)
  Parallelization: Wave 7 | Blocked by: T10 (streaming pipeline), T26 (optimizer results), T34 (map) | Blocks: T40
  References: SOTA spec §13.1: streaming pipeline. Research bg_835b8072: PostgreSQL LISTEN/NOTIFY for instant dashboard updates, hybrid approach (LISTEN/NOTIFY + Redpanda).
  Acceptance criteria: Playwright test connects WS, receives broadcast after observation POST; WS disconnect → polling fallback updates within 15s; 2 concurrent clients both receive broadcast.
  QA scenarios:
  ```
  Scenario: WebSocket broadcasts new observation
    Tool: bash
    Steps: cd frontend && npx playwright test tests/websocket.spec.ts | tee ../.omo/evidence/task-35-resqnet-sage.txt
    Expected: WS client receives new_observation event within 2s of POST
    Evidence: .omo/evidence/task-35-resqnet-sage.txt
  ```
  Commit: Y | `feat(realtime): WebSocket fanout + LISTEN/NOTIFY + polling fallback`

- [ ] 36. LLM-based evidence summarization — grounded in structured observations, provenance-linked
  What to do / Must NOT do: `backend/app/perception/llm.py` — LLM integration for: (1) parse free-text reports into structured observations, (2) summarize evidence across heterogeneous streams (retrieval-augmented, source-traceable), (3) translate languages, (4) answer natural-language queries about incident state, (5) generate briefing drafts, (6) explain optimizer outputs in natural language, (7) retrieve applicable operating procedures. **Offline LLM strategy (Metis GAP 15)**: primary = local Ollama model (llama3.1/8B or similar) for offline inference; secondary = cloud API (OpenAI-compatible) when internet available; fallback chain: cloud → local → disabled. Provider config `{base_url, api_key, model}` resolved org → incident → user. Every generated claim links to structured observation IDs (citation requirement). PII redaction before LLM call (regex + NER). Prompt injection defense (untrusted data fenced in delimited blocks). Output Pydantic-validated with 1 retry on parse fail. All outputs land as `review_status=draft`. Prompt versioning (`prompts` table). All calls logged (`ai_calls`: prompt_name+version, tokens, latency, cost, provider). Must NOT: invent missing values, convert uncertain locations to exact coordinates, decide casualty counts from ambiguous images, bypass optimization constraints, modify operational records without confirmation, issue field commands from free-form text, send PII to cloud API when offline.
  SOTA spec ref: §10.3 (LLM role), §10.3 (LLM must NOT list), §12.3 (LLM isolation)
  Parallelization: Wave 7 | Blocked by: T4 (auth), T21 (NLP pipeline) | Blocks: T48 (LLM isolation)
  References: SOTA spec §10.3: "A language model may: parse reports; summarize evidence; translate; answer queries; generate briefings; explain optimizer outputs; retrieve procedures." SOTA spec §10.3: "Every generated claim should link to structured evidence." SOTA spec §12.3: "PII and medical details should not be sent to unrestricted third-party model."
  Acceptance criteria: `pytest tests/test_llm.py -q` — LLM summarizes 5 observations into a briefing with citations; PII redacted before call; output validated against Pydantic schema; hallucination (uncited claim) rejected by validator.
  QA scenarios:
  ```
  Scenario: LLM summary has citations
    Tool: bash
    Steps: cd backend && pytest tests/test_llm.py::test_citations -q | tee ../.omo/evidence/task-36-resqnet-sage.txt
    Expected: exit 0, summary contains observation IDs as citations
    Evidence: .omo/evidence/task-36-resqnet-sage.txt
  ```
  Commit: Y | `feat(perception): LLM evidence summarization with provenance + PII redaction`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 8: RESILIENT COMMUNICATIONS & OFFLINE OPERATION — SOTA spec §11 -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 37. Edge-first topology + PWA offline — local vector map, cached state, append-only outbox
  What to do / Must NOT do: `frontend/` — Progressive Web App (PWA) with Workbox service worker. Each edge node retains: local vector map (PMTiles from MinIO), latest risk state (IndexedDB via Dexie), active assignments, critical facility data, cached imagery (COG), local user identities and permissions, append-only offline event queue (IndexedDB outbox). `backend/app/realtime/edge_sync.py` — sync endpoint: `POST /api/sync` receives outbox items, deduplicates by content hash, applies in order. Must NOT require internet for basic field operation — local cache + offline queue.
  SOTA spec ref: §11.1 (edge-first topology), §11.2 (store-and-forward synchronization)
  Parallelization: Wave 8 | Blocked by: T32 (UI), T34 (map), T35 (realtime) | Blocks: T40
  References: SOTA spec §11.1: "Deploy nodes at: emergency operations center; secondary command center; municipal data center; responder vehicles; temporary field posts." SOTA spec §11.1: "Each node should retain: local vector map; latest risk state; active assignments; critical facility data; cached imagery; local user identities and permissions; append-only offline event queue."
  Acceptance criteria: Playwright test: load app, go offline (browser offline mode), submit a report (stored in IndexedDB outbox), go online, verify sync pushes to backend; `docker compose stop backend` → frontend still shows cached map + data.
  QA scenarios:
  ```
  Scenario: offline report syncs when online
    Tool: bash
    Steps: cd frontend && npx playwright test tests/offline.spec.ts | tee ../.omo/evidence/task-37-resqnet-sage.txt
    Expected: report queued offline, synced when online, appears in DB
    Evidence: .omo/evidence/task-37-resqnet-sage.txt
  ```
  Commit: Y | `feat(offline): PWA edge-first topology + IndexedDB outbox + sync`

- [ ] 38. Store-and-forward synchronization — monotonic sequence, dedupe, conflict surfacing
  What to do / Must NOT do: `backend/app/realtime/sync.py` — store-and-forward sync protocol. When connectivity disappears: (1) continue local operation, (2) append observations to outbox, (3) assign monotonic local sequence numbers, (4) synchronize when any path becomes available, (5) deduplicate by event ID + content hash, (6) surface conflicts rather than silently overwriting (return `{status: 'conflict', local: ..., remote: ...}` for same-entity edits), (7) prioritize text, coordinates, and task state before imagery. Conflict-free replicated structure for selected collaborative fields (e.g., task assignments). Must NOT silently overwrite conflicting edits.
  SOTA spec ref: §11.2 (store-and-forward synchronization)
  Parallelization: Wave 8 | Blocked by: T12 (federation outbox), T37 (PWA) | Blocks: T40
  References: SOTA spec §11.2: 7-step sync protocol. SOTA spec §11.2: "surface conflicts rather than silently overwriting." SOTA spec §11.2: "prioritize text, coordinates and task state before imagery."
  Acceptance criteria: `pytest tests/test_sync.py -q` — 3 offline observations sync in priority order (text first, imagery last); duplicate content hash deduped; conflicting edit on same entity returns conflict response.
  QA scenarios:
  ```
  Scenario: sync prioritizes text over imagery
    Tool: bash
    Steps: cd backend && pytest tests/test_sync.py::test_priority_ordering -q | tee ../.omo/evidence/task-38-resqnet-sage.txt
    Expected: exit 0, text observations synced before image observations
    Evidence: .omo/evidence/task-38-resqnet-sage.txt
  ```
  Commit: Y | `feat(offline): store-and-forward sync with conflict surfacing`

- [ ] 39. Low-bandwidth fallback — SMS, cell broadcast, LoRa, text-first payloads
  What to do / Must NOT do: `backend/app/comms/fallback.py` — low-bandwidth fallback channels: (1) SMS gateway adapter (Twilio/MSG91, stubbed in dev), (2) cell broadcast (note: government-gated, integration note only), (3) LoRa adapter interface (for sensor data via LoRaWAN), (4) delayed-tolerant networking (DTN) for store-carry-forward, (5) text-first payload compression (strip map, list-only, <2KB payloads). Fallback mode flag: when set, API returns minimal JSON (text lists, no GeoJSON, no images). Must NOT depend on internet for critical alerts — SMS + cell broadcast fallback.
  SOTA spec ref: §11.3 (low-bandwidth fallback)
  Parallelization: Wave 8 | Blocked by: T37 | Blocks: T40
  References: SOTA spec §11.3: "Possible fallback channels: SMS; cell broadcast; LoRa; delayed-tolerant networking; Wi-Fi mesh; portable satellite gateways; UAV relays; radio operator gateways." SOTA spec §11.3: "These should be considered supplementary resilience layers, not replacements for established public-safety radio systems."
  Acceptance criteria: `pytest tests/test_fallback.py -q` — low-bandwidth mode returns <2KB payload; SMS adapter sends formatted alert text; LoRa interface accepts sensor reading.
  QA scenarios:
  ```
  Scenario: low-bandwidth payload <2KB
    Tool: bash
    Steps: curl -s -H 'X-Low-Bandwidth: true' http://localhost:8000/api/incidents/test/summary | wc -c | tee .omo/evidence/task-39-resqnet-sage.txt
    Expected: byte count < 2048
    Evidence: .omo/evidence/task-39-resqnet-sage.txt
  ```
  Commit: Y | `feat(comms): low-bandwidth fallback (SMS + LoRa + text-first payloads)`

- [ ] 40. Honest degradation display — data age, lost feeds, widening uncertainty, stale-data warnings
  What to do / Must NOT do: `frontend/src/components/DegradationBanner.tsx` + `backend/app/api/routes/health.py` — each layer exposes: data age (time since last update), lost feeds (list of unavailable sources), current coverage (% of AOI with fresh data), queue backlog (unsynced items), synchronization state, widening uncertainty (confidence intervals expanding for stale data), unavailable capabilities (features disabled due to missing data). Stale data (>τ) shown in amber/red, not normal colors. `GET /api/incidents/{id}/feed-health` returns per-feed status. Must NOT display old information as if current.
  SOTA spec ref: §11.4 (honest degradation)
  Parallelization: Wave 8 | Blocked by: T34 (map), T35 (realtime) | Blocks: T44 (resilience metrics)
  References: SOTA spec §11.4: "Each layer should expose: data age; lost feeds; current coverage; queue backlog; synchronization state; widening uncertainty; unavailable capabilities." SOTA spec §11.4: "Do not keep displaying old information in normal colors. A stale road status can be more dangerous than no road status."
  Acceptance criteria: Playwright test: simulate feed loss (stop Redpanda consumer), degradation banner appears, stale data shown in amber; `GET /api/incidents/test/feed-health` returns per-feed status with age + status.
  QA scenarios:
  ```
  Scenario: stale data shown in warning color
    Tool: bash
    Steps: cd frontend && npx playwright test tests/degradation.spec.ts | tee ../.omo/evidence/task-40-resqnet-sage.txt
    Expected: degradation banner visible, stale data in amber
    Evidence: .omo/evidence/task-40-resqnet-sage.txt
  ```
  Commit: Y | `feat(ui): honest degradation display + feed health API`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 9: EVALUATION TESTBED — SOTA spec §14 -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 41. Replayable cyclone-flood digital twin — terrain, buildings, roads, population, sensors
  What to do / Must NOT do: `backend/app/eval/testbed.py` — city-scale digital twin containing: terrain + drainage (DEM), building footprints, road graph, hospitals, shelters, population distribution (H3), vulnerability indicators, substations + towers, responder stations, simulated citizen devices. Run the same disaster repeatedly under different random seeds. Scenario: Indian coastal-city cyclone-flood (Mumbai/Chennai-style). Seed data generator: `scripts/seed_testbed.py` creates deterministic testbed scenario with configurable parameters (population, road density, hazard intensity). Each run produces reproducible observation stream. Must NOT be a one-shot demo — replayable with different parameters + seeds.
  SOTA spec ref: §14.1 (build a replayable cyclone-flood testbed)
  Parallelization: Wave 9 | Blocked by: all layers | Blocks: T42-T45
  References: SOTA spec §14.1: "Use a city-scale digital twin containing: terrain and drainage; building footprints; road graph; hospitals; shelters; population distribution; vulnerability indicators; substations and towers; responder stations; simulated citizen devices." SOTA spec §14.1: "Run the same disaster repeatedly under different random seeds."
  Acceptance criteria: `pytest tests/test_testbed.py -q` — generates testbed with 1000 buildings, 50 roads, 5 shelters, 2 hospitals, 10000 population; two runs with same seed produce identical output; two runs with different seeds produce different output.
  QA scenarios:
  ```
  Scenario: testbed is deterministic per seed
    Tool: bash
    Steps: cd backend && pytest tests/test_testbed.py::test_deterministic -q | tee ../.omo/evidence/task-41-resqnet-sage.txt
    Expected: exit 0, same seed = same output, different seed = different output
    Evidence: .omo/evidence/task-41-resqnet-sage.txt
  ```
  Commit: Y | `feat(eval): replayable cyclone-flood digital twin testbed`

- [ ] 42. Failure injection framework — feed loss, delays, false reports, cloud cover, model errors
  What to do / Must NOT do: `backend/app/eval/failures.py` — failure injection system. Configurable failure types: (1) 30%/50%/70% feed loss, (2) delayed official reports (add 15-60 min delay), (3) stale road data (don't update for 30 min), (4) false social-media posts (inject misinformation), (5) duplicate posts, (6) geolocation ambiguity (vague place names), (7) cloud-covered optical imagery (block S2), (8) SAR model errors (add noise to flood map), (9) tower failures (disable cell tower in testbed), (10) shelter capacity changes, (11) responder unavailability, (12) road failure during transit, (13) unexpected hospital closure, (14) multilingual + code-mixed reports, (15) adversarial misinformation, (16) database-node failure. `POST /api/eval/run` with failure config → runs testbed with injected failures → returns metrics. Must NOT only test happy path — failure injection is mandatory.
  SOTA spec ref: §14.2 (inject realistic failures)
  Parallelization: Wave 9 | Blocked by: T41 | Blocks: T43
  References: SOTA spec §14.2 (full failure list). SOTA spec §14.2: "Test: 30%, 50% and 70% feed loss; delayed official reports; stale road data; false social-media posts; ..."
  Acceptance criteria: `pytest tests/test_failures.py -q` — inject 50% feed loss, verify 50% of observations missing; inject false report, verify it's flagged by confidence vector; inject tower failure, verify cascade reaches silence residual.
  QA scenarios:
  ```
  Scenario: feed loss reduces observations
    Tool: bash
    Steps: cd backend && pytest tests/test_failures.py::test_feed_loss -q | tee ../.omo/evidence/task-42-resqnet-sage.txt
    Expected: exit 0, 50% feed loss → ~50% fewer observations
    Evidence: .omo/evidence/task-42-resqnet-sage.txt
  ```
  Commit: Y | `feat(eval): failure injection framework`

- [ ] 43. Four baselines — independent dashboards, unified visualization, current ResQNet, ResQNet-SAGE
  What to do / Must NOT do: `backend/app/eval/baselines.py` — implement 4 baselines for comparison per SOTA spec §14.3. **All baselines must be automated (no human operators required).** (1) **Baseline 1 — Independent dashboards**: simulated operator that randomly inspects one feed at a time with configurable attention model (reaction delay, miss probability). No fusion. (2) **Baseline 2 — Unified visualization**: all information displayed on one map, no fusion or prioritization — operator sees everything but no scoring. Simulated operator picks tasks by recency (FIFO). (3) **Baseline 3 — Current ResQNet**: confidence-weighted reports, scalar zone score (`w1*hazard + w2*exposure + ...`), threshold-based recommendations (simple rules: if flood_depth > X and distress > Y → dispatch boat). This is the simple approach the SOTA doc critiques. (4) **Baseline 4 — ResQNet-SAGE**: full system (probabilistic world model, scenario forecasting, robust optimization, active sensing, human-evaluable alternatives). Each baseline runs the same testbed scenario with the same simulated disaster. Output: per-baseline metrics for comparison. Must NOT require human operators for any baseline.
  SOTA spec ref: §14.3 (baselines)
  Parallelization: Wave 9 | Blocked by: T41, T42 | Blocks: T44
  References: SOTA spec §14.3: "Compare four systems." Baselines 1-2 are operational modes — implement as simulated operators with configurable behavior (attention model, decision strategy) so they're automatable.
  Acceptance criteria: `pytest tests/test_baselines.py -q` — all 4 baselines run on same testbed seed, produce different metrics (ResQNet-SAGE should outperform others on prevented harm).
  QA scenarios:
  ```
  Scenario: baselines produce different metrics
    Tool: bash
    Steps: cd backend && pytest tests/test_baselines.py::test_comparison -q | tee ../.omo/evidence/task-43-resqnet-sage.txt
    Expected: exit 0, 4 baselines with different prevented_harm values
    Evidence: .omo/evidence/task-43-resqnet-sage.txt
  ```
  Commit: Y | `feat(eval): 4-baseline comparison framework`

- [ ] 44. Metrics collection — perception, uncertainty, operational, resilience, human-factors, equity
  What to do / Must NOT do: `backend/app/eval/metrics.py` — collect all 6 metric categories per SOTA spec §14.4-14.9. **All metrics must be automatable (no human subjects required).** (1) **Perception** (§14.4): precision/recall/F1, mIoU flood extent, building-damage macro-F1, road-passability accuracy, distress-report recall, duplicate-removal precision, median geolocation error, % geolocated within 100m/500m/ward. (2) **Uncertainty** (§14.5): Brier score, ECE, conformal coverage, interval width, NLL, false-confidence rate, disagreement detection, uncertainty under domain shift. (3) **Operational** (§14.6): time to first correct high-priority ID, expected casualties avoided, urgent demand served, people reached before access loss, median/tail response time, route completion rate, responder exposure, shelter overflow, hospital overload, resource utilization, plan instability, optimization runtime, decision regret vs oracle. (4) **Resilience** (§14.7): p50/p95 sensor-to-map latency, p50/p95 report-to-recommendation latency, RTO, data-loss window, % capability under connectivity loss, sync convergence time, stale-data detection rate, performance loss at each feed-dropout level. (5) **Human-factors** (§14.8): **automated proxy metrics** — simulated operator decision time (time from recommendation availability to simulated approval), correct/harmful override rate (simulated override model), evidence-chain comprehension score (automated: does the simulated operator's decision match the optimal decision given the evidence?), **NASA-TLX proxy** (workload estimated from information density × ambiguity × conflict count — NOT a real NASA-TLX which requires human subjects, but an automated proxy that correlates with cognitive load). (6) **Equity** (§14.9): response delay by ward + vulnerability, unmet urgent demand by connectivity level, false-negative rate in low-reporting communities, resource-allocation disparity, coverage before/after fairness constraints. Store all metrics in `eval_results` table. `GET /api/eval/results/{run_id}` returns all metrics.
  SOTA spec ref: §14.4 (perception metrics), §14.5 (uncertainty metrics), §14.6 (operational metrics), §14.7 (resilience metrics), §14.8 (human-factors metrics), §14.9 (equity metrics)
  Parallelization: Wave 9 | Blocked by: T41, T43 | Blocks: T45
  References: SOTA spec §14.4-14.9 (full metric lists for each category).
  Acceptance criteria: `pytest tests/test_metrics.py -q` — runs testbed, collects all 6 metric categories, each has >0 metrics; Brier score in [0,1]; prevented_harm > 0 for SAGE baseline.
  QA scenarios:
  ```
  Scenario: all 6 metric categories collected
    Tool: bash
    Steps: cd backend && pytest tests/test_metrics.py::test_all_categories -q | tee ../.omo/evidence/task-44-resqnet-sage.txt
    Expected: exit 0, 6 categories with non-empty metrics
    Evidence: .omo/evidence/task-44-resqnet-sage.txt
  ```
  Commit: Y | `feat(eval): 6-category metrics collection (perception/uncertainty/ops/resilience/human/equity)`

- [ ] 45. Ablation study runner — remove one component at a time, measure impact
  What to do / Must NOT do: `backend/app/eval/ablation.py` — ablation study runner per SOTA spec §14.10. Remove one component at a time and re-run the testbed: (1) no calibrated uncertainty, (2) no provenance, (3) no active sensing, (4) no robust optimization (use greedy), (5) no infrastructure dependencies (no cascade), (6) no telecom-silence residual, (7) no fairness constraints, (8) no edge operation (online-only), (9) no human counterfactual display. `POST /api/eval/ablation` runs all ablations + full system, returns comparison table showing which components actually improve outcomes. Must NOT skip ablation — it identifies which components provide real value.
  SOTA spec ref: §14.10 (required ablation studies)
  Parallelization: Wave 9 | Blocked by: T44 | Blocks: final verification
  References: SOTA spec §14.10: "Remove one component at a time: no calibrated uncertainty; no provenance; no active sensing; no robust optimization; no infrastructure dependencies; no telecom-silence residual; no fairness constraints; no edge operation; no human counterfactual display."
  Acceptance criteria: `pytest tests/test_ablation.py -q` — runs 9 ablations + 1 full system, produces comparison table; at least 3 ablations show statistically significant degradation (prevented_harm decreases).
  QA scenarios:
  ```
  Scenario: ablation shows component impact
    Tool: bash
    Steps: cd backend && pytest tests/test_ablation.py::test_component_impact -q | tee ../.omo/evidence/task-45-resqnet-sage.txt
    Expected: exit 0, >=3 ablations show prevented_harm decrease vs full system
    Evidence: .omo/evidence/task-45-resqnet-sage.txt
  ```
  Commit: Y | `feat(eval): ablation study runner`

<!-- ════════════════════════════════════════════════════════════════════════════ -->
<!-- WAVE 10: PRIVACY, SECURITY & INTEGRATION — SOTA spec §12 -->
<!-- ════════════════════════════════════════════════════════════════════════════ -->

- [ ] 46. Data minimization + progressive precision — ward → shelter → dispatcher → rescue team → auditor
  What to do / Must NOT do: `backend/app/lib/privacy.py` — progressive precision access control. Store exact personal locations only when operationally necessary. Precision levels: Public dashboard (ward-level aggregation), Shelter operator (shelter + assigned-person info), Dispatcher (task-relevant approximate or exact location), Assigned rescue team (exact rescue location), Auditor (controlled access to decision history). Implement as serializer layer: same entity serialized differently based on viewer's role + task assignment. Must NOT store exact personal locations in public-facing tables.
  SOTA spec ref: §12.1 (data minimization), §12.1 (progressive precision levels)
  Parallelization: Wave 10 (cross-cutting) | Blocked by: T3 (serializer), T4 (auth) | Blocks: final verification
  References: SOTA spec §12.1 (5 precision levels).
  Acceptance criteria: `pytest tests/test_privacy.py -q` — same observation serialized 3 ways (public=ward, dispatcher=approx, rescue=exact); public serializer strips PII.
  QA scenarios:
  ```
  Scenario: public view has no exact coordinates
    Tool: bash
    Steps: cd backend && pytest tests/test_privacy.py::test_progressive_precision -q | tee ../.omo/evidence/task-46-resqnet-sage.txt
    Expected: exit 0, public has ward-level, rescue has exact
    Evidence: .omo/evidence/task-46-resqnet-sage.txt
  ```
  Commit: Y | `feat(privacy): progressive precision + data minimization`

- [ ] 47. Attribute-based access control — role + incident + jurisdiction + sensitivity + task + emergency override
  What to do / Must NOT do: `backend/app/auth/abac.py` — attribute-based access control beyond role-based. Policy considers: user role, incident assignment, jurisdiction, data sensitivity, current operational task, emergency override status. `can(actor, action, subject, context)` function. Emergency override: admin can grant temporary elevated access during crisis (logged to audit). Must NOT rely on role-based access alone when multiple agencies participate.
  SOTA spec ref: §12.2 (access control)
  Parallelization: Wave 10 | Blocked by: T4 (auth) | Blocks: final verification
  References: SOTA spec §12.2: "Use attribute-based policies considering: user role; incident assignment; jurisdiction; data sensitivity; current operational task; emergency override status." SOTA spec §12.2: "Role-based access alone may be too coarse when multiple agencies participate."
  Acceptance criteria: `pytest tests/test_abac.py -q` — user without jurisdiction can't access data; emergency override grants temporary access + audit entry; override expires after configured time.
  QA scenarios:
  ```
  Scenario: emergency override grants + expires
    Tool: bash
    Steps: cd backend && pytest tests/test_abac.py::test_emergency_override -q | tee ../.omo/evidence/task-47-resqnet-sage.txt
    Expected: exit 0, override grants access, expires after TTL, audit entry created
    Evidence: .omo/evidence/task-47-resqnet-sage.txt
  ```
  Commit: Y | `feat(auth): attribute-based access control + emergency override`

- [ ] 48. LLM isolation — PII redaction, local inference, tokenization, prompt injection defense
  What to do / Must NOT do: `backend/app/perception/llm_safety.py` — LLM safety layer. (1) PII redaction: regex + NER model to strip PII/medical details before LLM call. (2) Local inference option: for sensitive reports, use local model (Ollama/llama.cpp) instead of third-party API. (3) Tokenization/pseudonymization: replace names with tokens before LLM, restore after. (4) Prompt injection defense: untrusted data fenced in delimited blocks with instruction firewall preamble. (5) Output validation: Pydantic schema validation with 1 retry. (6) Non-retention: LLM call logs don't store prompt content (only prompt version + metadata). (7) Model access audit records. Must NOT send PII or medical details to unrestricted third-party models.
  SOTA spec ref: §12.3 (language-model isolation)
  Parallelization: Wave 10 | Blocked by: T36 (LLM integration) | Blocks: final verification
  References: SOTA spec §12.3: "Use: local or controlled inference for sensitive reports; tokenization or pseudonymization; structured redaction; narrowly scoped prompts; output validation; non-retention policies; model-access audit records."
  Acceptance criteria: `pytest tests/test_llm_safety.py -q` — PII (phone, name, medical) redacted before LLM call; prompt injection attempt blocked by firewall; output schema validation rejects malformed response.
  QA scenarios:
  ```
  Scenario: PII redacted before LLM call
    Tool: bash
    Steps: cd backend && pytest tests/test_llm_safety.py::test_pii_redaction -q | tee ../.omo/evidence/task-48-resqnet-sage.txt
    Expected: exit 0, PII patterns absent in LLM input
    Evidence: .omo/evidence/task-48-resqnet-sage.txt
  ```
  Commit: Y | `feat(safety): LLM isolation (PII redaction + injection defense + audit)`

- [ ] 49. Provenance & auditability — input obs IDs, model versions, optimizer params, operator decisions
  What to do / Must NOT do: `backend/app/audit/provenance.py` — for every recommendation, preserve: input observation IDs, data versions, model versions, optimization parameters, scenario set, constraints, generated alternatives, operator decision, override reason, execution outcome. All stored in `decision_provenance` table linked to recommendation ID. Hash-chained audit log (T3) provides tamper evidence. `GET /api/decisions/{id}/provenance` returns full chain. Must NOT use blockchain — hash-chained append-only log is sufficient unless multiple distrustful organizations require shared consensus.
  SOTA spec ref: §12.4 (provenance and auditability)
  Parallelization: Wave 10 | Blocked by: T3 (audit), T26 (optimizer) | Blocks: final verification
  References: SOTA spec §12.4: "For every recommendation, preserve: Input observation IDs; Data versions; Model versions; Optimization parameters; Scenario set; Constraints; Generated alternatives; Operator decision; Override reason; Execution outcome." SOTA spec §12.4: "A hash-chained append-only log is sufficient for tamper evidence. A blockchain is not necessary."
  Acceptance criteria: `pytest tests/test_provenance.py -q` — optimizer produces recommendation, provenance chain has all 10 fields; tamper detection from T3 still works on provenance entries.
  QA scenarios:
  ```
  Scenario: provenance chain complete
    Tool: bash
    Steps: cd backend && pytest tests/test_provenance.py::test_full_chain -q | tee ../.omo/evidence/task-49-resqnet-sage.txt
    Expected: exit 0, all 10 provenance fields present
    Evidence: .omo/evidence/task-49-resqnet-sage.txt
  ```
  Commit: Y | `feat(audit): provenance chain + decision auditability`

- [ ] 50. Fairness constraints — coverage minimums, response delay disparity, low-connectivity protection
  What to do / Must NOT do: `backend/app/optimizer/fairness.py` — fairness constraints in optimizer. (1) Coverage constraint: `Coverage_z >= C_min` for designated vulnerable zones. (2) Response delay disparity: `max_z ResponseDelay_z - min_z ResponseDelay_z <= δ` subject to emergency severity. (3) Low-connectivity area protection: areas with historically low smartphone ownership / weak network / limited social-media use get minimum service guarantee. (4) Report: when equity constraints alter the mathematically highest-throughput plan, surface this to the operator ("Equity constraint applied: Ward 7 (low-connectivity) received priority allocation, reducing total throughput by 8%"). Must NOT maximize total benefit in a way that systematically ignores vulnerable communities.
  SOTA spec ref: §12.5 (fairness constraints)
  Parallelization: Wave 10 | Blocked by: T26 (optimizer + constraints, formerly T27) | Blocks: final verification
  References: SOTA spec §12.5: "The optimizer should not maximize total expected benefit in a way that systematically ignores: low-connectivity areas; informal settlements; people with disabilities; elderly residents; people without social-media access; linguistic minorities; geographically isolated communities." SOTA spec §12.5: "The system should report when equity constraints alter the mathematically highest-throughput plan."
  Acceptance criteria: `pytest tests/test_fairness.py -q` — optimizer without fairness: Ward 7 (low-connectivity) gets 0 coverage; with fairness: Ward 7 gets >= C_min; disparity <= δ; equity report flag shows throughput tradeoff.
  QA scenarios:
  ```
  Scenario: fairness constraint protects vulnerable zone
    Tool: bash
    Steps: cd backend && pytest tests/test_fairness.py::test_coverage_minimum -q | tee ../.omo/evidence/task-50-resqnet-sage.txt
    Expected: exit 0, Ward 7 coverage >= C_min with fairness, 0 without
    Evidence: .omo/evidence/task-50-resqnet-sage.txt
  ```
  Commit: Y | `feat(fairness): optimizer fairness constraints + equity impact reporting`

- [ ] 52. Seed data package — fixtures for all layers (Metis GAP 8)
  What to do / Must NOT do: Create `backend/app/seed/` directory with: (1) CAP 1.2 XML fixture files (sample alerts from SACHET/IPAWS format), (2) SensorThings JSON fixtures (rain gauge, river gauge, weather station data), (3) STAC item fixtures (sample Sentinel-1 metadata), (4) GeoJSON entity fixtures (roads, shelters, hospitals, buildings, substations, cell towers for a fictional coastal-city "Rivertown"), (5) Sample SAR scene crops (small 512×512 patches, not full scenes, stored in MinIO), (6) PMTiles basemap for the demo region (pre-generated from OSM extract via tippecanoe, stored in `frontend/public/basemaps/`), (7) Population grid (H3 hexes with population counts), (8) `seed_demo.py` script that populates DB with a cyclone-flood scenario: 1 incident, 5 zones, 20 roads, 3 shelters, 2 hospitals, 10 buildings, 5 responders, 3 vehicles, 50 observations (mix of sensor/citizen/official), 5 hypotheses (2 contradictory), 3 scenarios (best/expected/worst). (9) `backend/tests/fixtures/` with small sample tensors for ML model tests. Must NOT require internet to run seed — all fixtures are local files.
  SOTA spec ref: §14.1 (testbed needs terrain, buildings, roads, hospitals, shelters, population, sensors), §14.10 (ablation needs deterministic fixtures)
  Parallelization: Wave 1 | Blocked by: T1, T2 | Blocks: all acceptance criteria
  References: Metis GAP 8. `DESIGN.md:213-220` (existing Rivertown seed concept to adapt). SOTA spec §14.1 (digital twin contents).
  Acceptance criteria: `cd backend && python -m app.seed.seed_demo` populates DB with all entities; `docker compose exec db psql -U disaster -c "SELECT count(*) FROM observations;"` returns >= 50; seed is idempotent (run twice = same count).
  QA scenarios:
  ```
  Scenario: seed creates demo scenario
    Tool: bash
    Steps: cd backend && python -m app.seed.seed_demo | tee ../.omo/evidence/task-52-resqnet-sage.txt
    Expected: JSON summary with counts: observations>=50, roads>=20, shelters>=3, hypotheses>=5
    Evidence: .omo/evidence/task-52-resqnet-sage.txt
  ```
  Commit: Y | `feat(seed): fixture package for all layers + cyclone-flood demo scenario`

- [x] 53. Offline pre-deployment preparation script (Metis GAP 11)
  What to do / Must NOT do: Create `scripts/offline_prep.sh` that: (1) downloads and caches all ML model **base pretrained weights** (DOFA, TorchGeo ResNet50 S1, Clay, TerraMind) to `backend/models/cache/` — these are base foundation model weights, NOT fine-tuned models (fine-tuning happens in Wave 4 T18-T21, ONNX conversion of fine-tuned models happens in T22 after fine-tuning), (2) generates PMTiles basemap for demo region from pre-downloaded OSM extract via tippecanoe (tippecanoe must be installed on the build machine, not in Docker), stores in `frontend/public/basemaps/`, (3) builds the custom PostgreSQL Docker image (from T51 spike result), (4) pre-pulls all Docker images (`docker compose pull`), (5) vendors pip packages (`pip download -r requirements.txt -d backend/vendor/`), (6) vendors npm packages (`cd frontend && npm install --package-lock-only && npm ci --prefix ./node_modules-offline` or `npm pack` tarballs), (7) downloads sample Sentinel-1 scenes for testing, stores in MinIO, (8) pulls Ollama model (`ollama pull llama3.1:8b`), (9) downloads Whisper model for ASR, (10) downloads NER model for PII detection. Document minimum hardware: ~16 cores, 32 GB RAM, 256 GB SSD for full stack; ~8 cores, 16 GB RAM, 128 GB SSD for reduced stack (no ML, no Grafana). Per-service resource limits in `docker-compose.yml` (`deploy.resources`). Redpanda minimum 4GB RAM (not 1GB). Must NOT require internet after running this script.
  SOTA spec ref: §11 (resilient communications and offline operation), §13.4 (ONNX Runtime at edge)
  Parallelization: Wave 1 | Blocked by: T1, T51 | Blocks: T22 (model serving), T37 (offline PWA)
  References: Metis GAP 11. User constraint: "everything must work on local hardware with low internet connectivity." Research bg_bac2773d: model weights 45MB-2.6GB per model, ONNX conversion via `torch.onnx.export()`, PMTiles via tippecanoe.
  Acceptance criteria: `scripts/offline_prep.sh` exits 0; after running, `docker compose down && docker compose up -d --wait` starts all services with network disabled via `docker network disconnect`; `curl -s http://localhost:8000/healthz` returns ok. NOTE: ONNX conversion of fine-tuned models happens in Wave 4 (after T18-T21), NOT in this script — T53 only downloads base pretrained weights (DOFA, ResNet50 S1, Clay, TerraMind) and pre-pulls Docker images. Fine-tuned model ONNX conversion is handled in T22 (model serving) after fine-tuning completes.
  QA scenarios:
  ```
  Scenario: stack boots offline after prep
    Tool: bash
    Steps: bash scripts/offline_prep.sh && docker compose down && docker network create --internal offline-net 2>/dev/null; docker compose up -d --wait && curl -s http://localhost:8000/healthz | tee .omo/evidence/task-53-resqnet-sage.txt
    Expected: healthz returns ok:true with no internet (internal network)
    Evidence: .omo/evidence/task-53-resqnet-sage.txt
  ```
  Commit: Y | `feat(offline): pre-deployment preparation script + resource limits`

## Final verification wave
> Runs in parallel; ALL must APPROVE; surface results and wait for user's explicit okay before declaring complete.
- F1: Plan compliance audit — every SOTA spec section (3-14) mapped to a todo; zero orphan sections
- F2: Code quality review — all files under 250 pure LOC; type annotations; no `Any` in logic code; hash-chain audit verifies
- F3: Real manual QA — full Docker Compose stack boots; seeded cyclone-flood scenario runs end-to-end; optimizer produces action portfolios; evaluation testbed runs ablation
- F4: Scope fidelity — no FEATURES.md dependencies; no Cloudflare code; no cloud runtime dependencies; offline mode verified

## Commit strategy
- Conventional commits: `feat(scope): description` (e.g., `feat(fusion): add confidence vector computation`)
- One commit per todo (implementation + tests together)
- Phase gate commits: `feat(phase-WN): ... gate`
- Evidence committed alongside code in `.omo/evidence/`

## Success criteria
- Docker Compose `up` brings up the full stack (PostGIS, Redpanda, Benthos, MinIO, FastAPI, React, Redis, Prometheus, Grafana) on local hardware
- Seeded cyclone-flood scenario produces: probabilistic flood map, confidence vectors, knowledge graph with hypotheses, scenario ensemble, optimized action portfolio, active sensing recommendation, 4-mode UI with action cards
- Evaluation testbed runs 4 baselines and ablation studies with all 6 metric categories
- System operates in degraded/offline mode with honest degradation (stale data flagged, uncertainty widens)
- All tests pass: `cd backend && pytest -q && cd ../frontend && npm run build && npx playwright test`
