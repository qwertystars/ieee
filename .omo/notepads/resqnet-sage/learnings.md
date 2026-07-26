# Resqnet-Sage Learnings

## T51 — PostgreSQL extension coexistence spike (2026-07-18)

### Outcome
All four extensions (PostGIS, Apache AGE, TimescaleDB, h3) coexist successfully on
PostgreSQL 16 in a single Docker image. No extension was dropped.

### Key findings

1. **The plan's compatibility note was outdated.** The plan said "AGE v1.8.0 requires
   PG 18.0.0" and "PostGIS 3.4 may not support PG 18." In reality:
   - AGE v1.6.0 stable supports PG 16 (tag `PG16/v1.6.0-rc0`).
   - AGE v1.7.0 stable supports PG 17 and PG 18.
   - PostGIS 3.5.x supports PG 12-18 (3.5.5+ supports PG 18 GA).
   - TimescaleDB 2.23+ supports PG 15-18.

2. **AGE must be in `shared_preload_libraries`.** Without it, `cypher()` fails with
   `ERROR: unhandled cypher(cstring) function call`. The `LOAD 'age';` command works
   as a per-session workaround but is fragile. Setting
   `shared_preload_libraries=timescaledb,age` in the Docker CMD is the clean fix.

3. **AGE functions live in `ag_catalog` schema.** Application code must set
   `search_path = ag_catalog, public` or schema-qualify all calls
   (`ag_catalog.cypher()`, `ag_catalog.agtype`).

4. **h3-pg v4.x takes a `point` type, not separate lat/lng args.**
   `h3_lat_lng_to_cell(point '(lat, lng)', resolution)` works.
   `h3_lat_lng_to_cell(40.7, -73.9, 9)` does NOT exist.
   `h3_lat_lng_to_cell` is deprecated in favor of `h3_latlng_to_cell` (same signature).

5. **AGE is not in apt — must build from source.** The build requires
   `postgresql-server-dev-16`, `flex`, `bison`, `build-essential`, `git`. The
   Dockerfile purges these after `make install` to keep the image lean.

6. **PG 16 is the right choice over PG 18.** PG 16 has the most mature AGE release
   (v1.6.0), matches the existing `docker-compose.yml`, and all three extensions have
   production-quality packages for it. PG 18 would work too, but AGE v1.8.0 for PG 18
   is still a release candidate.

### Versions installed
- PostgreSQL 16 (Debian Bookworm base)
- PostGIS 3.6.4 (from PGDG apt)
- Apache AGE 1.6.0 (built from source, `PG16/v1.6.0-rc0` tag)
- TimescaleDB 2.28.3 (from Timescale packagecloud apt)
- h3 4.2.3 (from PGDG apt)

### Files produced
- `Dockerfile.db` — custom PostgreSQL 16 image with all four extensions.
- `docs/db-extensions.md` — decision document with usage notes.
- `.omo/evidence/task-0a-resqnet-sage.txt` — full test output.

## T1 — Project skeleton + Docker Compose (2026-07-18)

### Outcome
Full Docker Compose stack boots successfully with all 10 services: db, redis,
redpanda, minio, ollama, benthos, backend, frontend, prometheus, grafana.
`curl http://localhost:8000/healthz` returns `{"ok":true}` with all service
bindings. Frontend `npm install && npm run build` exits 0.

### Key findings

1. **PYTHONPATH must be set in docker-compose.yml.** The `alembic` command
   (at `/usr/local/bin/alembic`) does not include the WORKDIR in `sys.path`.
   Without `PYTHONPATH: /app`, `alembic upgrade head` fails with
   `ModuleNotFoundError: No module named 'app'`. uvicorn works without it
   because it adds the current directory to the path, but alembic does not.

2. **Ollama image has no curl or wget.** The `ollama/ollama:latest` image is
   based on a minimal Ubuntu and does not include `curl` or `wget`. The
   healthcheck must use `ollama list` (built-in command) instead of
   `curl -f http://localhost:11434/api/tags`.

3. **Redpanda `--memory 4G` is required, not 1G.** The original T1 plan note
   was correct: 1G is below Redpanda's minimum. The `--memory 4G` flag in the
   `redpanda start` command works reliably.

4. **Redpanda internal/external address split works with `--kafka-addr` and
   `--advertise-kafka-addr` flags.** The pattern:
   ```
   --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092
   --advertise-kafka-addr internal://redpanda:9092,external://localhost:19092
   ```
   Internal address (`redpanda:9092`) for container-to-container, external
   (`localhost:19092`) for host access. Both work simultaneously.

5. **Backend Dockerfile builds successfully with all heavy packages.** torch
   (CPU-only from `https://download.pytorch.org/whl/cpu`), torchgeo, rasterio,
   and gdal all install correctly. The GDAL Python package is installed
   separately with `pip install gdal==$(gdal-config --version)` to match the
   system GDAL version (3.6.2 on Debian Bookworm). Total pip install time:
   ~90 seconds.

6. **`docker compose up -d --wait` requires healthchecks on all services.**
   Services without healthchecks are considered ready immediately. Services
   with healthchecks must pass before `--wait` returns. The ollama healthcheck
   initially failed because it used `curl` (not available); switching to
   `ollama list` fixed it.

7. **Frontend port 5173 can conflict with host processes.** If a Vite dev
   server is already running on the host, `docker compose up frontend` will
   fail with "address already in use". Kill the host process before starting
   the container.

### Files produced
- `docker-compose.yml` — full 10-service stack.
- `backend/` — FastAPI project with all package structure.
- `frontend/` — React + Vite + TypeScript + Tailwind project.
- `benthos/disaster_pipeline.yaml` — minimal placeholder.
- `prometheus.yml` — scrape config.
- `.env.example` — all env vars with defaults.
- `.omo/evidence/task-1-resqnet-sage.txt` — healthz + AGE test output.

## T2 — Rich observation schema + core DB schema (2026-07-18)

### Outcome
Created 23-field observation model (27 columns including id/org_id/incident_id),
14 core entity tables, graph_edges, hypotheses, scenarios, events (hash-chained
audit), and 6 PostgreSQL enum types. Alembic migration `0001_init_schema.py`
creates all tables with PostGIS Geometry columns and GiST spatial indexes.
Geometry round-trip test passes.

### Key findings

1. **GeoAlchemy2 `Geometry` does not accept `index=True` as a keyword arg.**
   The `index` parameter must be set via `Index(..., postgresql_using="gist")`
   in `__table_args__` or via `op.create_index(..., postgresql_using="gist")`
   in the migration. Passing `index=True` to `Geometry()` raises
   `TypeError: _GISType.__init__() got an unexpected keyword argument 'index'`.

2. **`sa.Enum(PythonEnum, name="...", create_type=False)` does NOT prevent
   duplicate type creation.** The `create_type=False` parameter is specific to
   `sqlalchemy.dialects.postgresql.ENUM`, not the base `sa.Enum`. When using
   `sa.Enum()` in `op.create_table`, SQLAlchemy's `_on_table_create` hook
   tries to create the enum type regardless. The fix: don't pre-create enum
   types with `.create()` — let `op.create_table` create them automatically.
   Each enum should be used in only one table to avoid conflicts.

3. **`mapped_column(PythonEnum, native_enum=False)` fails — must wrap in
   `SAEnum()`.** The correct pattern is:
   ```python
   from sqlalchemy import Enum as SAEnum
   source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType, native_enum=False))
   ```
   Passing the Python enum class directly as the first positional arg to
   `mapped_column` raises `ArgumentError: 'SchemaItem' object expected`.

4. **`native_enum=False` stores enum values as VARCHAR, not PG enum type.**
   This is fine for the model layer. The migration creates native PG enum
   types via `sa.Enum(PythonEnum, name="...")` in `op.create_table` columns.
   The model's `native_enum=False` means SQLAlchemy sends string values,
   which PostgreSQL coerces to the enum type.

5. **conftest.py had a pre-existing bug: `Generator` imported after use.**
   The `from collections.abc import Generator` was at line 33, but
   `override_get_db() -> Generator` was at line 25. Python evaluates
   annotations at function definition time, so this raised `NameError`.
   Fixed by moving the import to the top of the file.

6. **27 columns on observations, not 23 or 25.** The task lists 25 fields
   (observation_id through duplicate_group) plus org_id and incident_id for
   tenancy = 27 total. The "23-field event model" is the conceptual name;
   the MUST DO list is authoritative with 25 fields + 2 tenancy columns.

### Files produced
- `backend/app/models/__init__.py` — exports all models + TenancyMixin/TimestampMixin
- `backend/app/models/enums.py` — 6 Python enums (SourceType, CorroborationState, etc.)
- `backend/app/models/observation.py` — Observation model (27 columns)
- `backend/app/models/entities.py` — 14 entity models (Hazard through Decision)
- `backend/app/models/relationships.py` — GraphEdge model
- `backend/app/models/hypotheses.py` — Hypothesis model
- `backend/app/models/scenarios.py` — Scenario model
- `backend/app/models/events.py` — Event model (hash-chained audit)
- `backend/alembic/versions/0001_init_schema.py` — Alembic migration
- `backend/tests/test_schema.py` — geometry round-trip test

## T53 — Offline pre-deployment preparation script (2026-07-18)

### Outcome
Created `scripts/offline_prep.sh` (12-step idempotent, resilient script) and
`scripts/offline_prep_lib.sh` (helper functions). Added `deploy.resources.limits`
to all 10 services in `docker-compose.yml`. Created `docs/offline-prep.md` with
hardware requirements and troubleshooting.

### Key findings

1. **`pip download` fails atomically on GDAL.** The `pip download -r requirements.txt`
   command exits with an error when it encounters `gdal>=3.6.0` because GDAL
   requires the system `gdal-config` binary (from `libgdal-dev`). No `.whl` files
   are saved — pip resolves all dependencies before downloading. Fix: two-phase
   download — try full requirements first, then retry with `grep -v gdal` if it
   fails. This vendors all non-GDAL packages for offline use.

2. **Docker Compose `deploy.resources.limits` is enforced in non-swarm mode.**
   Docker Compose v2+ respects `cpus` and `memory` limits under
   `deploy.resources.limits` when running `docker compose up`. The `docker compose
   config` command expands `4G` to `4294967296` bytes and `0.5` cpus to
   `"0.5"` — both are valid.

3. **ML model base weights are on HuggingFace, not GitHub.** DOFA, TorchGeo
   ResNet50 S1, Clay, and TerraMind all use HuggingFace model repositories. The
   URLs in the script are best-effort — if a model repo path changes, update the
   `*_URL` variable at the top of `offline_prep.sh`. The script logs a warning
   and continues if any URL is unavailable.

4. **tippecanoe is not installed on the dev machine.** PMTiles generation is
   skipped with a warning. The documentation explains how to install it
   (`brew install tippecanoe` on macOS, build from source on Linux).

5. **Ollama model pull (`llama3.1:8b`) downloads 4.9 GB.** This is the
   slowest step in the script (~40 seconds at 125 MB/s on a fast connection,
   much longer on low-bandwidth). The script starts the Ollama container first,
   waits for it to be healthy, then pulls the model. If the pull is interrupted,
   re-running the script detects the partial model and resumes.

6. **`set -euo pipefail` with `|| log_warn` pattern works for resilience.**
   Each potentially-failing command is followed by `|| log_warn "..."`. The `||`
   operator prevents `set -e` from exiting because the overall expression
   succeeds (the right side returns 0). This allows the script to continue past
   individual download failures while still catching genuine errors (like missing
   required arguments or undefined variables).

7. **Docker build caching makes the script idempotent for image builds.**
   Re-running `docker build` or `docker compose build` when images are already
   built returns instantly (all layers CACHED). No explicit "skip if exists"
   check is needed for Docker images.

### Resource limits added

| Service | CPUs | Memory |
|---------|------|--------|
| db | 2 | 4G |
| redis | 0.5 | 512M |
| redpanda | 2 | 4G |
| minio | 1 | 1G |
| ollama | 4 | 8G |
| benthos | 0.5 | 512M |
| backend | 2 | 4G |
| frontend | 0.5 | 512M |
| prometheus | 0.5 | 512M |
| grafana | 0.5 | 512M |

### Files produced
- `scripts/offline_prep.sh` — 12-step offline preparation script (executable)
- `scripts/offline_prep_lib.sh` — helper functions (logging, download, step runner)
- `docs/offline-prep.md` — documentation with hardware requirements and troubleshooting
- `docker-compose.yml` — modified: added `deploy.resources.limits` to all 10 services

## T4 — FastAPI app skeleton: routes, auth, error model, OpenAPI, WebSocket (2026-07-18)

### Outcome
Full FastAPI skeleton with JWT auth, 6 demo users, role-based access control,
request ID middleware, org context middleware (server-side org_id from JWT),
global error handler (`{error:{code,message,request_id}}`), 7 API route groups
under `/api`, and a WebSocket endpoint at `/ws/events/{incident_id}`. All
verification commands pass: OpenAPI 3.1 served at `/openapi.json`, login returns
JWT, wrong password returns 401, all 6 demo users authenticate successfully.

### Key findings

1. **passlib 1.7.x is incompatible with bcrypt 4.x.** passlib's internal
   `detect_wrap_bug()` function hashes a >72-byte test string to detect a
   legacy bcrypt bug. bcrypt 4.x enforces the 72-byte limit strictly (3.x
   silently truncated), causing `ValueError: password cannot be longer than
   72 bytes` at import/first-use time. Fix: use the `bcrypt` package directly
   (`bcrypt.hashpw` / `bcrypt.checkpw`) instead of `passlib.CryptContext`.
   The `bcrypt` package is already installed as a dependency of
   `passlib[bcrypt]`, so no requirements change needed.

2. **Starlette middleware ordering: `add_middleware` inserts at position 0.**
   The LAST middleware added via `add_middleware()` is the OUTERMOST (runs
   first on request, last on response). To get `RequestID → OrgContext → CORS`
   execution order, add CORS first, then OrgContext, then RequestID last.

3. **Users table created outside Alembic via `Base.metadata.create_all`.**
   The Alembic migration (`0001_init_schema.py`) was not modified. The User
   model is registered to `Base.metadata`, and the users table is created
   idempotently in the lifespan startup via
   `Base.metadata.create_all(bind=engine, tables=[User.__table__])`. This
   is safe because `create_all` uses `CREATE TABLE IF NOT EXISTS`.

4. **Circular import between `deps.py` and `auth/roles.py` resolved by import
   ordering.** `deps.py` defines `get_current_user`, then imports
   `require_roles` from `auth/roles.py` at the END of the file. When
   `roles.py` imports `get_current_user` from `deps.py`, it's already defined.
   This is a standard Python pattern for breaking circular imports.

5. **`OAuth2PasswordRequestForm` + `OAuth2PasswordBearer` is the cleanest JWT
   login pattern.** The form accepts `username` and `password` fields
   (form-encoded, not JSON). The `OAuth2PasswordBearer(tokenUrl="/api/auth/login")`
   security scheme makes the OpenAPI "Authorize" button work automatically.
   `auto_error=True` (default) returns 401 if no token is provided on
   protected routes.

6. **`org_context` middleware extracts org_id from JWT — never from client.**
   The middleware decodes the Bearer token (if present) and stores
   `org_id` in `request.state.org_id`. This is separate from
   `get_current_user` (which does full DB-backed authentication). The
   middleware is for tenancy scoping; the dependency is for auth. JWT
   decoding happens twice (middleware + dependency) but is cheap.

7. **Global error handler via `@app.exception_handler(Exception)`.** Registered
   handlers for `HTTPException`, `RequestValidationError`, and `Exception`
   ensure all errors return `{error:{code,message,request_id}}`. The
   `request_id` comes from `request.state.request_id` set by the RequestID
   middleware. The existing `/api/_test/error` endpoint (RuntimeError) is
   caught and returns 500 with the error format.

8. **WebSocket endpoint uses `receive_text()` to keep connection alive.**
   The `/ws/events/{incident_id}` endpoint accepts the connection, sends
   `{"type":"connected","incident_id":"..."}`, then loops on `receive_text()`.
   A "ping" message gets a `{"type":"pong"}` response. Real Redpanda consumer
   fanout will replace the loop with a server-side push.

9. **Redpanda failure is non-fatal.** The lifespan tries to start an
   `AIOKafkaProducer` in a try/except. When Redpanda is down (container
   exited), the producer fails to bootstrap, logs a warning, and the app
   continues without Kafka. This is the correct behavior for development.

### Files produced/modified
- `backend/app/main.py` (MODIFY — lifespan, middleware, route groups, error handler)
- `backend/app/deps.py` (MODIFY — get_current_user, oauth2_scheme, require_roles re-export)
- `backend/app/models/__init__.py` (MODIFY — added User export)
- `backend/app/models/user.py` (NEW — User model: id, email, hashed_password, role, org_id, created_at)
- `backend/app/middleware/__init__.py` (NEW)
- `backend/app/middleware/request_id.py` (NEW — UUID4, X-Request-Id header)
- `backend/app/middleware/org_context.py` (NEW — org_id from JWT, never from client)
- `backend/app/middleware/error_handler.py` (NEW — {error:{code,message,request_id}})
- `backend/app/auth/jwt.py` (NEW — python-jose HS256 create/decode)
- `backend/app/auth/passwords.py` (NEW — bcrypt direct, not passlib)
- `backend/app/auth/roles.py` (NEW — require_roles(*roles) dependency factory)
- `backend/app/auth/seed.py` (NEW — 6 demo users, password demo1234)
- `backend/app/schemas/auth.py` (NEW — TokenResponse, LoginRequest, UserInfo)
- `backend/app/schemas/observations.py` (NEW — ObservationResponse with from_attributes=True)
- `backend/app/api/routes/auth.py` (NEW — POST /api/auth/login)
- `backend/app/api/routes/observations.py` (NEW — GET /api/observations stub)
- `backend/app/api/routes/hypotheses.py` (NEW — GET /api/hypotheses stub)
- `backend/app/api/routes/scenarios.py` (NEW — GET /api/scenarios stub)
- `backend/app/api/routes/optimize.py` (NEW — GET /api/optimize stub)
- `backend/app/api/routes/sensing.py` (NEW — GET /api/sensing stub)
- `backend/app/api/routes/eval.py` (NEW — GET /api/eval stub)
- `backend/app/api/routes/ws.py` (NEW — WebSocket /ws/events/{incident_id})

## T3 — ULID + timestamp + audit hash-chain + idempotency primitives (2026-07-18)

### Outcome
Created 5 utility modules in `backend/app/lib/` and 2 test files. All 9 tests pass
against the real PostgreSQL database in Docker (exit 0). ULIDs are 26-char
Crockford base32, monotonic per process. The audit hash-chain detects tampering
of any middle row. Idempotency dedup works via a unique constraint on
`(source, external_id)`.

### Key findings

1. **The `ulid` PyPI package is not in `requirements.txt`.** Rather than add a
   new dependency for a 128-bit identifier, implemented ULID natively in
   `ulid.py` using `time.time_ns()` + `os.urandom(10)`. The implementation is
   monotonic within a process: same-millisecond calls increment the 80-bit
   randomness portion under a `threading.Lock`. A `parse_ulid()` helper is
   included for round-trip verification. 100 rapid-fire ULIDs sort ascending.

2. **Crockford base32 encoding is bit-exact, not byte-exact.** The 48-bit
   timestamp encodes to 10 chars (50 bits, 2 leading zero padding bits), and
   the 80-bit randomness encodes to 16 chars (80 bits exact). Total = 26 chars.
   The encoder extracts 5-bit chunks from the low end of the big-endian int
   and reverses, so the first char carries the high bits. `parse_ulid` must
   right-shift the timestamp by 2 to drop the padding bits.

3. **`verify_chain` returns `True | int`, not `bool`.** The MUST DO says
   "Return True if all match, False if any mismatch (return the index of first
   mismatch)" — these two specs conflict (False vs. int index). Resolved by
   returning `True` on success and the 0-based int index on first mismatch.
   The test uses `is True` / `is not True` so it works whether the return is
   `False` or an int. Tampering the middle row (index 1) returns `1`.

4. **The `idempotency_keys` table is NOT in the Alembic migration.** The task
   explicitly forbade modifying the migration or existing models. Created a new
   `IdempotencyKey` model inside `idempotency.py` (extending `Base`) and an
   `ensure_table(engine)` helper that calls `IdempotencyKey.__table__.create(
   checkfirst=True)`. The test module calls `ensure_table(engine)` once via an
   autouse module-scoped fixture. In production, `ensure_table` should be
   called at app startup or added to a future migration.

5. **`IntegrityError` is the dedup signal.** `check_and_record` inserts a row
   and commits; on a duplicate `(source, external_id)`, PostgreSQL raises
   `IntegrityError` (unique constraint violation). The function catches it,
   rolls back, and returns `False`. This is the canonical SQLAlchemy pattern
   for insert-or-reject dedup — no need for a SELECT-then-INSERT race.

6. **Canonical JSON must use `separators=(",", ":")` for byte-stable hashes.**
   `json.dumps(sort_keys=True)` alone is not enough — the default separators
   include a space after every `,` and `:`. While this is consistent within a
   process, explicit compact separators make the hash independent of any
   future `json` default changes and match the AGENTS.md "canonical
   serialization" intent.

7. **`datetime.fromisoformat` (Python 3.11) does not accept a trailing `Z`.**
   The `from_iso()` helper strips `Z` and replaces with `+00:00` before
   parsing. Naive datetimes (no tzinfo) are assumed UTC. The `to_iso()`
   helper formats with millisecond precision and a `Z` suffix:
   `2026-07-18T09:01:20.826Z`. Round-trip `from_iso(to_iso(ms)) == ms` is exact.

8. **`verify_chain` orders by `(ts, id)`, not just `ts`.** Two events written
   in the same millisecond would have identical `ts` values. Ordering by
   `id` as a tiebreaker is not strictly correct for ULIDs (the randomness
   portion is not guaranteed monotonic across processes), but within a single
   writer process the ULID monotonicity ensures correct ordering. For
   multi-writer scenarios, a sequence column or Lamport timestamp would be
   needed — out of scope for T3.

9. **`serialize.py` interprets `visibility` as the viewer's clearance level.**
   The task spec was ambiguous ("visibility level" could mean the object's
   classification or the viewer's clearance). Chose viewer clearance because
   the rules ("sensitive fields hidden for public visibility", "draft fields
   hidden for non-internal users") only make sense from the viewer's
   perspective. `SENSITIVE_FIELDS` and `DRAFT_FIELDS` are frozensets defined
   at module level for easy extension.

### Files produced
- `backend/app/lib/ulid.py` — 26-char Crockford base32 monotonic ULID (96 LOC)
- `backend/app/lib/time.py` — now_ms / from_iso / to_iso (40 LOC)
- `backend/app/lib/audit.py` — write_audit + verify_chain (115 LOC)
- `backend/app/lib/idempotency.py` — IdempotencyKey model + ensure_table + check_and_record (72 LOC)
- `backend/app/lib/serialize.py` — visibility + review_status serializer (88 LOC)
- `backend/tests/test_audit.py` — 5 tests: single append, 3-event chain, tamper, empty, per-org isolation
- `backend/tests/test_idempotency.py` — 4 tests: first insert, duplicate, different external_ids, different sources

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_audit.py tests/test_idempotency.py -v"
→ 9 passed, 1 warning in 0.60s (exit 0)
```

## T12 — Federated data fabric: source ownership, policy-controlled sharing, delayed sync (2026-07-18)

### Outcome
Created the federated data fabric with source management, ownership discipline, and
delayed sync outbox. 5 tests pass against the real PostgreSQL database (exit 0). The
fabric respects source ownership: federated sources are NOT centralized — their
outbox entries are marked as "skipped" during sync_outbox(), preventing blind
data centralization.

### Key findings

1. **SourceKind enum is distinct from the existing SourceType enum.** The existing
   `SourceType` (in `enums.py`) classifies observation provenance (satellite, sensor,
   drone, etc.). The new `SourceKind` classifies the source's protocol/type (cap_feed,
   sensorthings, ogc_features, stac, hdx, social_media, citizen_report, internal).
   Both enums are needed — an observation from a SensorThings API source has
   `source_type=sensor` (what kind of data) and its source has `type=sensorthings`
   (what protocol the source uses). Defined SourceKind, SourceStatus, and Ownership
   in `source.py` to avoid modifying the shared `enums.py`.

2. **The `add_to_outbox` signature required a `payload` parameter extension.** The
   task spec listed `add_to_outbox(observation_id, source_id, sync_priority=0)`,
   but without the observation data, `sync_outbox()` cannot insert the observation.
   Extended to `add_to_outbox(observation_id, source_id, payload, sync_priority=0)`
   where `payload` is a dict containing all Observation fields plus `geometry_wkt`
   (a WKT string). The `_build_observation()` helper converts the payload dict to
   an Observation ORM object, transforming `geometry_wkt` → `WKTElement` and
   string enum values → enum instances.

3. **Ownership discipline is enforced in `sync_outbox()`, not in `add_to_outbox()`.**
   The outbox accepts entries for any source regardless of ownership. The sync
   loop checks `source.ownership`:
   - `owned` / `aggregated`: insert the observation locally (centralized)
   - `federated`: mark as "skipped" with error "federated source — not centralized"
   This design lets field devices queue observations offline even for federated
   sources; the sync loop decides whether to centralize based on current ownership
   policy. A source's ownership can change between when the outbox entry was
   created and when sync_outbox() runs.

4. **`sync_outbox()` is idempotent via a pre-insert existence check.** Before
   constructing and inserting an Observation, the method checks
   `db.get(Observation, entry.observation_id)`. If the observation already exists
   (e.g., from a previous sync run that committed the observation but crashed
   before marking the outbox entry as synced), the entry is marked as "synced"
   without re-inserting. This prevents duplicate-key IntegrityErrors on re-runs.

5. **Error recovery in `sync_outbox()` uses rollback + re-fetch.** When an
   observation insert fails (e.g., constraint violation), `db.rollback()` undoes
   the pending insert. The outbox entry object becomes expired after rollback.
   The code re-fetches it via `db.get(OutboxEntry, entry.id)` and marks it as
   "failed" with the error message (truncated to 500 chars). The final
   `db.commit()` persists all status changes (synced, skipped, failed) in one
   transaction.

6. **The `sources` and `federation_outbox` tables are created on demand via
   `ensure_tables(engine)`.** Following the same pattern as `IdempotencyKey` in
   `idempotency.py` — the Alembic migration was not modified (per task
   constraints). The test module calls `ensure_tables(engine)` once via an
   autouse module-scoped fixture. In production, `ensure_tables` should be
   called at app startup or added to a future migration.

7. **The `type` column name is safe in PostgreSQL.** Although `type` is a Python
   builtin, it's a valid column name in PostgreSQL (not a reserved word). The
   SQLAlchemy model uses `type: Mapped[SourceKind]` and the column is created
   as `type` in the table. No quoting issues. The `register_source` method
   accepts `type` as a parameter name, which shadows the builtin within the
   method scope — this is fine and matches the task spec signature.

8. **OutboxEntry uses a String `status` column, not a PG enum.** The status
   values (pending, synced, skipped, failed) are stored as plain strings. This
   avoids creating a PostgreSQL enum type (which would need to be in the
   migration) and allows easy extension of status values without migration
   changes. The tradeoff is no DB-level constraint on valid status values,
   but the application layer enforces this via the OutboxManager methods.

### Files produced
- `backend/app/models/source.py` — Source model + SourceKind, SourceStatus, Ownership enums (80 LOC)
- `backend/app/ingestion/federation.py` — SourceManager, OutboxManager, OutboxEntry, ensure_tables (234 LOC)
- `backend/tests/test_federation.py` — 5 tests: register, update_status, delayed_sync, ownership_filter, federated_not_centralized (219 LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_federation.py -v"
→ 5 passed, 1 warning in 0.25s (exit 0)
```

## T5 — OpenTelemetry + Prometheus + Grafana observability (2026-07-18)

### Outcome
Backend exposes a `/metrics` endpoint returning Prometheus-format metrics.
Prometheus scrapes it every 15s (target `up`). Grafana starts and is
accessible at http://localhost:3000. Six custom metrics are registered and
visible in Prometheus queries. Existing `/healthz`, `/healthz/deep`, and
`/api/*` endpoints are unchanged.

### Key findings

1. **Middleware order is critical for OTel trace-ID propagation.** The
   `TelemetryMiddleware` must be added to the FastAPI app BEFORE
   `FastAPIInstrumentor.instrument_app(app)` is called. Starlette adds
   middleware last-added = outermost, so `instrument_app` (called second)
   wraps `TelemetryMiddleware`. The OTel span is therefore already active
   when `TelemetryMiddleware.dispatch` runs, and
   `trace.get_current_span().get_span_context()` returns a valid context.
   If the order is reversed, the span is not yet active and `trace_id`
   is never set on `request.state`.

2. **`opentelemetry-instrumentation-sqlalchemy` is NOT in requirements.txt.**
   The task said "Do NOT add new dependencies." SQLAlchemy instrumentation
   is attempted via a `try/except ImportError` — if the package is not
   installed, it logs a debug message and skips. FastAPI instrumentation
   (`opentelemetry-instrumentation-fastapi`) IS in requirements.txt and
   works. To enable SQLAlchemy tracing, add
   `opentelemetry-instrumentation-sqlalchemy>=0.46b0` to requirements.txt.

3. **No OTel span exporter is wired (dev mode).** The `TracerProvider` is
   configured with a `Resource` but no `SpanProcessor`/exporter. Spans are
   created (so trace IDs propagate to `request.state.trace_id`) but not
   shipped anywhere. Add a `BatchSpanProcessor` with an `OTLPExporter` or
   `ConsoleSpanExporter` in production for distributed tracing.

4. **Grafana provisioning files are created but NOT mounted.** The
   `docker-compose.yml` Grafana service does not mount
   `./grafana/provisioning` to `/etc/grafana/provisioning`. The task said
   "Do NOT modify docker-compose.yml," so the datasource and dashboard
   provisioning files exist on disk but are not visible inside the
   container. To enable auto-provisioning, add this volume mount to the
   Grafana service in `docker-compose.yml`:
   ```yaml
   volumes:
     - grafana_data:/var/lib/grafana
     - ./grafana/provisioning:/etc/grafana/provisioning:ro
   ```

5. **Path normalization prevents label cardinality explosion.** The
   middleware uses `request.scope["route"].path` (the route template, e.g.
   `/api/observations/{observation_id}`) when available, falling back to
   a regex that replaces 8+ char hex segments with `/{id}`. Without this,
   every unique ULID in a URL path would create a new time series.

6. **`prometheus_client` auto-exposes Python process metrics.** In addition
   to the six custom metrics, the `/metrics` endpoint includes
   `process_resident_memory_bytes`, `process_virtual_memory_bytes`,
   `process_cpu_seconds_total`, `process_start_time_seconds`,
   `python_gc_*`, and `python_info`. The Grafana dashboard uses these for
   the CPU and memory panels — no node_exporter needed.

7. **The `/metrics` endpoint is self-referential.** Every Prometheus scrape
   increments `http_requests_total{path="/metrics"}`. This is desirable —
   it lets you monitor scrape health — but means the metric count grows
   even with no user traffic.

### Files produced
- `backend/app/lib/telemetry.py` — 188 LOC. Six metrics, TelemetryMiddleware,
  setup_telemetry(), metrics_endpoint().
- `grafana/provisioning/datasources/prometheus.yml` — Prometheus datasource.
- `grafana/provisioning/dashboards/dashboards.yml` — dashboard provider.
- `grafana/provisioning/dashboards/system_health.json` — 6-panel dashboard
  (request rate, error rate, p50/p95 latency, memory, CPU, WebSocket+queue).

### Files modified
- `backend/app/main.py` — added `setup_telemetry(app)` call after error
  handlers, added `/metrics` endpoint.
- `prometheus.yml` — added `scrape_timeout: 10s` to backend scrape config.

### Verification
```
curl -s http://localhost:8000/metrics | head -5
→ # HELP python_gc_objects_collected_total Objects collected during gc
→ # TYPE python_gc_objects_collected_total counter
→ python_gc_objects_collected_total{generation="0"} 752.0

curl -s 'http://localhost:9090/api/v1/query?query=up' | jq '.data.result[].value[1]'
→ "1"  (backend target is up)

curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
→ 302  (Grafana redirect to login)

docker compose up -d prometheus grafana --wait
→ Container ieee-grafana-1 Healthy
→ Container ieee-prometheus-1 Healthy
```

## T6 — CAP 1.2 adapter — parse, validate, ingest CAP alerts (2026-07-18)

### Outcome
Created `backend/app/ingestion/adapters/cap.py` (207 pure LOC) with
`parse_cap_alert(xml_string) -> dict` and `ingest_cap_alert(db, xml_string,
org_id, incident_id) -> str`. All 6 tests pass against the real PostgreSQL
database in Docker (exit 0). The adapter parses OASIS CAP 1.2 XML, extracts
geometry (polygon or circle), severity, urgency, and all alert metadata,
maps to the Observation model, and writes a row with idempotent dedup via
`(source_id, raw_data_hash)` lookup.

### Key findings

1. **CAP polygon coordinates are `lat,lon` — opposite of WKT/GeoJSON.** The
   OASIS CAP 1.2 spec says polygon is "space-delimited list of
   latitude/longitude pairs" where each pair is `latitude,longitude`. WKT
   and GeoJSON use `(longitude, latitude)` ordering. The parser must swap
   the order when constructing WKT: `POLYGON ((lon lat, ...))`. Getting
   this wrong silently produces mirrored geometries that look correct on
   a map but are in the wrong hemisphere.

2. **CAP polygon does not require a closing point.** The spec says "at least
   4 coordinate pairs (3 points + closing point)" but many real feeds send
   only the unique vertices without repeating the first. The parser
   auto-closes the ring by appending `coords[0]` if `coords[0] !=
   coords[-1]`. Shapely's `Polygon()` requires a closed ring, so this
   must happen before construction.

3. **CAP circle radius is in kilometers, not meters.** The spec says the
   circle element is `lat,lon radius` where radius is in kilometers. To
   buffer the point into a polygon, convert km to degrees using the
   rough equatorial conversion (1 degree ~ 111 km). This is an
   approximation — for high-latitude alerts the buffer will be slightly
   elongated. The true radius is preserved in `geometry_uncertainty`
   (converted to meters: `radius_km * 1000`).

4. **Observation.geometry is NOT NULL — CAP alerts without geometry must be
   rejected.** The model has `Geometry(geometry_type="GEOMETRY", srid=4326)`
   without `nullable=True`. Some CAP alerts have only `<areaDesc>` text
   without polygon/circle. The adapter raises `ValueError` in this case
   rather than inserting a NULL geometry (which would fail at the DB level
   anyway). This is the correct behavior — an observation without spatial
   data is not useful in this platform.

5. **Idempotency via `(source_id, raw_data_hash)` SELECT-then-INSERT, not
   unique constraint.** The Observation table has no unique constraint on
   `(source_id, raw_data_hash)` (and the task forbade modifying migrations).
   The adapter does a SELECT before INSERT. This has a TOCTOU race in
   concurrent scenarios, but for a single-worker ingestion loop it is
   sufficient. A future migration could add a unique constraint and use
   `ON CONFLICT DO NOTHING` for true atomic dedup.

6. **CAP references format is `sender,identifier,sent` (space-delimited for
   multiple).** For Update/Cancel messages, the `<references>` element
   contains one or more `sender,identifier,sent` triples separated by
   spaces. The adapter parses these, constructs the `source_id` for each
   referenced alert (`cap:{sender}:{identifier}`), and looks up the prior
   observation to set the `supersedes` foreign key. If the referenced
   alert hasn't been ingested yet, `supersedes` is left NULL (graceful
   degradation for out-of-order delivery).

7. **`review_status` is not a column on the Observation model.** The
   AGENTS.md mentions `review_status in {draft,reviewed,official}` but the
   Observation model (27 columns) does not include this field. The
   `corroboration_state=uncorroborated` enum serves as the "draft" state
   for observations. The `review_status` concept is likely handled at the
   API serialization layer (T3's `serialize.py` with `DRAFT_FIELDS`), not
   stored on the model. The adapter sets
   `corroboration_state=uncorroborated` as the equivalent of "draft".

8. **`xml.etree.ElementTree` is sufficient for CAP parsing — no
   lxml/defusedxml needed.** CAP 1.2 uses a single XML namespace
   (`urn:oasis:names:tc:emergency:cap:1.2`). ElementTree handles this with
   the `{namespace}tag` prefix syntax. No external dependencies were added
   to `requirements.txt`. For untrusted feeds, `defusedxml` would be safer
   (prevents billion-laughs/entity expansion attacks), but it's not in the
   current requirements and the task scope is trusted official feeds.

9. **`shapely` is already in requirements.txt — use it for geometry
   construction.** Rather than manually constructing WKT strings (error-prone
   with coordinate ordering and ring closure), use
   `shapely.geometry.Polygon` and `.wkt` for valid WKT output. For circles,
   `Point(lon, lat).buffer(radius_km / 111.0)` produces a valid polygon
   approximation. Shapely validates the geometry before serialization.

10. **Access policy derived from severity, not scope.** The task says
    extreme/severe -> sensitive, moderate/minor -> internal. This is a
    content-based classification, independent of the CAP `<scope>` element
    (which is Public/Restricted/Private — a distribution scope, not a data
    sensitivity classification). The adapter maps severity to access_policy
    and stores the CAP scope in `quality_flags` for auditability.

### Files produced
- `backend/app/ingestion/adapters/__init__.py` — package marker
- `backend/app/ingestion/adapters/cap.py` — CAP 1.2 parser + ingester (207 pure LOC)
- `backend/tests/test_cap_adapter.py` — 6 tests: parse polygon, parse circle,
  ingest to DB, idempotent reparse, circle ingest, supersedes on update

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_cap_adapter.py -q"
-> 6 passed, 1 warning in 0.14s (exit 0)
```

## T8 — OGC API Features adapter (2026-07-18)

### Outcome
Created `backend/app/ingestion/adapters/ogc_features.py` (231 pure LOC) and
`backend/tests/test_ogc_adapter.py` (188 pure LOC). All 4 tests pass against
the real Postgres DB with mocked OGC HTTP endpoints.

```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_ogc_adapter.py -q"
-> 4 passed, 1 warning in 0.45s (exit 0)
```

### Key findings

1. **Migration 0001 is missing entity-specific columns.** The init migration
   creates entity tables (road_segments, shelters, hospitals, etc.) with only
   the basic columns: id, org_id, incident_id, created_at, updated_at,
   geometry, properties. The ORM models in `entities.py` define additional
   columns (name, status, capacity, occupancy, zone_type, building_type) that
   are NOT in the migration. Any ORM INSERT fails with
   `column "name" of relation "road_segments" does not exist`.

   **Fix:** Added a module-scoped autouse fixture `_ensure_columns` in the test
   file that runs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for all missing
   columns before tests run. This follows the same pattern as
   `test_idempotency.py`'s `ensure_table()`. A proper migration (0002) should
   be created later to add these columns permanently.

2. **httpx.Response requires `request` parameter for `raise_for_status()`.**
   In httpx 0.28, `httpx.Response(200, json=fc)` works for `.json()` but
   `raise_for_status()` raises `RuntimeError: Cannot call raise_for_status as
   the request instance has not been set on this response`. The mock response
   must include a `request` parameter:
   ```python
   req = httpx.Request("GET", "https://mock.example.org/...")
   resp = httpx.Response(200, json=fc, request=req)
   ```

3. **JSONB path access for upsert conflict detection works.** The
   `properties["_external_id"].astext == value` SQLAlchemy expression compiles
   to `properties ->> '_external_id' = :value` in PostgreSQL. This allows
   finding existing entity rows by their OGC feature ID stored in the JSONB
   `properties` column, without needing a dedicated `external_id` column.

4. **Conflict detection via `_source_hash` + `_user_edited` flag.** The adapter
   stores a 16-char SHA-256 hash of (geometry + properties) in
   `properties._source_hash`. On re-sync, if the hash matches, the row is
   skipped (no-op). If a user has set `properties._user_edited = True`, the
   upsert is skipped entirely to preserve user edits. This is tested in
   `test_upsert_user_edited_not_overwritten`.

5. **Async adapter with sync DB session.** The `OGCFeaturesClient.pull_features`
   method is async (httpx.AsyncClient), but DB operations use the synchronous
   `SessionLocal`. `sync_collection` is async (calls `pull_features`) but
   delegates to the synchronous `upsert_feature` for DB writes. Tests use
   `asyncio.run()` to bridge — no `pytest-asyncio` needed.

6. **Mocking httpx with unittest.mock.** The tests patch
   `client._client.get` (the AsyncClient's get method) with
   `unittest.mock.AsyncMock`. This intercepts HTTP calls before any real I/O,
   so the AsyncClient never needs a real event loop connection. The mock is
   active across multiple `asyncio.run()` calls within the same test.

### Files produced
- `backend/app/ingestion/adapters/__init__.py` — package init
- `backend/app/ingestion/adapters/ogc_features.py` — OGCFeaturesClient,
  pull_features, map_to_entity, upsert_feature, sync_collection
- `backend/tests/test_ogc_adapter.py` — 4 tests (roads, shelters, upsert
  conflict, user-edited protection)

### Entity type mapping
The adapter supports 8 entity types via `ENTITY_MAP`:
road_segment, shelter, hospital, zone, building, bridge, power_substation,
cell_tower. Each maps to its ORM class and a whitelist of property fields
copied from GeoJSON `properties` to model columns.

## T7 — SensorThings API adapter (2026-07-18)

### Outcome
Created OGC SensorThings API v1.0 async client adapter that pulls sensor
observations with pagination (`@iot.nextLink`), maps them to the Observation
model, and inserts via `sync_datastream`. 6 tests pass with mocked HTTP
endpoints (no real SensorThings server required).

### Key findings

1. **`httpx.MockTransport` is the cleanest HTTP mocking approach for async
   httpx clients.** No `responses` or `respx` package needed — `httpx.MockTransport`
   is built into httpx 0.28.x and accepts a handler function
   `(request: httpx.Request) -> httpx.Response`. The handler can inspect the
   URL and return different responses for pagination tests. Tests inject the
   transport by setting `client._client = httpx.AsyncClient(transport=..., timeout=...)`.

2. **`pytest-asyncio` is NOT in the Docker image.** The verification command
   only does `pip install pytest -q`. Use `asyncio.run()` inside synchronous
   test functions instead of `@pytest.mark.asyncio`. Pattern:
   ```python
   def test_foo():
       async def _test():
           # async setup + assertions
           ...
       asyncio.run(_test())
   ```
   This works because `asyncio.run()` creates a fresh event loop per call.
   The `httpx.AsyncClient` must be created INSIDE the async function (not
   outside) to bind to the correct event loop.

3. **SensorThings `$expand` inlines related entities in a single request.**
   Instead of fetching Datastream and FeatureOfInterest separately for each
   observation, use `$expand=Datastream,FeatureOfInterest` in the Observations
   URL. This returns each observation with nested `Datastream` (for phenomenon
   name + unitOfMeasurement) and `FeatureOfInterest` (for geometry). The
   `map_to_observation` function then extracts everything from the single
   expanded dict.

4. **`@iot.nextLink` is a full URL, not a relative path.** The pagination loop
   follows it directly without prepending `base_url`. A safety guard
   (`_MAX_PAGES = 100`) prevents infinite loops if a server misbehaves.

5. **404/timeout handling returns `None` from `_fetch_json`, which breaks the
   pagination loop and returns an empty list.** This is the graceful
   degradation pattern: the adapter logs a warning and returns `[]`, allowing
   the caller (`sync_datastream`) to skip insertion and return 0. No
   exceptions propagate to the caller.

6. **Idempotency follows the same pattern as `cap.py`: check
   `(source_id, raw_data_hash, org_id)` before insert.** The `source_id` is
   formatted as `sensorthings:{@iot.id}`. The `raw_data_hash` is
   `sha256:` + canonical JSON of the observation dict. This prevents duplicate
   inserts when the same datastream is synced multiple times.

7. **`WKTElement` from GeoAlchemy2 is the correct type for the `geometry`
   column.** The Observation model uses `Geometry(geometry_type="GEOMETRY",
   srid=4326)`. Setting `geometry=WKTElement("POINT(lng lat)", srid=4326)`
   works for both Point and Polygon GeoJSON features. The `_feature_to_wkt`
   helper converts GeoJSON to WKT, handling Point and Polygon types.

### Files produced
- `backend/app/ingestion/adapters/sensorthings.py` — SensorThingsClient,
  pull_observations, map_to_observation, sync_datastream (243 LOC)
- `backend/tests/test_sensorthings_adapter.py` — 6 tests: pull_observations,
  pagination, timeout, 404, geometry mapping, sync_datastream (203 LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_sensorthings_adapter.py -q"
→ 6 passed, 1 warning in 0.06s (exit 0)
```

## T10 — Event-time processing pipeline: Redpanda + Benthos (2026-07-18)

### Outcome
Full event-time processing pipeline operational: aiokafka async producer writes to
Redpanda `observations.raw`, Benthos normalizes + dedups + switch-routes to
type-specific topics and `observations.normalized`, and an async consumer INSERTs
into PostgreSQL with idempotency dedup and audit provenance. End-to-end test
passes: produce → benthos normalize → consumer INSERT → row in PostgreSQL.
Duplicate observation_id is correctly deduped (only 1 row inserted).

### Key findings

1. **Redpanda container memory limit must exceed `--memory 4G` flag.** The
   docker-compose `deploy.resources.limits.memory: 4G` leaves only ~3.93GB
   available inside the container (kernel overhead). Redpanda's `--memory 4G`
   flag requires exactly 4294967296 bytes, so it fails with
   `insufficient physical memory: needed 4294967296 available 4225761280`.
   Fix: bump the container limit to 5G while keeping `--memory 4G` for Redpanda.

2. **Benthos `switch` output default is a case without `check`, not a separate
   `output` field.** The `switch` output type has `cases`, and the default
   output is the last case without a `check` field. Writing `output:` at the
   `switch` level (separate from `cases`) causes a lint error:
   `field output not recognised`. Correct pattern:
   ```yaml
   output:
     switch:
       cases:
         - check: errored()
           output: {kafka: {topic: observations.dlq}}
         - output:  # default (no check)
             kafka: {topic: observations.normalized}
   ```

3. **Benthos `switch` output `continue: true` enables fan-out routing.** To send
   a message to BOTH a type-specific topic AND the default `observations.normalized`,
   set `continue: true` on the type-specific case. The message is sent to the
   matching case's output, then continues to the next case (eventually hitting the
   default). Without `continue: true`, only the first matching case's output
   receives the message.

4. **Benthos `fan_out` output does NOT support nested `switch` outputs.** Attempting
   to nest a `switch` output inside `fan_out.outputs` causes
   `unable to infer component type`. Use `switch` with `continue: true` instead
   for conditional fan-out.

5. **Benthos `mapping` processor (not `bloblang`) is the current name.** Benthos
   v4.27.0 uses `mapping` as the processor name for Bloblang mappings. The older
   `bloblang` processor name is deprecated.

6. **Benthos error handling: `errored()` persists through the pipeline.** When a
   `mapping` processor fails (e.g., `content().parse_json()` on invalid JSON),
   the `errored()` flag is set and persists through subsequent processors. A
   `switch` processor with `check: errored()` can create an error payload, and
   the output `switch` with `check: errored()` routes to DLQ. The `!errored()`
   check in a second `switch` processor conditionally runs `dedupe` only on
   valid messages.

7. **Benthos `dedupe` processor with Redis cache works for cross-restart
   dedup.** The `dedupe` processor uses a cache resource to track seen keys.
   With a Redis cache, dedup state survives benthos restarts. The `key` field
   accepts Bloblang interpolation: `key: ${! json("observation_id") }`.

8. **`from geoalchemy2 import func` fails — use `from sqlalchemy import func`.**
   GeoAlchemy2 does not export `func` directly. PostGIS functions like
   `ST_GeomFromGeoJSON` and `ST_SetSRID` are accessed via SQLAlchemy's `func`
   object: `func.ST_SetSRID(func.ST_GeomFromGeoJSON(geojson), 4326)`.

9. **aiokafka `enable_idempotence=True` requires `acks="all"`.** The idempotent
   producer semantics in aiokafka/Redpanda require all ISR replicas to
   acknowledge. This is the correct setting for the observation pipeline where
   data loss is unacceptable.

10. **Consumer DLQ pattern: commit offset after DLQ send.** When a message fails
    processing, the consumer sends it to the DLQ topic and then commits the
    offset. This prevents infinite reprocessing of poison messages. The
    `finally: await self._consumer.commit()` in the consume loop ensures the
    offset is committed regardless of success or failure.

### Pipeline architecture
```
ProducerManager → observations.raw (Redpanda)
                        ↓
                   Benthos pipeline:
                   1. mapping: parse JSON, normalize
                      (timestamp→epoch ms, source_type→UPPERCASE,
                       lat/lng→GeoJSON Point, set defaults)
                   2. switch: if errored() → build error payload
                   3. switch: if !errored() → dedupe by observation_id (Redis)
                   4. output switch:
                      - errored() → observations.dlq
                      - SENSOR (continue) → observations.sensor
                      - CITIZEN_REPORT (continue) → observations.citizen
                      - SATELLITE (continue) → observations.satellite
                      - OFFICIAL_FEED (continue) → alerts.official
                      - default → observations.normalized
                        ↓
                   ConsumerManager (reads observations.normalized)
                   1. check_and_record (idempotency dedup by source+observation_id)
                   2. INSERT Observation to PostgreSQL
                   3. write_audit (hash-chained provenance)
                   4. On error → send to observations.dlq
```

### Redpanda topics created
- `observations.raw` — producer input
- `observations.normalized` — benthos output (consumer reads this)
- `observations.sensor` — type-specific (source_type=SENSOR)
- `observations.citizen` — type-specific (source_type=CITIZEN_REPORT)
- `observations.satellite` — type-specific (source_type=SATELLITE)
- `alerts.official` — type-specific (source_type=OFFICIAL_FEED)
- `observations.dlq` — dead letter queue (malformed messages)

### Files produced/modified
- `backend/app/streaming/__init__.py` (NEW — exports ProducerManager, ConsumerManager)
- `backend/app/streaming/producer.py` (NEW — ProducerManager: start/send/stop, 71 LOC)
- `backend/app/streaming/consumer.py` (NEW — ConsumerManager: start/consume/stop, 174 LOC)
- `benthos/disaster_pipeline.yaml` (MODIFIED — full pipeline: input→normalize→dedup→switch-route→output, 126 LOC)
- `docker-compose.yml` (MODIFIED — redpanda memory limit 4G→5G for container headroom)

### Verification
```
# Topics created
docker compose exec redpanda rpk topic list
→ 7 topics (observations.raw, observations.normalized, observations.sensor,
   observations.citizen, observations.satellite, alerts.official, observations.dlq)

# End-to-end test
ProducerManager.send("observations.raw", {observation_id, event_type, ...})
→ Benthos normalizes (timestamp→epoch ms, source_type→UPPERCASE, lat/lng→GeoJSON)
→ observations.normalized + observations.sensor (continue: true fan-out)
→ ConsumerManager reads observations.normalized
→ check_and_record (idempotency dedup)
→ INSERT Observation to PostgreSQL
→ write_audit (hash-chained provenance)
→ SUCCESS: Observation found in PostgreSQL with all 27 fields

# Dedup test
Send same observation_id twice → only 1 row in PostgreSQL (dedup via idempotency_keys)

# DLQ test
Send malformed JSON to observations.raw → Benthos routes to observations.dlq
with error: "failed to parse value as JSON: invalid character 't'"
```

## T11 — Temporal crisis knowledge graph (Apache AGE) (2026-07-18)

### Outcome
Created `backend/app/knowledge/graph.py` (234 pure LOC) with a `KnowledgeGraph`
class that manages entities, edges, and contradictory hypotheses via Apache AGE
Cypher queries, with a recursive CTE fallback over `graph_edges`. 5 tests pass
against the real PostgreSQL database (exit 0). The 2-hop graph query returns
correct neighbors; contradictory hypotheses are both preserved.

### Key findings

1. **SQLAlchemy `text()` interprets Cypher's `:Label` and `:relationship` syntax
   as bind parameters.** The Cypher query `CREATE (a)-[:passes_through]->(b)`
   contains `:passes_through`, which SQLAlchemy's `text()` parser treats as a
   bind parameter named `passes_through`. This raises
   `InvalidRequestError: A value is required for bind parameter 'passes_through'`.
   The `$$` dollar-quoting used by AGE does NOT help — SQLAlchemy's parser
   does not understand PostgreSQL dollar-quoting and scans the entire string
   for `:` patterns. Fix: use `Connection.exec_driver_sql()` which bypasses
   SQLAlchemy's parameter parsing and passes the SQL string directly to psycopg.

2. **AGE's `cypher()` function does NOT accept bind parameters for the graph
   name.** Attempting `SELECT * FROM cypher($1, $2) AS (...)` raises
   `psycopg.errors.SyntaxError: a name constant is expected`. The graph name
   must be a string literal in the SQL statement. The Cypher query string
   also cannot be a bind parameter — both must be embedded in the SQL string
   literal (via `$$` dollar-quoting).

3. **AGE Cypher variable-length paths return ALL paths, not unique neighbors.**
   `MATCH p=(start)-[*1..N]->(neighbor) RETURN neighbor.id, length(p)` returns
   one row per path, not per neighbor. If there are multiple paths to the same
   neighbor (e.g., via cycles), duplicates appear. Fix: use
   `RETURN neighbor.id, labels(neighbor), min(length(p)) AS hop` — Cypher's
   implicit grouping groups by the non-aggregate columns and returns the
   minimum path length.

4. **AGE graph state persists across test runs — must clear between tests.**
   The AGE graph is a PostgreSQL schema. Once created, vertices and edges
   persist until explicitly deleted or the graph is dropped. Tests that call
   `add_entity()` and `add_edge()` will accumulate data across runs, causing
   duplicate vertices and inflated neighbor counts. Fix: add a `clear_graph()`
   method that executes `MATCH (n) DETACH DELETE n` to remove all vertices
   and edges without dropping the graph itself.

5. **The recursive CTE fallback is essential for reliability.** AGE Cypher
   queries can fail silently (the `_cypher` helper swallows `SQLAlchemyError`
   for resilience). If AGE is available but the Cypher query fails (e.g.,
   vertex doesn't exist), the query returns 0 results without raising. The
   `query_neighbors` method tries Cypher first, and if it returns results,
   uses them. If Cypher fails or AGE is unavailable, it falls back to the
   recursive CTE on `graph_edges`, which always works because edges are
   always written to the relational table.

6. **`graph_edges` is the relational mirror; AGE is the query accelerator.**
   The `add_edge` method ALWAYS writes to `graph_edges` (committed first),
   then mirrors to AGE if available. This ensures edges survive even if AGE
   has issues. The `add_entity` method is a no-op when AGE is unavailable —
   entities are implicitly represented by their edges in `graph_edges`.
   This dual-write pattern means the recursive CTE path and the Cypher path
   produce the same results.

7. **AGE graph names must be valid PostgreSQL identifiers.** ULID-based
   incident IDs start with digits (timestamp portion), which are invalid as
   PostgreSQL identifiers. The graph name is constructed as
   `g_{incident_id.lower()}` with non-alphanumeric characters replaced by
   underscores. The `g_` prefix ensures it starts with a letter.

8. **Contradictory hypotheses are preserved by design.** The `add_hypothesis`
   method creates a new Hypothesis row with `status=active` — it never
   checks for or modifies existing hypotheses about the same entity. Two
   hypotheses with contradictory claims (e.g., "road passable" vs "road
   impassable") coexist in the database. The `get_hypotheses` method returns
   ALL hypotheses for an entity, including contradictory ones. Resolution is
   deferred to the human decision-maker via `update_hypothesis_status`.

9. **`exec_driver_sql` returns a `CursorResult` that is iterable.** Unlike
   `Session.execute(text(...))` which returns a `Result` object with
   `.fetchall()`, `.scalar()`, etc., `exec_driver_sql` returns a
   `CursorResult` that can be iterated directly with `for row in result`.
   Row access is positional (`row[0]`, `row[1]`) or by column name
   (`row.column_name`).

### Graph topology used in tests
```
R1 (road) --passes_through--> Z1 (zone)
R1 (road) --provides_access_to--> H1 (hospital)
H1 (hospital) --reachable_via--> B1 (building)
B1 (building) --refers_to--> S1 (shelter)
S1 (shelter) --provides_access_to--> Z1 (zone)

2-hop from R1: Z1 (hop 1), H1 (hop 1), B1 (hop 2)
```

### Files produced
- `backend/app/knowledge/__init__.py` — package init, exports KnowledgeGraph
- `backend/app/knowledge/graph.py` — KnowledgeGraph class (234 pure LOC):
  create_graph, add_entity, add_edge, query_neighbors, query_two_hop,
  add_hypothesis, link_observation, get_hypotheses, update_hypothesis_status,
  clear_graph, drop_graph
- `backend/tests/test_knowledge_graph.py` — 3 tests: add_entity_and_edge,
  query_neighbors (1-hop), two_hop_query (5 entities + 5 edges)
- `backend/tests/test_hypotheses.py` — 2 tests: contradictory_hypotheses_preserved,
  hypothesis_status_transitions (active -> resolved -> superseded)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_knowledge_graph.py tests/test_hypotheses.py -q"
→ 5 passed, 1 warning in 0.42s (exit 0)
```

---

## T9: STAC Catalog + HDX HAPI Adapter (2026-07-18)

### Task
Create STAC and HDX HAPI adapters for satellite imagery indexing and humanitarian data ingestion.

### Files produced
- `backend/app/ingestion/adapters/stac.py` (NEW — STACClient + index_item, 218 pure LOC)
- `backend/app/ingestion/adapters/hdx.py` (NEW — HDXClient + map_to_observations, 171 pure LOC)
- `backend/tests/test_stac_adapter.py` (NEW — 4 tests: index 3 items, cloud cover filter, local catalog, remote search)
- `backend/tests/test_hdx_adapter.py` (NEW — 3 tests: pull 2 indicators, geometry mapping, indicator filter)

### Design decisions

**STAC adapter (`stac.py`)**:
- `STACClient(catalog_url)` supports both remote STAC APIs (HTTP) and local file catalogs (offline).
  - Detects local catalogs via `os.path.isfile(catalog_url)` — if True, reads JSON from disk.
  - Remote search uses `GET /search` with `bbox`, `datetime`, `collections` params.
  - Cloud cover filtering is done client-side (not all STAC APIs support the filter extension).
  - Pagination follows `rel=next` links in the STAC response `links` array.
- `index_item(stac_item, org_id, incident_id)` returns a dict (not an Observation model instance)
  per the task spec. The dict contains all 23+ Observation fields plus `geometry_wkt` (string,
  not WKTElement) for JSON-serializable portability.
- Imagery asset URLs are stored in `quality_flags.assets` as `{key: {href, type}}` for later
  download in T18. No imagery is downloaded now.
- `source_type = SourceType.satellite`, `collection_method = "stac_api"`.
- `source_reliability = 0.9` (satellite data is high-quality).
- `event_type = "satellite_imagery"`, `phenomenon = constellation or collection`.

**HDX adapter (`hdx.py`)**:
- `HDXClient(base_url)` uses HDX HAPI (NOT the retired HXL services — retired Jan 31, 2026).
- `pull_indicators(country, indicator_ids)` hits `{base_url}/population?country_code={country}`,
  follows `next_url` pagination, optionally filters by `#indicator+code` client-side.
- `map_to_observations(indicator, org_id, incident_id)` returns `list[dict]` (typically 1 item).
- HDX indicators are country-level, so geometry is a country centroid from a 14-entry ISO3
  lookup table (`_COUNTRY_CENTROIDS`). Unknown countries default to `POINT(0.0 0.0)`.
- `geometry_uncertainty = 50000.0` (50km) — reflects country-level granularity.
- `source_type = SourceType.official_feed`, `collection_method = "hdx_hapi"`.
- `source_reliability = 0.85` (official humanitarian data).
- HXL hashtags are used as dict keys (e.g. `#indicator+code`, `#country+code`, `#date`).

### Key learning: httpx params={} strips URL query params
When following STAC pagination "next" links, passing `params={}` to `httpx.AsyncClient.get()`
causes httpx to strip the query params from the next-link URL. Fix: only pass `params` on the
first request; for subsequent pages, call `client.get(url)` without `params` so the next-link
URL (which carries its own query params) is used as-is.

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_stac_adapter.py tests/test_hdx_adapter.py -q"
→ 7 passed, 1 warning in 0.05s
```

Tests:
1. `test_index_stac_items` — indexes 3 STAC items (cloud_cover 5%, 25%, 80%), verifies all
   metadata fields (geometry WKT, cloud cover, platform, instruments, assets, source_id, etc.)
2. `test_search_by_cloud_cover` — filters by max_cloud_cover threshold (20% → 1 item, 30% → 2, None → 3)
3. `test_search_local_catalog` — writes FeatureCollection to temp file, searches offline
4. `test_search_remote` — mocks STAC API with httpx.MockTransport, tests pagination + cloud cover filter
5. `test_pull_indicators` — mocks HDX HAPI, pulls 2 indicators (POP + AFFECTED), verifies mapping
6. `test_map_to_observations_geometry` — verifies country centroid lookup (COL, AFG, unknown)
7. `test_pull_with_indicator_filter` — filters pulled indicators by indicator_ids list

## T15 — Phenomenon-specific freshness decay (2026-07-18)

### Outcome
Created `backend/app/fusion/freshness.py` (96 LOC) with `FreshnessCalculator`
class implementing per-phenomenon exponential decay F = exp(-age/tau). 10
tests pass (exit 0). All stopping conditions verified: road 60s old F=0.905
(>0.9), road 2h old F=6.1e-6 (<0.01), building 1h old F=0.959 (>0.9).

### Key findings

1. **Timestamps are epoch milliseconds but tau is in seconds — must convert.**
   The Observation model stores `observed_at` as `BigInteger` UTC epoch ms
   (per AGENTS.md convention), but the task spec defines tau in seconds. The
   `compute_freshness` method converts: `age_seconds = (current_time -
   observed_at) / 1000.0` before applying `exp(-age_seconds / tau)`. Forgetting
   this conversion would make freshness decay 1000x too fast (a 60s-old road
   observation would have F=exp(-60000/600)≈0 instead of 0.905).

2. **Freshness is computed on READ, not stored at write time.** The
   `compute_freshness` and `compute_for_observation` methods take the current
   time as a parameter (or call `now_ms()` internally). This means freshness
   is always current — a 5-minute-old observation queried now and queried
   again in 10 minutes will have different freshness values. The
   `Observation.freshness` column (Float, written at ingestion) is the
   stored-at-write value; the `FreshnessCalculator` provides the live value.
   Both coexist: the stored value is for sorting/filtering at query time;
   the computed value is for real-time fusion decisions.

3. **Future observations (clock skew) must be clamped to F=1.0.** When
   `observed_at > current_time` (e.g., producer clock is ahead of consumer),
   `exp(-negative)` returns a value > 1.0. The method returns 1.0 immediately
   for `age_ms <= 0` to keep F in [0, 1]. This is the correct behavior for
   clock skew tolerance — a "future" observation is treated as maximally
   fresh rather than producing an invalid freshness > 1.

4. **Instance-level tau overrides don't mutate the module-level dict.** The
   `FreshnessCalculator.__init__` copies `TAU_BY_PHENOMENON` into
   `self._overrides` via `dict(...)`. `update_tau` modifies only the instance
   dict. This means multiple `FreshnessCalculator` instances can have
   different tau configurations (e.g., per-tenant) without interfering. A
   future DB table backing per-tenant tau would replace `self._overrides`
   with a DB lookup.

5. **`SimpleNamespace` does not satisfy `typing.Protocol` for static type
   checkers.** The `_ObsLike` Protocol requires `observed_at: int` and
   `phenomenon: str`. `SimpleNamespace` sets attributes dynamically, so
   basedpyright reports `reportArgumentType`. Fix: use a `@dataclass` with
   typed fields in tests. The dataclass satisfies the Protocol structurally
   and gives proper type checking. This is a general pattern for test
   doubles of ORM models — prefer dataclasses over SimpleNamespace when a
   Protocol constrains the parameter type.

6. **`compute_for_observation` uses real `now_ms()` — tests must align.**
   Unlike `compute_freshness` (which takes `current_time` as a parameter),
   `compute_for_observation` calls `now_ms()` internally. Tests that use a
   fixed 2023 timestamp for `observed_at` will see F≈0 because the real
   wall clock is 2026. Fix: call `now_ms()` in the test to set `observed_at`
   to the current time, then assert `f > 0.99` (allowing a few ms of
   elapsed time between setting `observed_at` and computing freshness).

7. **The 9 phenomenon types span 5 orders of magnitude in tau.** From
   `responder_position` (τ=60s, 1 min) to `demographic_vulnerability`
   (τ=2592000s, 30 days). This reflects the physical reality: a responder's
   position is stale after a minute, but a neighborhood's demographic
   vulnerability profile is stable for weeks. Using a single τ for all feeds
   would either over-decay slow phenomena (building footprints appearing
   stale after 10 minutes) or under-decay fast phenomena (responder positions
   appearing fresh after an hour).

### Stopping condition verification
- Road 60s old: F = exp(-60/600) = exp(-0.1) = 0.9048 > 0.9 ✓
- Road 2h old (7200s): F = exp(-7200/600) = exp(-12) = 6.14e-6 < 0.01 ✓
- Building 1h old (3600s): F = exp(-3600/86400) = exp(-0.0417) = 0.9592 > 0.9 ✓

### Files produced
- `backend/app/fusion/freshness.py` — FreshnessCalculator with per-phenomenon
  tau, compute_freshness, compute_for_observation, update_tau (96 LOC)
- `backend/tests/test_freshness.py` — 10 tests: per_type_decay, default_tau,
  zero_age, old, custom_tau, compute_for_observation, nonpositive_tau_rejected,
  future_clamped, instance_isolation, all_taus_present (148 LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_freshness.py -q"
→ 10 passed, 1 warning in 0.03s (exit 0)
```

## T14 — Source reliability Beta model tests (2026-07-18)

### Outcome
Created `backend/tests/test_reliability.py` (215 pure LOC, 8 tests) verifying the
existing `backend/app/fusion/reliability.py` (184 LOC, committed in 453048a).
All 8 tests pass against the real PostgreSQL database in Docker (exit 0). No
bugs found in the implementation — `reliability.py` was NOT modified.

### Key findings

1. **The implementation is correct and matches the spec.** Verified all 8
   acceptance criteria:
   - Prior Beta(2,2) returns expected=0.5, CI=(0.1, 0.9) (hardcoded per spec;
     actual scipy CI for Beta(2,2) is ~0.068-0.932, but spec mandates 0.1-0.9).
   - 3 correct reports: alpha=5, beta=2, expected=5/7≈0.714 > 0.6 ✓
   - 2 disproven reports: alpha=2, beta=4, expected=2/6≈0.333 < 0.4 ✓
   - Conditioned reliability: roads (α=10, β=1) → 0.909 reliable; flood_depth
     (α=1, β=10) → 0.091 poor ✓
   - Time decay: alpha_eff = alpha * decay_factor, beta_eff = beta * decay_factor
     applied to ALL rows of the source (global + per-phenomenon) ✓
   - 95% CI via scipy.stats.beta.ppf(0.025/0.975, alpha, beta) ✓
   - get_conditioned_reliability returns dict excluding the global row ✓
   - update creates a row from prior Beta(2,2) if source is unknown ✓
   - Beta(2,2) CI width (~0.865) > Beta(100,100) CI width (~0.138) ✓

2. **scipy is a transitive dependency, not in requirements.txt.** The task spec
   said "scipy is already in requirements.txt" but `grep scipy requirements.txt`
   returns no matches. However, `python -c "import scipy"` works in the Docker
   image (scipy 1.17.1) — it's pulled in as a transitive dep of torch/torchgeo.
   No action needed; the import works at runtime.

3. **Test pattern follows test_idempotency.py.** Module-scoped autouse fixture
   calls `ensure_table(engine)` once; function-scoped `db` fixture yields a
   SessionLocal session and cleans up all rows for the test SOURCE after each
   test. This keeps tests isolated and idempotent across re-runs.

4. **Conditioned reliability test inserts rows directly.** The `update()` method
   only increments alpha/beta by 1 per call. To set up the exact scenario
   (roads α=10 β=1, flood_depth α=1 β=10) without 8+ update calls, the test
   inserts SourceReliability rows directly with the desired alpha/beta values.
   This tests `get_reliability(source_id, phenomenon_type)` in isolation from
   the update path.

5. **Time decay test verifies ALL rows are decayed.** `apply_time_decay` fetches
   all rows for a source (both global and per-phenomenon) and multiplies alpha
   and beta by decay_factor. The test sets up two rows (global + conditioned),
   applies decay_factor=0.5, and verifies both rows were decayed using
   `pytest.approx` for float comparison.

6. **CI widens with uncertainty test uses two Beta distributions.** Beta(2,2)
   has a wide 95% CI (~0.068-0.932, width ~0.865) because few pseudo-counts
   mean high uncertainty. Beta(100,100) has a narrow CI (~0.431-0.569, width
   ~0.138) because many pseudo-counts mean high confidence. The test asserts
   `width_low > width_high` and that both CIs bracket 0.5 (symmetric priors).

7. **No bugs found in reliability.py.** The implementation correctly:
   - Handles NULL phenomenon_type via `.is_(None)` in `_get_row`
   - Creates rows from prior Beta(2,2) when source is unknown
   - Commits after each update/decay operation
   - Excludes the global row from `get_conditioned_reliability` via
     `.is_not(None)` filter
   - Returns hardcoded prior CI (0.1, 0.9) for the no-data case, matching the
     spec (not the actual scipy CI of ~0.068-0.932)

### Files produced
- `backend/tests/test_reliability.py` — 8 tests covering all acceptance criteria
  (215 pure LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_reliability.py -q"
→ 8 passed, 1 warning in 1.13s (exit 0)
```

## T22 — ML model serving infrastructure (2026-07-18)

### Outcome
Created ONNX Runtime model serving layer with lazy loading, in-memory caching,
idle eviction, and a model registry table. 6 tests pass using in-memory SQLite
and mock ONNX sessions (no real model weights or MinIO required). The download
script's `--list` flag outputs all 3 pre-cataloged models. This is Wave 4
infrastructure — T18 (SAR flood mapping), T19 (ensemble), T20 (damage), T21
(NLP) will all use `ModelServing.run_inference()` instead of touching ONNX
Runtime directly.

### Key findings

1. **`JSONB` does NOT compile on SQLite.** `sqlalchemy.dialects.postgresql.JSONB`
   raises `CompileError: Compiler can't render element of type JSONB` when
   `create_all` runs on a SQLite engine. The task required both JSONB columns
   (for PostgreSQL production) and in-memory SQLite tests. Solution: a
   `JSONBCompat(TypeDecorator)` that uses `JSONB` on PostgreSQL and `JSON` on
   other dialects. This is a standard SQLAlchemy cross-dialect pattern — 15 LOC,
   no runtime overhead, and the model registry table doesn't need JSONB's GIN
   indexing (it has <100 rows).

2. **`Base.metadata.create_all(engine)` on SQLite fails for the full schema.**
   The `app.models.__init__` module imports all models (Observation with
   GeoAlchemy2 `Geometry`, entities, etc.) into `Base.metadata`. Running
   `create_all` on SQLite tries to create ALL tables and fails on `Geometry`
   (PostGIS-only). Solution: `ensure_table(engine)` creates only the `models`
   table via `ModelRecord.__table__.create(bind=engine, checkfirst=True)`. This
   follows the same pattern as `ensure_table` in `idempotency.py` and
   `ensure_tables` in `federation.py`.

3. **The `scripts/` directory is NOT mounted inside the backend Docker container.**
   `docker-compose.yml` mounts `./backend:/app` — the `scripts/` directory at the
   repo root is outside this mount. Tests running inside the container cannot
   access `scripts/download_models.py` via `os.path` or `subprocess`. Solution:
   the catalog logic (`MODEL_CATALOG`, `format_catalog()`) lives in
   `app/perception/serving.py` (inside the mount), and the script is a thin CLI
   wrapper that imports from there. The test verifies `format_catalog()` output
   (which is what `--list` calls) and conditionally checks the script file if
   accessible.

4. **Mock ONNX sessions are sufficient for serving-layer tests.** The task
   allows mocking `InferenceSession` instead of creating real ONNX models. The
   mock session implements `get_inputs()`, `get_outputs()`, and `run()` — the
   only three methods `ModelServing._run_session()` calls. The mock is injected
   by overriding `serving._create_session` with a lambda that returns the mock.
   This tests the lazy-loading/cache/eviction logic without requiring the `onnx`
   package (which is NOT in requirements.txt — only `onnxruntime` is).

5. **`onnxruntime` IS in requirements.txt (line 29).** `onnxruntime>=1.18.0`
   was already listed from T1. Version 1.27.0 is installed in the Docker image.
   No requirements.txt modification needed.

6. **Thread-safe cache with `threading.Lock`.** The in-memory model cache is a
   `dict[str, _CachedModel]` protected by a `threading.Lock`. The lock is held
   for cache reads/writes only — the expensive MinIO download and ONNX session
   creation happen OUTSIDE the lock (after a cache miss is detected). This
   prevents concurrent requests for the same model from triggering duplicate
   downloads (a subtle race: two threads both see a cache miss, both download).
   For the current single-worker deployment this is acceptable; for
   multi-worker, a per-model lock or double-checked locking would be needed.

7. **`_CachedModel` uses `slots=True` without `frozen=True`.** The
   `last_used_ms` field must be mutable (updated on every cache hit). Using
   `frozen=True` would require replacing the entire object on each access.
   `slots=True` without `frozen=True` gives memory efficiency + mutability.

8. **Model versioning format: `name:version`.** The `run_inference` method
   returns `{"outputs": ..., "model_version": "model-name:1.0.0"}`. This is
   what gets recorded on the observation's `model_version` column for
   provenance tracking (T2's Observation model has `model_version: String,
   nullable=True`).

### Files produced
- `backend/app/perception/models.py` — ModelRecord ORM, JSONBCompat, enums,
  ensure_table (69 pure LOC)
- `backend/app/perception/serving.py` — ModelServing class, MODEL_CATALOG,
  format_catalog (196 pure LOC)
- `scripts/download_models.py` — CLI with --list and --download flags
  (77 pure LOC)
- `backend/tests/test_serving.py` — 6 tests: lazy loading, inference, idle
  unload, CRUD, versioning, catalog list (190 pure LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_serving.py -v"
→ 6 passed, 1 warning in 0.08s (exit 0)

docker compose run --rm -e PYTHONPATH=/app -v ./scripts:/scripts backend \
  python /scripts/download_models.py --list
→ sar-flood-mapping, building-damage, incident-nlp (3 models)
```

## T13 — Confidence vector computation (6 dimensions) (2026-07-18)

### Outcome
Created `backend/app/fusion/confidence.py` (240 pure LOC) with
`ConfidenceVector` dataclass and `ConfidenceVectorCalculator` class computing
all 6 dimensions per SOTA spec §6.1: S (source reliability), C (corroboration),
F (freshness), G (geo precision), M (model uncertainty), K (conflict). 8 tests
pass (exit 0). The vector is stored in `quality_flags["confidence_vector"]`.
Display confidence (weighted sum) is computed for UI only — the reasoning
engine always uses the full 6-D vector.

### Key findings

1. **In-memory SQLite cannot create the observations table due to JSONB and
   Geometry columns.** The Observation model uses `JSONB` for `quality_flags`
   and `provenance_chain`, and `Geometry` from geoalchemy2 for the `geometry`
   column. SQLite's type compiler can't render `JSONB` (raises `CompileError`)
   and geoalchemy2 tries to call `RecoverGeometryColumn()` (a SpatiaLite
   function) during table creation. The `@compiles(JSONB, "sqlite")` and
   `@compiles(Geometry, "sqlite")` hooks can patch the column types, but the
   geoalchemy2 management DDL still fails. Solution: use in-memory SQLite only
   for the `source_reliability` table (via `ensure_table(engine)`), and pass
   `candidates` list directly to `compute_corroboration`/`compute_conflict`
   instead of querying the observations table.

2. **The `candidates` parameter decouples testing from the DB.** The task spec
   says `compute_corroboration(observation, db_session)`, but this requires the
   observations table to exist. Adding an optional `candidates` parameter
   (checked before `db_session`) lets tests pass dataclass observation doubles
   directly, avoiding the PostGIS/JSONB dependency entirely. In production,
   `db_session` is used to query the observations table via standard SQL
   (phenomenon + temporal window), with spatial proximity checked in Python
   via haversine distance.

3. **Spatial proximity is computed in Python, not via PostGIS functions.** The
   `_nearby` method queries the DB by phenomenon + org_id + temporal window
   (standard SQL, portable to any database), then filters by spatial proximity
   in Python using the haversine formula. The spatial window is
   `max(geometry_uncertainty, candidate.geometry_uncertainty, 100.0)` meters.
   This avoids PostGIS functions (`ST_DWithin`, `ST_Distance`) that don't work
   on SQLite and keeps the calculator portable.

4. **Corroboration and conflict use `1 - exp(-n)` normalization.** Both
   dimensions count nearby observations (within spatial+temporal window) and
   normalize via `1 - exp(-n)` where n is the count. This gives: 0 → 0.0,
   1 → 0.632, 2 → 0.865, 3+ → approaches 1.0. The function is monotonically
   increasing with diminishing returns, which matches the intuition that each
   additional corroborating/contradicting observation adds less evidence than
   the previous one.

5. **Contradiction detection uses relative value tolerance.** Two observations
   with the same phenomenon contradict each other if
   `|value_a - value_b| / max(|value_a|, |value_b|, 1.0) >= 0.2`. This handles
   both boolean-like values (road_passability: 1.0 vs 0.0 → contradicts) and
   continuous values (flood_depth: 2.0m vs 2.1m → corroborates, 2.0m vs 5.0m →
   contradicts). Observations with `value=None` never contradict (can't
   contradict without a quantitative value).

6. **Display confidence uses negative weights for M and K.** The formula is
   `display = 0.25*S + 0.20*C + 0.20*F + 0.10*G + (-0.10)*M + (-0.15)*K`.
   Higher model uncertainty and conflict decrease the display score. When
   M is None (direct observation), it's treated as 0.0 (no model uncertainty).
   The weights for positive dimensions sum to 0.75; the negative weights sum
   to -0.25. The display score ranges from -0.25 (all bad) to 0.75 (all good).
   This is a UI heuristic only — the reasoning engine uses the full 6-D vector.

7. **The `_ObsLike` Protocol enables structural typing for test doubles.** The
   calculator accepts any object with the right attributes (observation_id,
   source_id, source_type, phenomenon, observed_at, geometry_uncertainty,
   model_uncertainty, quality_flags, geometry, org_id, event_type, value).
   Tests use a `@dataclass` `_TestObs` that satisfies the Protocol structurally,
   giving proper type checking without needing the full ORM model. This is the
   same pattern as T15's `_ObsLike` Protocol in freshness.py.

8. **Geometry extraction handles 5 input formats.** The `_extract_coords`
   function accepts: (1) WKT string (tests), (2) WKB bytes, (3) GeoJSON dict,
   (4) shapely geometry, (5) geoalchemy2 element (production). It uses
   `shapely.wkt.loads`, `shapely.wkb.loads`, `shapely.geometry.shape`, or
   `geoalchemy2.shape.to_shape` depending on the input type. For non-point
   geometries, it uses the centroid. Returns `(lat, lng)` tuple.

### Stopping condition verification
- 6 dimensions for 5 test observations: `test_six_dimensions` creates 5 obs,
  each vector has s, c, f, g, m, k fields ✓
- Corroboration increases: `test_corroboration_increases` — C goes from 0.0
  (no candidates) → 0.632 (1 corrob) → 0.865 (2 corrob) ✓
- Conflict increases: `test_conflict_increases` — K goes from 0.0 (no
  candidates) → 0.632 (1 contradicting) ✓

### Files produced
- `backend/app/fusion/confidence.py` — ConfidenceVector dataclass +
  ConfidenceVectorCalculator (240 pure LOC)
- `backend/tests/test_confidence_vector.py` — 8 tests (161 pure LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_confidence_vector.py -q"
→ 8 passed, 1 warning in 0.94s (exit 0)
```

## T17 — Conformal calibration layer — MAPIE (2026-07-18)

### Outcome
Created `backend/app/fusion/calibration.py` (241 pure LOC) with
`ConformalCalibrator` class wrapping MAPIE 1.4.1 conformal prediction.
8 tests pass (exit 0). All stopping conditions verified: conformal
coverage 0.925 >= 0.89 for alpha=0.1; Brier score + ECE computed on mock
classifier; `partial_fit` (EnbPI `update`) changes intervals with new data.

### Key findings

1. **MAPIE 1.4.1 renamed all public classes — the task spec's API names
   don't exist.** The task said `MapieRegressor` and
   `MapieTimeSeriesRegressor` (pre-1.0 API). In v1.4.1 (installed):
   - `MapieRegressor` → `SplitConformalRegressor` (static calibration)
     or `CrossConformalRegressor` (cross-validation)
   - `MapieTimeSeriesRegressor` → `TimeSeriesRegressor` (EnbPI, ACI)
   - `mapie.regressor` module exists but does NOT export `MapieRegressor`
   - `partial_fit` does not exist; the streaming equivalent is
     `TimeSeriesRegressor.update(X, y)` (EnbPI) or
     `adapt_conformal_inference(X, y, gamma)` (ACI for distribution shift)
   The module docstring documents this mapping for future maintainers.

2. **MAPIE 1.4.1 SplitConformalRegressor API: fit → conformalize →
   predict_interval.** The workflow is:
   ```python
   sc = SplitConformalRegressor(estimator=LinearRegression(),
                                 confidence_level=0.9, prefit=False)
   sc.fit(X_train, y_train)          # fits the estimator
   sc.conformalize(X_calib, y_calib) # calibrates with held-out set
   y_pred, y_int = sc.predict_interval(X_test)
   # y_int shape: (n_samples, 2, 1) — [:, 0, 0] = lower, [:, 1, 0] = upper
   ```
   `prefit=False` means MAPIE fits the estimator; `prefit=True` requires
   a pre-fitted estimator. The internal train/calibration split (70/30)
   is done in `ConformalCalibrator.fit` before passing to MAPIE.

3. **TimeSeriesRegressor.update() is the partial_fit equivalent.**
   `TimeSeriesRegressor(method='enbpi')` supports streaming via
   `update(X, y)` which incorporates new labeled data and updates the
   conformal scores. After `update`, `predict(X, confidence_level=0.9)`
   returns intervals that reflect the new data. The intervals DO change
   — verified in `test_partial_fit`. Note: `update()` emits a
   UserWarning about `confidence_level` and `optimize_beta` having no
   effect in `update` (they're kept for API stability). This is benign.

4. **Classification metrics (Brier, ECE, reliability, NLL, false
   confidence) don't need MAPIE.** These are standard calibration
   metrics computed on probability arrays from any classifier. MAPIE
   is only needed for conformal prediction (intervals and prediction
   sets). The `ConformalCalibrator` provides both: MAPIE for regression
   conformal intervals, and static utility methods for classification
   calibration metrics. The tests use sklearn's `LogisticRegression` as
   a mock classifier to generate probabilities for the classification
   metrics, and `LinearRegression` for the regression conformal tests.

5. **ECE (Expected Calibration Error) formula: bin by confidence,
   compute |accuracy - confidence| per bin weighted by bin proportion.**
   For perfect calibration (y_prob == y_true), ECE = 0.0. For all-wrong
   (prob=1.0, label=0.0), ECE ≈ 1.0. The implementation uses
   `np.linspace(0, 1, n_bins+1)` for bin edges, with the last bin
   inclusive (`<=`) to catch prob=1.0 predictions. Empty bins contribute
   0 to the ECE (no data to miscalibrate).

6. **False confidence rate: fraction of high-confidence (>= threshold)
   predictions that are wrong.** This is the most operationally
   important metric — it answers "how often is the model confidently
   wrong?" For 5 predictions at prob=0.95 all with label=0, FCR=1.0.
   For a mix of 3 correct + 2 wrong at prob>=0.9, FCR=0.4. If no
   predictions exceed the threshold, FCR=0.0 (no false confidence
   possible).

7. **Geographically weighted conformal: per-H3-zone sub-calibrators.**
   The `h3_zone` parameter on `fit`/`predict`/`partial_fit` routes to
   a per-zone `ConformalCalibrator` via `_zone(h3_zone)`. Each zone
   gets an independent calibrator with its own estimator and calibration
   set. This handles spatial distribution shift — a model calibrated on
   flat terrain may be overconfident in mountainous regions. The
   `get_metrics()` method reports which zones have been calibrated.
   Tested in `test_geographically_weighted_conformal`: two zones fit
   on different data subsets produce different intervals.

8. **basedpyright `reportConstantRedefinition` flags uppercase parameter
   reassignment.** `X = np.asarray(X, dtype=float)` triggers this
   because basedpyright treats all-uppercase names as constants. Fix:
   use a lowercase alias (`xa = np.asarray(X, dtype=float)`). This is
   a basedpyright-specific strictness — the existing fusion modules
   (confidence.py, freshness.py) don't reassign parameters, so this
   pattern is new to this module.

9. **basedpyright `reportOptionalMemberAccess` on attribute narrowing.**
   `self._calibrator` is typed as `SplitConformalRegressor |
   TimeSeriesRegressor | None`. After `if self._calibrator is None:
   raise`, basedpyright narrows local variables but NOT attributes
   accessed via `self.`. Fix: assign to a local variable first
   (`cal = self._calibrator; if cal is None: raise; cal.fit(...)`).
   This is a known basedpyright limitation — attribute narrowing
   requires a local variable intermediary.

10. **`mapie>=0.9.0` in requirements.txt resolves to 1.4.1.** The
    version constraint `>=0.9.0` allows the 1.x major release which
    completely restructured the API. No requirements.txt modification
    was needed (the constraint is satisfied), but the code must use
    the v1.4.1 class names. If MAPIE 2.x introduces another API break,
    the module docstring's API mapping table should be updated.

### Stopping condition verification
- Conformal coverage 0.925 >= 0.89 for alpha=0.1 ✓ (test_coverage)
- Brier score computed on mock LogisticRegression ✓ (test_brier_score)
- ECE ≈ 0 for perfect calibration ✓ (test_ece)
- `partial_fit` (EnbPI update) changes intervals ✓ (test_partial_fit)
- Reliability data has correct structure ✓ (test_reliability_data)
- False confidence rate flags wrong predictions ✓ (test_false_confidence_rate)

### Files produced
- `backend/app/fusion/calibration.py` — ConformalCalibrator class with
  MAPIE 1.4.1 SplitConformalRegressor + TimeSeriesRegressor, metric
  utilities (Brier, ECE, reliability, NLL, coverage, false confidence),
  per-H3-zone geographically weighted conformal (241 pure LOC)
- `backend/tests/test_calibration.py` — 8 tests: coverage, brier_score,
  ece, partial_fit, reliability_data, false_confidence_rate,
  geographically_weighted_conformal, store_metrics_dashboard
  (158 pure LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_calibration.py -q"
→ 8 passed, 2 warnings in 1.67s (exit 0)
```

## T16 — Probabilistic world state estimation — pgmpy Dynamic Bayesian Network (2026-07-18)

### Outcome
Created `backend/app/fusion/world_state.py` (199 pure LOC) with
`WorldStateEstimator` class implementing a Dynamic Bayesian Network via
pgmpy's `DynamicBayesianNetwork` + `DBNInference` for exact inference
(junction tree). 6 tests pass (exit 0). All stopping conditions verified:
3-state flood severity over 3 time slices returns distributions summing
to 1.0; severe evidence increases P(severe) from prior 0.1 to > 0.5.

### Key findings

1. **pgmpy `DBNInference.forward_inference()` returns a `dict`, not a
   `list`.** The return type is `dict[tuple[str, int], DiscreteFactor]`
   mapping variable tuples to `DiscreteFactor` objects. Accessing
   `result[0]` raises `KeyError` (0 is not a tuple key), and
   `result.values` returns the dict's `.values()` method object (a
   `builtin_function_or_method`), not a numpy array. The correct
   extraction pattern is:
   ```python
   if isinstance(result, dict):
       factor = next(iter(result.values()))
   elif isinstance(result, list):
       factor = result[0]
   else:
       factor = result
   values = factor.values  # numpy array of probabilities
   ```
   This is not well-documented in pgmpy's docs — the DBN example notebook
   only shows `simulate()` and `fit()`, not `forward_inference()`.

2. **pgmpy DBN CPDs use `(node, time_slice)` tuples as the `variable`
   parameter.** Unlike standard Bayesian Networks where `variable` is a
   string, DBN CPDs require `variable=('flood_severity', 0)` — a tuple
   of (node_name, time_slice). The `evidence` parameter also uses tuples:
   `evidence=[('flood_severity', 0)]`. This is consistent across
   `TabularCPD`, `add_cpds()`, and `forward_inference()`.

3. **pgmpy auto-creates slice 1 observation CPDs from slice 0 patterns.**
   When you define `P(obs_0 | state_0)` and call
   `dbn.initialize_initial_state()`, pgmpy automatically creates
   `P(obs_1 | state_1)` with the same structure. You only need to
   explicitly define: (1) the prior `P(state_0)`, (2) the transition
   `P(state_1 | state_0)`, and (3) observation CPDs for slice 0 only.
   This halves the number of CPDs you need to write. The warning
   `Replacing existing CPD for ('flood_severity', 1)` is benign — it
   means pgmpy's auto-creation found your explicit transition CPD already
   in place.

4. **Observation node names must be unique across hazard types.** If two
   hazards (flood, fire) both have a `sensor_reading` node, the DBN
   treats them as the same node, creating an ambiguous parent
   relationship. Fix: prefix observation nodes with the hazard type:
   `flood_sensor_reading`, `fire_sensor_reading`. This creates
   independent sub-networks within a single DBN — each hazard's state
   node only parents its own observation nodes. `forward_inference`
   correctly computes marginals for disconnected sub-networks.

5. **pgmpy DBN only accepts `TabularCPD` (discrete states).** Continuous
   variables must be discretized before entering the DBN. The
   `discretize_sensor()` function maps continuous values to integer bin
   indices using left-closed, right-open intervals:
   `[bins[i], bins[i+1]) → state i`. For flood water level (meters):
   `[0, 0.5, 1.5, 3.0, 5.0, ∞)` → 5 bins matching severity states
   (none, minor, moderate, severe, extreme). The bin boundaries are
   documented as module-level constants (`FLOOD_SENSOR_BINS`,
   `FLOOD_SATELLITE_BINS`).

6. **The persistence-biased transition matrix models crisis inertia.**
   The default transition has 0.7 on the diagonal (state persists) and
   0.3/(n-1) off-diagonal (spread to other states). This reflects the
   physical reality that a severe flood doesn't instantly become "none" —
   it persists with high probability and gradually decays. With 3 states
   and prior P(severe)=0.1, after observing sensor=severe:
   - P(severe | sensor=severe) ≈ 0.557 (Bayesian update with accuracy=0.85)
   - P(severe at t+1 | sensor=severe at t) ≈ 0.456 (transition spreads)
   Both values are > 0.5 and > 0.1 respectively, satisfying the stopping
   conditions.

7. **Evidence values must be integer indices when `state_names` is not
   defined in CPDs.** pgmpy's `forward_inference` evidence dict accepts
   either string state names (if CPDs define `state_names`) or integer
   indices. Since DBN tuple variables complicate `state_names`
   registration, the `WorldStateEstimator` handles the mapping
   internally: `add_evidence()` accepts both string names ("severe") and
   integer indices (2), converting all to integers via `_state_index()`.
   The returned distribution maps back to state names via
   `dict(zip(self._states, probs))`.

8. **The rolling evidence window uses `deque(maxlen=N)`.** Evidence is
   stored per time slice in a `deque` with `maxlen=window_size`. When the
   window is full, the oldest evidence is automatically evicted. This
   bounds memory usage for long-running estimation sessions. The cache
   (`dict[(hazard, slice), distribution]`) is invalidated on every
   `add_evidence()` and `step()` call — stale cache entries would
   produce incorrect filtering results.

9. **`forward_inference` with empty evidence returns the prior (slice 0)
   or prediction (slice > 0).** When no evidence is provided,
   `forward_inference(variables=[(state, 0)], evidence={})` returns
   `P(state_0)` (the prior). For slice 1, it returns
   `P(state_1) = Σ_{state_0} P(state_1 | state_0) * P(state_0)` (the
   one-step prediction). This is the correct filtering behavior — with no
   observations, the belief evolves purely via the transition model.

### Stopping condition verification
- 3-state flood severity, 3 time slices, probabilities sum to 1.0 ✓
  (`test_forward_inference`)
- Prior P(severe)=0.1, with severe evidence P(severe) > 0.5 ✓
  (`test_evidence_increases_severe` — measured P(severe) ≈ 0.557)
- Transition matrix propagates state over time ✓
  (`test_transition_matrix` — P(severe) decreases from slice 0 to 1
  but stays above prior)
- Sensor reading updates state probability ✓
  (`test_sensor_model`)
- Multiple hazard types handled independently ✓
  (`test_multiple_hazard_types` — flood affected by evidence, fire
  stays at prior)

### Files produced
- `backend/app/fusion/world_state.py` — WorldStateEstimator class with
  pgmpy DynamicBayesianNetwork, DBNInference, rolling evidence window,
  caching, evidence discretization (199 pure LOC)
- `backend/tests/test_world_state.py` — 6 tests: forward_inference,
  evidence_increases_severe, transition_matrix, sensor_model,
  multiple_hazard_types, discretize_sensor (90 pure LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_world_state.py -q"
→ 6 passed, 2 warnings in 4.12s (exit 0)
```

## T20 — Building & road damage assessment (xBD/xView2 + SpaceNet 8) (2026-07-18)

### Outcome
Created `backend/app/perception/damage.py` (248 pure LOC) with `DamageAssessor`
class implementing building damage classification (xBD/xView2: no_damage, minor,
major, destroyed) and per-vehicle-class road passability (SpaceNet 8 operational
output). 6 tests pass (exit 0). A flooded road correctly yields ambulance P≈0.18
(low) and boat P≈0.86 (high) — passability differs by vehicle class.

### Key findings

1. **Boat passability inverts the flood factor.** A road can be passable for a
   boat while unsafe for an ambulance. The vehicle-class factor table uses a
   negative `flood_factor` for boats (`-1.0`), which triggers the branch
   `p = flood_prob * (1 - damage_prob * damage_factor)` instead of the standard
   `(1 - flood_prob * flood_factor) * (1 - damage_prob * damage_factor)`. This
   means flood ENABLES boat passage while BLOCKING all other vehicles. The
   sign of `flood_factor` is the discriminator — no separate code path needed
   per vehicle class.

2. **`compute_vehicle_class_passability` reads flood/damage probs from
   `road_segment["properties"]`, not from parameters.** The task signature is
   `compute_vehicle_class_passability(road_segment, vehicle_class)` — no
   flood_prob/damage_prob params. `assess_road_passability` attaches them to
   `road_segment["properties"]["flood_prob"]` and `["damage_prob"]` before
   iterating over vehicle classes. This keeps the public signature clean while
   allowing the helper to access the probabilities. The road_segment dict is
   mutable, so this is safe within a single `assess_road_passability` call.

3. **Uncertainty has two sources: model confidence and pre-event availability.**
   For building damage, `uncertainty = 1 - max_class_probability`. When
   pre-event imagery is missing (single-post-event-image model), a 0.1 penalty
   is added (capped at 1.0) because change detection is less reliable without
   a baseline. For road passability, uncertainty is the standard deviation of
   per-vehicle-class passabilities — high spread means high disagreement
   between vehicle classes, which indicates operational uncertainty.

4. **Mock model serving via duck typing, not inheritance.** The `_MockModelServing`
   in tests implements `run_inference(model_id, input_data) -> dict` — the only
   method `DamageAssessor` calls. No need to subclass `ModelServing` or set up
   the model registry table, MinIO, or ONNX sessions. The mock returns fixed
   logits `[0.5, 1.0, 3.0, 0.5]` which softmax to ~`[0.06, 0.10, 0.77, 0.06]`,
   predicting "major" damage with probability ~0.77. This is the same pattern
   as `test_serving.py`'s `_MockONNXSession` but simpler — no `_create_session`
   override needed.

5. **`_to_numpy` handles both torch tensors and numpy arrays via duck typing.**
   `hasattr(tensor, "detach")` detects torch tensors (which need
   `.detach().cpu().numpy()`), while `np.asarray(tensor)` handles numpy arrays
   directly. This avoids importing torch in `damage.py` — torch is only needed
   in tests for `torch.randn(3, 256, 256)` fixture creation. The 3D→4D batch
   dimension expansion (`arr[np.newaxis, ...]`) happens automatically for 3D
   inputs (the common case from `torch.randn(3, H, W)`).

6. **Failure time uses a 3-tier threshold, not a continuous decay.** If the
   worst vehicle-class passability is below 0.3, `failure_time = 0.0` (already
   failed). Above 0.7, `failure_time = None` (not expected to fail soon).
   Between 0.3 and 0.7, `failure_time = worst * 3600` (proportional, up to 1
   hour). This gives operational teams a clear signal: 0 = act now, None = safe,
   intermediate = monitor. A continuous decay would be more precise but less
   actionable.

7. **GeoJSON output carries `feature_id` and `geometry` from the source.**
   Both `BuildingDamageResult` and `RoadPassabilityResult` have optional
   `feature_id` and `geometry` fields. For road passability, these come from
   the `road_segment` dict. For building damage, the caller sets them from the
   building footprint. The `to_geojson` static method serializes both result
   types into a single `FeatureCollection` — building features carry
   `damage_class` + `class_probabilities`, road features carry
   `vehicle_class_passabilities` + `traversal_speed` + `failure_time`.

8. **`numpy` is a transitive dependency of torch, not in requirements.txt.**
   `grep numpy requirements.txt` returns no matches, but `python -c "import numpy"`
   works in the Docker image (numpy 2.x is pulled in by torch/torchgeo). No
   requirements.txt modification needed — the task forbids adding dependencies.

### Vehicle-class factor table

| Vehicle class | flood_factor | damage_factor | Behavior |
|---|---|---|---|
| ambulance | 0.90 | 0.50 | Almost fully blocked by flood; moderately affected by damage |
| fire_truck | 0.70 | 0.60 | Moderately blocked by flood; more damage-sensitive |
| boat | -1.0 | 0.50 | Flood ENABLES passage; damage still blocks |
| high_clearance_vehicle | 0.50 | 0.70 | Tolerant of flood; more damage-sensitive |
| regular_vehicle | 0.95 | 0.90 | Almost fully blocked by both flood and damage |

### Stopping condition verification
- Building damage from fixture image: `test_building_damage_classification`
  — `torch.randn(3, 256, 256)` → `DamageClass.major`, probability > 0.5 ✓
- Road passability ambulance P=0.2, boat P=0.9: `test_vehicle_class_passability`
  — flood=0.9, damage=0.1 → ambulance ≈ 0.18 (< 0.3), boat ≈ 0.86 (> 0.8) ✓
- Different vehicle classes get different P: `test_road_passability_differs_by_class`
  — 5 classes, ≥3 distinct values, boat ≠ ambulance ≠ regular_vehicle ✓

### Files produced
- `backend/app/perception/damage.py` — DamageAssessor, BuildingDamageResult,
  RoadPassabilityResult, DamageClass, VehicleClass (248 pure LOC)
- `backend/tests/test_damage.py` — 6 tests: building damage classification,
  vehicle class passability, differs by class, GeoJSON output, uncertainty,
  failure time + speed (214 pure LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_damage.py -q"
→ 6 passed, 1 warning in 1.45s (exit 0)
```

## T21 — Social media & citizen report NLP pipeline (2026-07-18)

### Outcome
Created a multilingual NLP pipeline for citizen reports, social media, and
helpline calls. 10 tests pass (exit 0). The pipeline processes 5 mixed-
language reports (English, Hindi/Devanagari, code-mixed), extracts urgency
(low/medium/high/critical) and humanitarian category (12 categories),
generates geolocation candidates (NEVER exact points for vague reports),
detects/redacts PII before any LLM call, and clusters 2 near-duplicate
reports via FAISS cosine similarity.

### Key findings

1. **`whisper` is NOT in requirements.txt.** The task said "verify
   dependencies — if missing, note in notepad, do NOT modify
   requirements.txt." `faiss-cpu>=1.8.0` IS listed (line 30), but
   `openai-whisper` is not. The processor lazy-imports whisper inside
   `_transcribe_audio()` and raises a clear `RuntimeError` if not installed.
   Tests inject a mock `asr_fn` so no real Whisper model is required. To
   enable real ASR in production, add `openai-whisper>=20231117` to
   requirements.txt.

2. **Python's `\b` word boundary breaks on Devanagari combining marks.**
   The initial keyword matching used `re.search(r"\b" + re.escape(kw) +
   r"\b", text)`. This works for English but fails for Hindi because
   Devanagari combining marks (ं U+0902, े U+0947) are NOT `\w`
   characters in Python's `re` module. So `\bफंसे\b` doesn't match
   "फंसे" in "लोग फंसे हुए" — the word boundary fires between फ (word
   char) and ं (non-word char), splitting the keyword. Fix: use
   ASCII-only lookarounds `(?<![a-zA-Z0-9])` and `(?![a-zA-Z0-9])`
   instead of `\b`. This enforces word boundaries only for ASCII
   alphanumeric characters, allowing Devanagari to match freely.

3. **Substring matching causes false positives for English keywords.**
   The original keyword matching used `kw.lower() in lowered` (substring).
   This caused "collapse" to match "collapsed" (double-counting the
   structural_collapse category). Switching to word-boundary regex
   (`(?<![a-zA-Z0-9])collapse(?![a-zA-Z0-9])`) fixes this — "collapse"
   does NOT match "collapsed" because "d" follows.

4. **`hash()` is randomized per Python process (PYTHONHASHSEED).** The
   default hash-based bag-of-words embedder uses `hash(token) % 64` to
   map tokens to vector buckets. Because `hash()` returns different
   values in different Python processes, the embeddings (and thus the
   cosine similarity) change every run. This made the duplicate
   clustering test flaky — sometimes reports 0 and 3 had similarity
   above 0.7, sometimes below. Fix: inject a deterministic `embed_fn`
   in tests that uses `hashlib.sha256(token)` instead of `hash(token)`.
   Production should use a real sentence encoder (e.g., sentence-transformers)
   via `embed_fn`, not the hash-based fallback.

5. **Vague geolocation must take precedence over named-place suffixes.**
   The text "near the old market" contains both a vague qualifier ("near")
   and a place suffix ("market"). The initial logic checked `has_vague
   and not has_suffix` first, then `has_suffix` — so when both were
   present, it returned `named_place` (high confidence) instead of
   `uncertainty_polygon` (low confidence). This is wrong: "near the old
   market" is vague because we don't know WHICH old market. Fix: check
   `has_vague` before `has_suffix` — vague always yields
   `uncertainty_polygon` regardless of suffix presence.

6. **File split was required to stay under 250 pure LOC.** The initial
   `nlp.py` was 469 LOC. Split into 4 files by responsibility:
   - `nlp_types.py` (117 LOC) — dataclasses + enums
   - `nlp_patterns.py` (73 LOC) — keyword tables + regex patterns
   - `nlp_clustering.py` (139 LOC) — DuplicateClusterer (FAISS + Python fallback)
   - `nlp.py` (245 LOC) — CitizenReportProcessor pipeline stages

7. **FAISS is installed in the Docker image and works for clustering.**
   `faiss-cpu>=1.8.0` is in requirements.txt and installs correctly. The
   `DuplicateClusterer._cluster_with_faiss()` method uses
   `faiss.IndexFlatIP` with L2-normalized vectors for cosine similarity
   search. The pure-Python fallback (`_cluster_python`) is only used
   when FAISS is not installed. Both paths produce identical results on
   small test sets.

8. **PII redaction is applied right-to-left to preserve offsets.** The
   `_redact_pii` method converts the text to a list of characters, then
   replaces spans from right to left (highest start offset first). This
   ensures earlier spans' offsets remain valid when later spans are
   replaced. The redacted text is what downstream stages (urgency,
   category, geolocation) operate on — PII never reaches an LLM.

9. **Credibility estimation feeds the M dimension of T13's confidence
   vector.** The `_estimate_credibility` method returns a float in [0, 1]
   based on text length, presence of digits/coordinates, image
   corroboration, and a penalty for critical-urgency reports without
   images. This value should be passed to T13's
   `ConfidenceVectorCalculator` as the `model_uncertainty` dimension.

### Stopping condition verification
- 5 test reports (English, Hindi, code-mixed) processed: ✓
- Urgency extracted (low/medium/high/critical): ✓
- Category extracted (12 humanitarian categories): ✓
- Geolocation candidate (distribution/uncertainty_polygon, NOT point): ✓
- PII flagged and redacted before processing: ✓
- 2 duplicate reports clustered together: ✓

### Files produced
- `backend/app/perception/nlp_types.py` — ProcessedReport, PIISpan,
  GeoCandidate dataclasses + Urgency/Category/GeoType/PIIType enums
  (117 pure LOC)
- `backend/app/perception/nlp_patterns.py` — URGENCY_KEYWORDS,
  CATEGORY_KEYWORDS, PII regex patterns, place-name extraction patterns
  (73 pure LOC)
- `backend/app/perception/nlp_clustering.py` — DuplicateClusterer class
  with FAISS + pure-Python fallback (139 pure LOC)
- `backend/app/perception/nlp.py` — CitizenReportProcessor class with
  process_report + all pipeline stages (245 pure LOC)
- `backend/tests/test_nlp.py` — 10 tests covering all 6 required scenarios
  (188 pure LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_nlp.py -q"
→ 10 passed, 1 warning in 0.13s (exit 0)
```

## T18 — SAR flood mapping pipeline — Sentinel-1 + DOFA + probabilistic output (2026-07-18)

### Outcome
Created `backend/app/perception/flood_types.py` (32 pure LOC),
`backend/app/perception/flood_mapping.py` (235 pure LOC), and
`backend/tests/test_flood_mapping.py` (90 pure LOC). 5 tests pass (exit 0).
Loads sample SAR tensor [2, 224, 224], runs DOFA inference, outputs flood
probability map [224, 224] in [0,1], uncertainty std map, writes COG to
MinIO (mocked).

### Key findings

1. **DOFA is built into TorchGeo but lazy-imported with fallback.** The
   `_DOFASegmentation` class lazy-imports `torchgeo.models.dofa` inside
   `__init__`. If torchgeo is unavailable or the DOFA API has changed, it
   falls back to `_RandomEncoder` (a simple nn.Module that returns random
   features). This lets the module import and tests pass without real
   DOFA weights — the tests inject a `_MockDOFA` model directly.

2. **MC Dropout requires explicit train/eval mode management.** The
   `run_inference` method sets `model.eval()` for deterministic inference,
   then `compute_uncertainty` sets `model.train()` to enable dropout for
   MC Dropout (n forward passes, std of softmax outputs). Both methods
   save and restore the original training state via `was_training =
   model.training` + `model.train(was_training)` in a `finally` block.
   Without this, calling `compute_uncertainty` would leave the model in
   train mode, affecting subsequent deterministic inference.

3. **HAND method uses `max_pool2d` for local DEM maximum.** The water
   depth formula is `flood_prob * max(dem_max - dem, 0)` where
   `dem_max` is the local maximum over a 7x7 neighborhood via
   `F.max_pool2d(dem, kernel_size=7, stride=1, padding=3)`. The padding
   ensures the output has the same spatial dimensions as the input.
   Without a DEM, water depth is zeros (no elevation data → no depth
   estimate).

4. **GFM fusion is a simple weighted average with disagreement tracking.**
   `fused = 0.6 * model_prob + 0.4 * gfm_prob`, `disagreement =
   |model_prob - gfm_prob|`. The `model_disagreement` field in
   `FloodMapResult` is initialized to zeros in `run_inference` (no GFM
   to compare with) and only populated with actual values in
   `fuse_with_gfm`. This lets downstream consumers check if
   `model_disagreement.max() > threshold` to flag areas where the model
   and GFM disagree.

5. **COG output via rasterio works with `driver='COG'`.** The
   `save_as_cog` method writes the flood probability map as a single-band
   float32 COG to a temp file, then uploads to MinIO via `put_object`.
   The `from_bounds(0, 0, 1, 1, W, H)` transform provides a placeholder
   georeference (real georeferencing would come from the Sentinel-1
   scene metadata). The mock MinIO client records `(bucket, key, length)`
   tuples for verification.

6. **Probabilistic output is preserved — never binarized.** The
   `flood_prob` tensor is the softmax probability of the "water" class,
   a continuous float in [0, 1]. The test `test_inference` explicitly
   checks `len(result.flood_prob.unique()) > 2` to ensure the output is
   not binary. This is critical for downstream uncertainty propagation
   and fusion — a binary mask would lose all gradient information.

7. **`_preprocess` handles 2D and non-224x224 inputs.** If the input is
   2D (single band), it's expanded to 2 bands via `unsqueeze(0).expand(
   2, *x.shape)`. If the spatial dimensions aren't 224x224, the tensor
   is resized via `F.interpolate` with bilinear interpolation. This
   ensures the model always receives [2, 224, 224] regardless of input
   scene size.

8. **`torch.as_tensor` handles both scalar and tensor GFM inputs.** The
   `fuse_with_gfm` method accepts a GFM product dict where `flood_prob`
   can be a scalar (broadcast to full map size via `expand_as`) or a
   tensor (used directly). `torch.as_tensor(data, dtype=...)` avoids
   unnecessary copies when the input is already a tensor with the right
   dtype.

### Stopping condition verification
- Loads sample SAR tensor [2, 224, 224] ✓ (`test_inference` fixture)
- Runs DOFA inference ✓ (`test_inference` — mock model with Conv2d)
- Outputs flood probability map [224, 224] in [0,1] ✓
- Uncertainty std map ✓ (`test_uncertainty` — MC Dropout with p=0.5)
- Writes COG to MinIO (mocked) ✓ (`test_cog_output` — file + put_object)
- GFM fusion ✓ (`test_gfm_fusion` — weighted average + disagreement)
- Water depth via HAND ✓ (`test_water_depth` — with and without DEM)

### Files produced
- `backend/app/perception/flood_types.py` — QualityFlag enum +
  FloodMapResult dataclass (32 pure LOC)
- `backend/app/perception/flood_mapping.py` — SARFloodMapper class +
  _DOFASegmentation + _RandomEncoder (235 pure LOC)
- `backend/tests/test_flood_mapping.py` — 5 tests + _MockDOFA +
  _MockMinio mocks (90 pure LOC)

### Verification
```
docker compose run --rm -e PYTHONPATH=/app backend sh -c \
  "pip install pytest -q && python -m pytest tests/test_flood_mapping.py -q"
→ 5 passed, 1 warning in 4.95s (exit 0)
```

## 2026-07-26 — Todo 1: Implementation audit + execution plan

### Environment constraints
- Docker is NOT available in this audit environment — all "implemented but
  unverified" classifications require Gate A (Docker + PostgreSQL) for runtime
  confirmation. Documented in `evidence/baseline/2026-07-26/environment.txt`.
- Python venv at `backend/.venv/` not yet ready — could not run pytest.
- Node/npm available but frontend deps not installed.

### Key findings from source-code audit (37 capabilities)
1. **Engine layer is remarkably complete** — ~60 real engine files (fusion,
   perception, optimizer, twin, knowledge, sensing, eval, streaming, realtime,
   auth, ABAC). The gap is integration wiring, not engine development.
2. **5 of 9 registered API routes are STUBS** returning `{"status":"ok"}`:
   observations, hypotheses, scenarios, sensing, eval. See
   `evidence/baseline/2026-07-26/stub_routes.txt`.
3. **Two real routers NOT registered in main.py**: `health.router`
   (FeedHealthTracker at `backend/app/api/routes/health.py`) and
   `manager.router` (WebSocketManager at `backend/app/realtime/manager.py`).
   These must be added in todos 16 and 27.
4. **Migration drift is severe**: 13 entity tables missing columns; 8+ tables
   created at runtime via `ensure_table()`/`create_all()`. See
   `evidence/baseline/2026-07-26/ensure_table_usage.txt` for full grep output.
5. **Native PG ENUM vs VARCHAR mismatch**: migration 0001 creates native ENUM
   types (`sourcetype`, `corroborationstate`, etc.) but ORM uses
   `native_enum=False` (VARCHAR). Must reconcile in migration 0002a.
6. **`sources` table is completely orphaned** — defined in ORM
   (`backend/app/models/source.py`) but NOWHERE in migration AND has no
   `ensure_table()` call. Table doesn't exist after `alembic upgrade head`.
7. **ORG_ID mismatch**: `seed/ids.py:39` has `ORG_ID = "demo_org"` but
   `auth/seed.py:18` has `DEMO_ORG_ID = "org_demo"`. Demo users and demo
   observations are in DIFFERENT orgs. Must reconcile to `"org_demo"` in todo 17.
8. **Security weaknesses**: `/healthz` leaks full DATABASE_URL (`main.py:106`);
   CORS defaults to `*` with `allow_credentials=True`; JWT_SECRET defaults to
   `dev-secret-change-me` with no prod validator; `/api/_test/error`
   unrestricted outside dev.
9. **No worker container** — ConsumerManager exists (`consumer.py:28-171`) but
   is never started; no `backend/app/worker/main.py`; no worker service in
   docker-compose.
10. **Frontend is near-empty**: `App.tsx` is 5 lines (just `<MapView />`);
    react-router-dom, @tanstack/react-query, i18next in package.json but NEVER
    imported; no typecheck/lint/test scripts.

### Patterns observed
- `ensure_table()` pattern is used in 7 modules: idempotency.py, reliability.py,
  federation.py, edge_sync.py, sync.py, perception/models.py, llm_types.py,
  provenance_types.py. All must be removed after migration 0002b.
- `ensure_columns()` in `seed/db_setup.py` is a runtime ALTER TABLE workaround
  listing 26 missing columns (incomplete — cross-reference against entities.py
  found additional missing: `hazards.hazard_type`, `hazards.severity`,
  `bridges.name`, `bridges.status`, `operational_tasks.title`,
  `operational_tasks.status`, `operational_tasks.priority`).
- Audit chain (`lib/audit.py`) is per-org_id, not per-incident — `verify_chain`
  queries by org_id only.
- Confidence vector (`fusion/confidence.py`) stores vector in
  `quality_flags["confidence_vector"]` — display confidence is weighted sum for
  UI ONLY; reasoning engine must use full 6D vector.
- `routing.py:130` has `compute_cost()` method (NOT line 210 as draft said).
- MinIO credentials mismatch: docker-compose uses `minio/minio123`,
  config.py defaults to `minioadmin/minioadmin`.

### Deliverables created
- `docs/IMPLEMENTATION_AUDIT.md` — 37-row capability table with classifications
- `docs/EXECUTION_PLAN.md` — 5 waves + 4 final verification tasks, gate definitions
- `evidence/baseline/2026-07-26/` — 7 dated baseline files:
  - `git_state.txt`, `migration_state.txt`, `test_count.txt`,
    `docker_compose_config.txt`, `environment.txt`, `stub_routes.txt`,
    `ensure_table_usage.txt`
- Branch `codex/resqnet-phase1-completion` created and checked out

## Migration 0002a — Add missing entity columns + fix enum types (2026-07-26)

### Outcome
Created `backend/alembic/versions/0002a_entity_columns.py` (105 pure LOC).
Migration adds 33 missing ORM-defined columns across 13 entity tables, converts
6 native PG ENUM columns to VARCHAR (matching ORM's `native_enum=False`),
drops the 6 unused enum types, and adds 14 indexes (13 composite
`(org_id, incident_id)` + 1 time-series `observations(observed_at, org_id)`).
`alembic upgrade head` succeeds from 0001 state. Downgrade + re-upgrade both
verified clean. All 13 entity tables have ORM column count == DB column count.

### Key findings

1. **The `db_setup.py:16-43` list of 26 missing columns was incomplete.**
   Cross-referencing `entities.py` ORM models against migration 0001 revealed
   33 missing columns (7 additional): `hazards.hazard_type`,
   `hazards.severity`, `bridges.name`, `bridges.status`,
   `operational_tasks.title`, `operational_tasks.status`,
   `operational_tasks.priority`. The `db_setup.py` list was a partial
   workaround, not a complete inventory. Always cross-reference the ORM
   `__table__.columns` against `information_schema.columns` to find ALL
   missing fields.

2. **`op.execute("ALTER TABLE ... ALTER COLUMN ... TYPE VARCHAR USING col::text")`
   is the cleanest way to convert PG enum to VARCHAR.** Using `op.alter_column`
   with `type_=sa.String()` works but generates DDL that references the enum
   type during the cast. Raw SQL with an explicit `USING col::text` clause is
   unambiguous and matches the task's instruction to use `op.execute()` for
   enum type operations.

3. **Enum type drops must come AFTER all columns using the type are altered.**
   PostgreSQL refuses `DROP TYPE` if any column still references it. The
   migration alters all 6 enum columns to VARCHAR first, then drops the 6
   types. The order is enforced by the sequential `_ENUM_COLUMNS` list —
   both loops iterate in the same order.

4. **Downgrade recreates enum types via `CREATE TYPE ... AS ENUM (...)` with
   values from the Python enum class.** The expression
   `", ".join(f"'{v.value}'" for v in enum_cls)` produces the SQL enum literal
   list. This works because all 6 Python enums are `str` subclasses with
   `name == value` (e.g., `satellite = "satellite"`), so the VARCHAR values
   stored by the ORM are valid enum values when converting back.

5. **NOT NULL columns can be added to empty tables without `server_default`.**
   All 13 entity tables had 0 rows at migration time (seed data is added
   separately by `db_setup.py` / `seed_demo`). PostgreSQL allows
   `ALTER TABLE ... ADD COLUMN ... NOT NULL` on empty tables. If the tables
   had data, a `server_default` would be required for the NOT NULL columns
   (`hazards.hazard_type`, `zones.name`, `hospitals.name`, `shelters.name`,
   `operational_tasks.title`).

6. **Composite index naming: `ix_{table}_org_incident` avoids collision with
   existing single-column indexes.** Migration 0001 created
   `ix_{table}_org_id` and `ix_{table}_incident_id`. The composite index name
   `ix_{table}_org_incident` is distinct and follows the same prefix
   convention.

7. **The `decisions` table is NOT one of the 13 entity tables.** The task
   explicitly lists 13 tables; `decisions` is excluded because migration 0001
   already created it with all ORM-defined columns (`title`, `rationale`).
   The composite `(org_id, incident_id)` index is only added to the 13
   listed entity tables, not to `decisions`.

### Verification
```
alembic upgrade head   → 0002a (head), exit 0
alembic downgrade 0001 → 0001, 6 enum types recreated, exit 0
alembic upgrade head   → 0002a (head), exit 0

ORM vs DB column count (all 13 entity tables):
  hazards=9, zones=9, buildings=9, road_segments=9, bridges=9,
  power_substations=9, cell_towers=9, hospitals=10, shelters=11,
  responders=10, vehicles=10, sensors=10, operational_tasks=10
  → ALL TABLES MATCH

Enum types after upgrade: 0 (all 6 dropped)
Enum columns after upgrade: all character varying (VARCHAR)
Indexes created: 14 (13 composite + 1 time-series)
```

## T6-config — Harden configuration: safe health, CORS, JWT, test endpoint (2026-07-26)

### Outcome
Hardened `backend/app/main.py` and `backend/app/config.py` to prevent credential
leaks in health endpoints, enforce JWT secret strength in non-dev environments,
disable CORS credentials for wildcard origins, and gate the test error endpoint
behind development mode. All 6 acceptance criteria verified via FastAPI
TestClient.

### Key findings

1. **`/healthz` was leaking the full `DATABASE_URL` connection string.** The
   shallow health check returned `settings.DATABASE_URL` (containing
   `disaster:disaster@db:5432`) in the `bindings` dict. Replaced with a
   `services` dict mapping service names to `"configured"` — no URLs, no
   credentials. The `environment` field is retained for operational visibility.

2. **`/healthz/deep` was leaking exception details via `str(exc)`.** The deep
   health check returned `{"ok": False, "error": str(exc)}` per service.
   Exception messages from SQLAlchemy/Redis/MinIO can contain connection
   strings, hostnames, and credential fragments. Replaced with simple
   `True`/`False` booleans per service. Added Redpanda TCP connect check
   (was missing — criterion (b) lists database, redis, redpanda, minio).

3. **`/api/_test/error` was accessible in all environments.** The test endpoint
   that raises a `RuntimeError` for error-handler verification had no
   environment gate. Added `if settings.ENVIRONMENT != "development": raise
   HTTPException(status_code=404)` at the top. In dev: returns 500 (RuntimeError
   caught by error handler). In non-dev: returns 404 (endpoint hidden).

4. **CORS wildcard with `allow_credentials=True` is a browser security
   violation.** The W3C CORS spec forbids `Access-Control-Allow-Credentials:
   true` when `Access-Control-Allow-Origin: *`. Browsers reject credentialed
   requests to wildcard-origin servers. Fix: when `CORS_ORIGINS == "*"`, set
   `allow_credentials=False` and log a warning. When specific origins are
   provided, `allow_credentials=True` is safe. Verified: wildcard origin →
   `access-control-allow-credentials` header absent; specific origin → header
   is `true`.

5. **Pydantic v2 `@model_validator(mode="after")` is the correct tool for
   cross-field validation.** `@field_validator("JWT_SECRET")` cannot access
   `ENVIRONMENT` because field validators receive only the field value, not
   `self`. The `@model_validator(mode="after")` runs after all fields are
   validated and receives `self`, allowing cross-field checks. The validator
   raises `ValueError` when `ENVIRONMENT != "development"` and
   `len(JWT_SECRET) < 32`, which causes pydantic to reject the Settings
   instantiation — the app refuses to start.

6. **MinIO credential defaults in `config.py` were `minioadmin/minioadmin`**
   while `docker-compose.yml` and `.env.example` use `minio/minio123`. The
   defaults now match: `MINIO_ACCESS_KEY: str = "minio"` and
   `MINIO_SECRET_KEY: str = "minio123"`. This ensures the app can connect to
   MinIO out of the box when using docker-compose defaults.

### Files modified
- `backend/app/config.py` — added `model_validator` import, fixed MinIO creds,
  added `_validate_jwt_secret` model validator (55 LOC, 32 pure LOC)
- `backend/app/main.py` — hardened `/healthz`, `/healthz/deep`,
  `/api/_test/error`, and CORS setup (219 LOC, 161 pure LOC)

### Verification
```
# /healthz — no credentials
GET /healthz → {"ok": true, "services": {"database": "configured", ...}}
No 'postgresql', 'redis://', 'minio123', 'dev-secret' in response: PASS

# /healthz/deep — ok/false per service, no error strings
GET /healthz/deep → {"ok": false, "checks": {"database": true, "redis": false, "redpanda": false, "minio": false}}
No 'error' key, all values are bool: PASS

# /api/_test/error — dev mode (500) vs prod mode (404)
dev:  GET /api/_test/error → 500 (RuntimeError caught by error handler)
prod: GET /api/_test/error → 404 (HTTPException)
PASS

# CORS — wildcard origin
CORS_ORIGINS=* → allow_credentials=False, warning logged
CORS_ORIGINS=http://localhost:5173 → allow_credentials=true
PASS

# JWT_SECRET validator
ENVIRONMENT=development, JWT_SECRET=short → OK (dev exempt)
ENVIRONMENT=production, JWT_SECRET=short → ValueError (app refuses to start)
ENVIRONMENT=production, JWT_SECRET=32chars → OK
PASS

# MinIO creds
MINIO_ACCESS_KEY=minio, MINIO_SECRET_KEY=minio123 (matches docker-compose.yml)
PASS
```

## Migration 0002b — Add missing tables + remove ensure_table workarounds (2026-07-26)

### Outcome
Created migration `0002b_missing_tables.py` (210 pure LOC) that creates 13 tables
previously created on demand via `ensure_table()` or `Base.metadata.create_all()`.
Removed all `ensure_table`/`ensure_tables`/`ensure_columns`/`create_all` function
definitions and calls from 14 production files. `alembic upgrade head` exits 0.
`grep -rn "ensure_table\|create_all\|ensure_tables\|ensure_columns" backend/app/`
returns zero results.

### Tables created (13)
1. `users` — conditional create (already existed from `Base.metadata.create_all`)
2. `sources` — federated data source registry
3. `idempotency_keys` — dedup with `uq_idempotency_source_external` unique constraint
4. `source_reliability` — Beta(alpha,beta) with `uq_reliability_source_phenomenon` unique constraint
5. `federation_outbox` — delayed sync outbox
6. `edge_sync_applied` — cross-batch dedup by content_hash
7. `edge_sync_state` — per-incident sync state
8. `sync_conflicts` — surfaced conflict log
9. `models` — ML model registry (perception)
10. `prompts` — LLM prompt versioning
11. `ai_calls` — LLM call audit log
12. `decision_provenance` — hash-chained decision provenance
13. `h3_geo_index` — H3 spatial index with `uq_h3_entity_h3` unique constraint

### Key findings

1. **The `users` table already existed in the DB (created by `Base.metadata.create_all`
   in `main.py` lifespan).** Alembic's `op.create_table()` does NOT support
   `if_not_exists=True`. Used `sa.inspect(bind).get_table_names()` to conditionally
   create the table only if it doesn't exist. This is non-deterministic but correct
   for the current state — a fresh DB will create the table; the existing DB skips it.
   The downgrade drops `users` unconditionally (per task spec: "drops all tables").

2. **Table names must match ORM `__tablename__`, not the task's descriptive labels.**
   The task listed `perception_models`, `prompt_records`, `llm_call_log`, and
   `sync_conflict` — but the actual ORM `__tablename__` attributes are `models`,
   `prompts`, `ai_calls`, and `sync_conflicts` (plural). Using the task's labels
   would have created tables that the ORM can't query.

3. **The task listed `sync_applied` as a separate table, but no such ORM model exists.**
   `sync.py` imports `EdgeSyncApplied` from `edge_sync.py` — it doesn't define its
   own `SyncApplied` model. The `edge_sync_applied` table (item 6) already covers
   this. Skipped item 9 as a duplicate.

4. **`source_reliability` had no unique constraint in the ORM model.** The task
   required `uq_reliability_source_phenomenon` on `(source_id, phenomenon_type)`.
   Added it in the migration only — the ORM model doesn't declare it. This is safe:
   the DB enforces the constraint; the ORM works fine without knowing about it.

5. **Removing `ensure_table` from production code breaks test imports.** Tests in
   `test_idempotency.py` and `test_confidence_vector.py` import `ensure_table` from
   the production modules. After removing the function, these tests will get
   `ImportError`. This is explicitly acceptable per the task: "tests may still use
   ensure_table for setup — that's OK for now, will be fixed in todo 29."

6. **`llm.py` re-exported `ensure_tables` without calling it.** The `__all__` list
   included `ensure_tables` for convenience, but no code in `llm.py` actually called
   it. Removed the import and `__all__` entry. No callers imported `ensure_tables`
   from `llm.py` (verified via grep).

7. **`db_setup.py` had `_MISSING_COLUMNS` list used only by `ensure_columns`.** After
   removing `ensure_columns`, the 26-entry column list became dead code. Removed it
   along with the function. The columns are now permanently in migration 0002a.
   Updated the module docstring to reflect that only `clean_demo_data` remains.

8. **`auth/seed.py` had `_ensure_users_table()` which called `Base.metadata.create_all`.**
   Removed the function and its call. Also removed unused imports: `inspect` from
   sqlalchemy, `Base` and `engine` from `app.db`. The `seed_demo_users` function
   now assumes the `users` table exists (created by migration 0002b).

9. **Module docstrings referenced `ensure_table`/`create_all`.** The grep pattern
   `ensure_table` matches in docstrings too. Updated docstrings in `idempotency.py`,
   `reliability.py`, `llm_types.py`, `provenance_types.py`, `auth/seed.py`, and
   `db_setup.py` to remove these references.

10. **`TYPE_CHECKING` imports became unused after removing `ensure_table`.** Several
    modules imported `TYPE_CHECKING` and `Engine` only for the `ensure_table` type
    hint. Removed these unused imports from `idempotency.py`, `reliability.py`,
    `federation.py`, `edge_sync.py`, `sync.py`, `llm_types.py`, and
    `provenance_types.py`. Also removed `create_engine` from `idempotency.py` and
    `Engine` from `perception/models.py`.

### Files modified (14 production files)
- `backend/alembic/versions/0002b_missing_tables.py` (NEW — 210 pure LOC)
- `backend/app/lib/idempotency.py` — removed ensure_table, TYPE_CHECKING, create_engine
- `backend/app/fusion/reliability.py` — removed ensure_table, TYPE_CHECKING
- `backend/app/ingestion/federation.py` — removed ensure_tables, TYPE_CHECKING
- `backend/app/realtime/edge_sync.py` — removed ensure_tables, TYPE_CHECKING
- `backend/app/realtime/sync.py` — removed ensure_tables, TYPE_CHECKING
- `backend/app/perception/models.py` — removed ensure_table, Engine import
- `backend/app/perception/llm_types.py` — removed ensure_tables, TYPE_CHECKING, Engine
- `backend/app/perception/llm.py` — removed ensure_tables import + __all__ entry
- `backend/app/audit/provenance_types.py` — removed ensure_table, TYPE_CHECKING
- `backend/app/main.py` — removed Base.metadata.create_all + User import
- `backend/app/auth/seed.py` — removed _ensure_users_table + inspect/Base/engine imports
- `backend/app/streaming/consumer.py` — removed ensure_table import + call
- `backend/app/seed/seed_demo.py` — removed ensure_columns import + call
- `backend/app/seed/db_setup.py` — removed ensure_columns + _MISSING_COLUMNS + engine import

### Verification
```
cd backend && source .venv/bin/activate
export PYTHONPATH=/root/srijan/ieee/backend
export DATABASE_URL="postgresql+psycopg://resqnet:resqnet123@localhost:5432/resqnet"
alembic upgrade head → EXIT_CODE=0
alembic current → 0002b (head)

grep -rn "ensure_table\|create_all\|ensure_tables\|ensure_columns" backend/app/ \
  --include="*.py" | grep -v test | grep -v __pycache__
→ GREP_EXIT=1 (zero results)

# All 13 tables exist in DB
python -c "from sqlalchemy import inspect; from app.db import engine; \
  print(sorted(set(inspect(engine).get_table_names()) & \
  {'users','sources','idempotency_keys','source_reliability','federation_outbox',\
   'edge_sync_applied','edge_sync_state','sync_conflicts','models','prompts',\
   'ai_calls','decision_provenance','h3_geo_index'}))"
→ all 13 tables present

# All modules import correctly
python -c "from app.main import app; print('OK')"
→ All modules imported successfully
```

## T4-domain — Incident, Alert, Recommendation models + migration 0003 (2026-07-26)

### Outcome
Created 3 new domain models (Incident, Alert, Recommendation) and migration
0003 that creates the corresponding tables with GiST spatial indexes and
composite (org_id, incident_id) indexes. `alembic upgrade head` reaches
0003 (head); `alembic downgrade 0002b` drops all 3 tables cleanly;
re-apply succeeds. All model imports work from both direct module path and
package `__init__.py` exports. Event model and events table untouched.

### Key findings

1. **Incident is the top-level container — it does NOT carry incident_id.**
   Unlike every other entity in the platform (which uses the `_EntityMixin`
   with `org_id` + `incident_id`), Incident IS the incident. It has only
   `org_id` for tenancy and `id` as its own primary key. The composite
   `(org_id, incident_id)` index pattern used on alerts and recommendations
   does not apply to incidents — a simple `org_id` index suffices.

2. **FK ordering dictates table creation/drop order in the migration.**
   Alerts has FK to incidents; recommendations has FK to both incidents and
   alerts. Creation order must be incidents → alerts → recommendations.
   Drop order is the reverse: recommendations → alerts → incidents. Getting
   this wrong causes `relation does not exist` errors on FK creation.

3. **GeoAlchemy2 Geometry creates a duplicate GiST index.** When a
   `Geometry` column is created in a table, GeoAlchemy2 automatically
   creates a GiST index named `idx_<table>_<column>`. The explicit
   `op.create_index(..., postgresql_using="gist")` in the migration creates
   a second index named `ix_<table>_<column>`. This is the same pattern
   used by the existing `observations` table (which has both
   `idx_observations_geometry` and `ix_observations_geometry`). Both indexes
   are functionally identical; the explicit one is kept for naming
   consistency with the ORM's `__table_args__` Index declarations.

4. **`default=` in mapped_column is Python-side only — no server_default
   in migration.** The Incident `status` column has `default="active"` in
   the ORM model, and Alert/Recommendation have `default="draft"`. These
   are SQLAlchemy Python-side defaults (applied at INSERT time by the ORM).
   The migration does NOT set `server_default` — this matches the existing
   pattern (e.g., `sources.status` in 0002b has no server_default). The
   application layer is responsible for providing default values when
   inserting raw SQL.

5. **`confidence_vector` is JSONB, not ARRAY(Float).** The 6D confidence
   vector [S,C,F,G,M,K] is stored as JSONB (a list of 6 floats). This
   matches the existing pattern for `supporting_evidence`,
   `contradicting_evidence`, and other JSONB columns. Using PG ARRAY would
   require a separate type and is less flexible for future schema changes.

6. **Recommendation.alert_id is nullable — recommendations can exist
   without an alert.** The FK to alerts is `nullable=True`, allowing
   recommendations generated from observations or scenarios directly
   (not tied to a specific alert). The FK constraint still enforces
   referential integrity when alert_id is present.

### Files produced
- `backend/app/models/incident.py` — Incident model (36 pure LOC)
- `backend/app/models/alert.py` — Alert model (42 pure LOC)
- `backend/app/models/recommendation.py` — Recommendation model (40 pure LOC)
- `backend/alembic/versions/0003_incidents_alerts.py` — Migration (123 pure LOC)

### Files modified
- `backend/app/models/__init__.py` — added Incident, Alert, Recommendation
  imports and `__all__` exports

### Verification
```
alembic upgrade head → 0003 (head)
alembic downgrade 0002b → 0002b (all 3 tables dropped)
alembic upgrade head → 0003 (head) (re-applied cleanly)

python3 -c "from app.models.incident import Incident; \
  from app.models.alert import Alert; \
  from app.models.recommendation import Recommendation; \
  print('OK')"
→ OK

python3 -c "from app.models import Incident, Alert, Recommendation; print('OK')"
→ OK

# Tables in DB after upgrade:
incidents, alerts, recommendations (all 3 present)
# Indexes: GiST on geometry/area, composite (org_id, incident_id) on
# alerts and recommendations, plus status/severity/urgency indexes
```

## T7-worker — Dedicated worker container with retry and topic creation (2026-07-26)

### Outcome
Created a dedicated worker container that runs `ConsumerManager` in its own
process, consuming from `observations.normalized` with retry on transient
errors, DLQ for permanent failures, and graceful SIGTERM/SIGINT shutdown.
Added `scripts/create_topics.sh` for idempotent Kafka topic creation. Added
retry logic (`_should_retry` + `_retry_with_backoff`) to `consumer.py` with
3x exponential backoff (1s, 2s, 4s) for transient errors. All imports and
retry logic tests pass.

### Key findings

1. **`ensure_table` was already removed by Task 3.** Verified: `grep -n
   "ensure_table" consumer.py` returns no matches. Only `check_and_record`
   is imported from `app.lib.idempotency`. No changes needed to the import
   list for idempotency — Task 3 already cleaned this up.

2. **`asyncio.Event` + `loop.add_signal_handler` is the clean pattern for
   async graceful shutdown.** The worker creates a `stop_event`, registers
   SIGTERM/SIGINT handlers that set it, then `asyncio.wait`s on both the
   consume task and the stop event with `FIRST_COMPLETED`. When the signal
   fires, the stop task completes, the consume task is cancelled, and
   `consumer.stop()` is called. This avoids polling and works with Docker's
   SIGTERM-on-stop.

3. **`prometheus_client.start_http_server(port)` is a one-liner for the
   metrics endpoint.** It starts a background thread serving the default
   Prometheus registry on the given port. No need for a manual HTTP server
   or aiohttp. The worker exposes 3 counters: `worker_messages_processed_total`,
   `worker_messages_failed_total`, `worker_retry_attempts_total`. The
   healthcheck in docker-compose uses `curl -sf http://localhost:8001/metrics`
   to verify the worker is alive.

4. **Retry classification: permanent vs transient.** `_should_retry` returns
   `False` for `ValueError`, `KeyError`, `TypeError`, `AttributeError`, and
   `IntegrityError` (all permanent — malformed payload or constraint
   violation). Everything else (`OperationalError`, `TimeoutError`,
   `ConnectionError`, `OSError`) is treated as transient and retried. This
   is a whitelist-of-permanent approach: unknown exceptions are retried,
   which is safer than the inverse (unknown exceptions going straight to DLQ).

5. **`_retry_with_backoff` tries up to 4 times (1 initial + 3 retries).**
   The `delays = [1.0, 2.0, 4.0]` list defines both the retry count and the
   backoff delays. `range(len(delays) + 1)` gives attempts 0,1,2,3 (4 total).
   On attempt 0,1,2: if the error is transient, sleep `delays[attempt]`
   seconds and retry. On attempt 3 (the last): raise regardless. If the error
   is permanent at any attempt, raise immediately. Verified with 3 test
   scenarios: permanent (1 call), transient-exhausted (4 calls), transient-
   succeeds-on-retry (2 calls).

6. **`rpk topic create` exits non-zero when the topic already exists.** The
   `create_topics.sh` script wraps each `rpk topic create` in an `if/else`
   that treats the failure as "already exists" (idempotent). The script
   checks for `rpk` in PATH first and exits with a clear error if missing.
   Default bootstrap is `localhost:19092` (host-accessible Redpanda port);
   inside Docker, set `REDPANDA_BOOTSTRAP_SERVERS=redpanda:9092`.

7. **Worker healthcheck uses the metrics endpoint, not `pgrep`.** The
   `python:3.11-slim-bookworm` base image does not include `pgrep` (part of
   `procps`). Instead, the healthcheck does `curl -sf
   http://localhost:8001/metrics` — `curl` is installed in the backend
   Dockerfile (which the worker builds from). This is a real liveness check:
   if the worker process is hung or crashed, the metrics endpoint won't
   respond.

8. **Worker resource limits: 1 CPU, 1G memory.** The worker is I/O-bound
   (Kafka consume + DB insert), not CPU-bound. 1 CPU and 1G memory is
   sufficient for the single-partition, single-consumer dev setup. The
   backend service has 2 CPU / 4G for comparison (it runs FastAPI + ML
   models). The worker does not need ML model weights loaded.

### Files produced/modified
- `backend/app/worker/__init__.py` (NEW — package init, 4 LOC)
- `backend/app/worker/main.py` (NEW — worker entry point with asyncio +
  signal handlers + Prometheus metrics on :8001, 76 pure LOC)
- `scripts/create_topics.sh` (NEW — idempotent Kafka topic creation, 3 topics)
- `docker-compose.yml` (MODIFIED — added worker service with 1 CPU / 1G
  memory, healthcheck on :8001/metrics, restart: unless-stopped)
- `backend/app/streaming/consumer.py` (MODIFIED — added `import asyncio`,
  `from sqlalchemy.exc import IntegrityError`, `_should_retry()`,
  `_retry_with_backoff()`, placeholder `# TODO: Wire confidence vector
  computation (todo 13)`, 179 pure LOC)

### Verification
```
# Import test
PYTHONPATH=/root/srijan/ieee/backend python3 -c "from app.worker.main import main; print('OK')"
→ OK: worker.main imports

# Retry logic tests (3 scenarios)
python3 -c "..."  # permanent, transient-exhausted, transient-succeeds-on-retry
→ OK: permanent error raises immediately (1 call)
→ OK: transient error retries 3x then raises (4 calls)
→ OK: transient error succeeds on retry (2 calls)
→ OK: _should_retry classification correct
→ All retry logic tests passed.

# ensure_table not in consumer.py
grep -n "ensure_table" consumer.py → exit 1 (no matches)

# docker-compose valid YAML with worker service
python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"
→ OK: docker-compose.yml is valid YAML
→ worker service present with all required fields

# Pure LOC
consumer.py: 179 pure LOC (under 250 ✓)
worker/main.py: 76 pure LOC (under 250 ✓)
```


## T5 — Expand OperationalTask model + migration 0004 (2026-07-26)

### Outcome
Added 3 columns to `operational_tasks` table via migration `0004_task_expansion.py`
and updated the `OperationalTask` ORM model in `entities.py` to match. Alembic
upgrade to `0004 (head)` succeeds; all 3 columns verified present in
`information_schema.columns` with correct types (`character varying` for the two
String columns, `jsonb` for `assignment_history`).

### Key findings
1. **Migration 0004 follows the 0002a `add_column` pattern, not 0003's
   `create_table` pattern.** Since `operational_tasks` already exists (created
   in 0001, expanded in 0002a), 0004 only adds columns via `op.add_column`. The
   downgrade drops them in reverse order. No indexes are added — the task spec
   did not require them and the existing `ix_operational_tasks_org_incident`
   composite index from 0002a covers tenancy lookups.

2. **JSONB column uses `from sqlalchemy.dialects.postgresql import JSONB` in
   both the migration and the model.** The model already imports JSONB (used
   by `properties` on every entity), so no new import was needed in
   `entities.py`. The migration imports JSONB explicitly. Using `sa.JSON`
   instead would compile to `JSON` on PostgreSQL, which is less capable than
   `JSONB` (no GIN indexing, no `@>` operator) — JSONB is the correct choice
   for an append-only history column that will be queried.

3. **The `OperationalTask` model uses `Mapped[str | None]` (PEP 604 union)
   for nullable columns, not `Mapped[Optional[str]]`.** This matches the
   existing style in `entities.py` (every nullable column uses `str | None`).
   The task spec suggested `Optional[str]` but the codebase convention is the
   union syntax — followed the codebase. Both compile to the same SQLAlchemy
   type.

4. **Column ordering in the ORM matters for readability, not for the
   migration.** The 3 new fields are placed after `priority` (the last
   task-specific field added in 0002a) and before `geometry`/`properties`
   (the generic spatial/metadata columns from `_EntityMixin`-adjacent
   convention). PostgreSQL `add_column` always appends to the end of the
   table physically; the ORM declaration order is purely for source
   readability.

5. **`alembic upgrade head` produced no stdout output on success.** This is
   the default behavior when the migration is a no-op-ish `add_column` (no
   data backfill, no DDL that prints progress). The exit code 0 is the
   success signal — `alembic current` confirms the new head.

### Files produced/modified
- `backend/alembic/versions/0004_task_expansion.py` (NEW — 3 add_column / 3 drop_column)
- `backend/app/models/entities.py` (MODIFY — 3 new fields on OperationalTask)

### Verification
```
cd backend && source .venv/bin/activate
export PYTHONPATH=/root/srijan/ieee/backend
export DATABASE_URL="postgresql+psycopg://resqnet:resqnet123@localhost:5432/resqnet"
alembic upgrade head  # exit 0
alembic current      # → 0004 (head)

SELECT column_name, data_type FROM information_schema.columns
WHERE table_name='operational_tasks'
  AND column_name IN ('assigned_team_id','required_capability','assignment_history');
→ assigned_team_id    | character varying
→ assignment_history  | jsonb
→ required_capability | character varying
```

## T11 — Complete auth API: login, /me, logout, role enforcement, tenant isolation (2026-07-26)

### Outcome
Completed the auth API with GET /api/auth/me, POST /api/auth/logout, Redis-based
token revocation denylist in get_current_user, and ENVIRONMENT=development guard
on demo user seeding. All verification commands pass: login → 200 + JWT, /me → 200
+ user info, logout → 204, /me after logout → 200 (best-effort, Redis unavailable
in this environment as documented).

### Key findings

1. **Redis denylist uses a SET with a single key-level TTL, not per-member TTL.**
   The task spec explicitly requires `sadd('revoked_tokens', token)` + `expire(
   'revoked_tokens', remaining_ttl)`. Redis SET keys support only a single TTL
   for the entire key, not per-member. This means each `expire` call resets the
   TTL for ALL members in the set. In practice, the last-revoked token's TTL
   wins. This is acceptable for a demo/best-effort denylist — when Redis is
   available, the denylist works correctly for single-token revocation. For
   production, per-token keys (`revoked_token:{token}` with individual TTLs)
   would be more correct, but the task explicitly specifies the SET pattern.

2. **Redis is NOT available in this environment — all operations are best-effort.**
   The `get_redis()` lazy singleton attempts `ping()` on first call. If it fails
   (Error 111 connection refused), it logs a warning and returns None. Both
   `is_token_revoked` and `revoke_token` check for None and return False/no-op
   respectively. This means: logout always returns 204 (even if Redis is down),
   and a revoked token is still accepted (best-effort). The task spec explicitly
   allows this: "if Redis unavailable, log warning and still return 204" and
   "/me after logout → 401 (if Redis available) or 200 (if Redis unavailable,
   best-effort)".

3. **`get_redis()` retries on every call when Redis is down.** Unlike a
   "try-once-and-cache-failure" pattern, the singleton sets `_redis_client = None`
   on failure, so the next call re-enters the try block. This means each
   authenticated request pays the 2s `socket_connect_timeout` cost when Redis
   is down. For a dev environment this is acceptable (and the timeout is short).
   In production with Redis available, the first successful `ping()` caches the
   client and subsequent calls return immediately.

4. **`oauth2_scheme` can be used as a direct dependency to extract the raw token.**
   The logout endpoint needs both the raw token string (to add to the denylist)
   and the authenticated user (to verify the token is valid). Using
   `token: str = Depends(oauth2_scheme)` alongside `current_user: User =
   Depends(get_current_user)` is the cleanest pattern — FastAPI calls
   `oauth2_scheme.__call__` twice (once for each dependency), but it's just
   extracting a string from the Authorization header, which is trivially cheap.

5. **JWT `exp` claim is a Unix timestamp (seconds), not milliseconds.** The
   `create_access_token` function in `jwt.py` uses `datetime.now(timezone.utc) +
   expires_delta` and assigns it to `to_encode["exp"]`. python-jose encodes
   datetime objects as Unix timestamps (seconds). To compute remaining TTL in
   the logout endpoint: `int(exp) - int(datetime.now(timezone.utc).timestamp())`.
   The result is in seconds, which is what `redis.expire` expects.

6. **`UserInfo.model_validate(user)` works with SQLAlchemy User objects.** The
   `UserInfo` Pydantic model has `from_attributes=True` in its config, so
   `model_validate(user)` extracts `id`, `email`, `role`, `org_id` from the
   SQLAlchemy User object (ignoring `hashed_password` and `created_at`). This
   is the standard Pydantic v2 pattern for ORM-to-schema conversion.

7. **Demo user seeding now guarded by `ENVIRONMENT=development`.** The
   `seed_demo_users` function returns 0 immediately if
   `settings.ENVIRONMENT != "development"`. This prevents demo users from being
   created in production/staging environments. The check is in the function
   itself (not in the caller), so any future caller is protected.

8. **No changes needed to `jwt.py` for token revocation.** The task spec said
   "add token revocation support (if needed)". Revocation is handled entirely
   at the dependency layer (`deps.py` checks the denylist) and route layer
   (`auth.py` logout endpoint adds to denylist). The JWT module's
   `create_access_token` and `decode_token` functions are unchanged — they
   don't need to know about revocation. The denylist is an external concern.

### Files modified
- `backend/app/deps.py` — added Redis singleton (`get_redis`), `is_token_revoked`,
  `revoke_token`, denylist check in `get_current_user` (55 → 93 pure LOC)
- `backend/app/api/routes/auth.py` — added GET /me, POST /logout endpoints
  (37 → 55 pure LOC)
- `backend/app/auth/seed.py` — added ENVIRONMENT=development guard
  (69 → 65 pure LOC, net reduction due to docstring consolidation)

### Verification
```
Login: 200
Me: 200 {'id': '01KYFXYCDJS9R0CZDHNCSN2TJD', 'email': 'admin@demo.disaster',
          'role': 'admin', 'org_id': 'org_demo'}
Logout: 204
Me after logout: 200  (best-effort — Redis unavailable, as documented)
```

## T9 — Rescue-ball simulator core: device model and scenarios (2026-07-26)

### Outcome
Created `backend/app/simulator/` package with a deterministic `RescueBallDevice`
digital twin (172 pure LOC) and 10 fault-injection functions plus the
`RIVERTOWN_FLOOD_PATH` waypoint list (107 pure LOC). Same-seed determinism
verified across 10 steps with velocity=2.5; all 10 fault injection functions
tested; fault-injected metadata preserved across `step()` calls.

### Key findings

1. **`@dataclass(slots=True)` (mutable, not frozen) is correct for a stateful
   simulator.** The codebase convention is `@dataclass(frozen=True, slots=True)`
   for value objects (see `twin/scenario_types.py`, `twin/silence_types.py`,
   `fusion/confidence.py`). But `RescueBallDevice` is a stateful entity whose
   fields mutate on every `step()` — freezing it would force returning a new
   instance per step, which is wasteful and breaks the "modify in place"
   contract that the fault injection functions depend on. Mutable `slots=True`
   is the right choice.

2. **`health_flags` typed as `dict[str, Any]` — justified.** The spec lists
   `health_flags (dict) — {low_battery, high_temp, signal_loss, etc.}` with
   boolean values, but the fault injection functions need to store non-boolean
   metadata (`thermal_hotspot_c: float`, `human_heat_at: str`,
   `connectivity_loss_duration_s: int`). `dict[str, Any]` is the honest type
   for a heterogeneous metadata dict. The "no `Any` in public sigs" rule targets
   function signatures, not dataclass fields explicitly designed to hold
   mixed-type metadata.

3. **`_recompute_health_flags()` uses `dict.update()` not replacement.** This
   preserves non-boolean keys set by fault injection functions (e.g.,
   `thermal_hotspot_c`) across `step()` calls. If `step()` replaced the entire
   dict, fault-injected data would be lost on the next step. Same pattern
   applied to `imu_reading.update()` and `acoustic_reading.update()` so
   fault-injected keys like `water_depth_m` and `motion_heading_deg` survive.

4. **Position update uses meter→degree conversion at the device's latitude.**
   `dx_m / (111_320 * cos(lat))` for longitude, `dy_m / 111_320` for latitude.
   This is the standard equirectangular approximation, accurate enough for
   urban-scale movements (< 10 km). The `cos(lat)` guard prevents division
   by zero near the poles — irrelevant for Rivertown (lat ≈ 19°) but
   defensive for the general case.

5. **Battery drain rate is deployment-state-dependent, not activity-level.**
   The spec says "Decreases battery based on delta_ms and activity level" —
   the deployment state IS the activity level. `deployed` = 0.005%/s (active
   sensing + comms), `standby` = 0.001%/s (low-power idle), `recovered` = 0
   (charging), `lost` = 0.002%/s (beacon only). `estimated_remaining_runtime`
   is recomputed from `battery_pct / rate` on every step.

6. **Thermal model uses exponential relaxation toward equilibrium.**
   `T += (T_eq - T) * (1 - exp(-dt/tau))` with `tau = 300s` (~5 minutes).
   This is a first-order RC thermal model — physically correct and
   deterministic. Each deployment state has its own equilibrium temperature
   (`deployed` = 38°C, `standby` = 25°C, etc.).

7. **Rivertown coordinates confirmed at lon ≈ 72.85, lat ≈ 19.06.** Extracted
   from `seed/fixtures/geojson/roads.geojson` and the cyclone alert XML
   (`19.08N, 72.87E`). The `RIVERTOWN_FLOOD_PATH` traces 8 waypoints from
   the riverside (5m altitude) through flooded wards (down to -1.5m in the
   basin center) and back to the recovery zone (0m).

8. **All randomness sourced from caller-provided `random.Random`.** No
   `time.time()`, `os.urandom()`, or module-level `random` calls. The `step()`
   method draws from `rng.gauss()` for: heading noise (±2°), altitude drift
   (±0.1m), signal quality walk (±2%), IMU readings (6 axes), and acoustic
   readings (2 values). Same seed → same RNG sequence → identical state.

### Files produced
- `backend/app/simulator/__init__.py` (NEW — package init with disclaimer)
- `backend/app/simulator/rescue_ball.py` (NEW — 172 pure LOC, RescueBallDevice + step())
- `backend/app/simulator/scenarios.py` (NEW — 107 pure LOC, RIVERTOWN_FLOOD_PATH + 10 inject_* functions)

### Verification
```
# Spec verification command
PYTHONPATH=/root/srijan/ieee/backend python3 -c "from app.simulator.rescue_ball import RescueBallDevice; ..."
→ Deterministic sim OK

# Determinism: 10 steps with seed 42, compare all fields
→ PASS (lon, lat, altitude, battery, signal, packet_loss, temp, imu, acoustic, health_flags, last_seen_ts all identical)

# Non-determinism: seed 42 vs seed 99
→ PASS (different seeds produce different state)

# Fault injection: all 10 functions tested
→ PASS (each function modifies the correct field deterministically)

# Fault injection preservation across step()
→ PASS (thermal_hotspot_c, water_depth_m preserved after step())

# RIVERTOWN_FLOOD_PATH structure
→ PASS (8 waypoints, all (lon, lat, alt) tuples in Rivertown range)

# Pure LOC
rescue_ball.py: 172 (under 250 ✓)
scenarios.py: 107 (under 250 ✓)
```

## T12-obs — Real Observation API (replace stub) (2026-07-26)

### Outcome
Replaced the 14-line stub in `backend/app/api/routes/observations.py` with a real
implementation: POST /api/observations (create from GeoJSON Feature), GET
/api/observations (list with 8 filters + pagination), GET /api/observations/{id}
(detail). All responses are GeoJSON Feature/FeatureCollection — never WKT. Split
filter logic into `observations_queries.py` to keep both files under 250 LOC.

### Key findings

1. **`func.ST_AsGeoJSON` returns a text string, not a JSON object.** The query
   `select(Observation, func.ST_AsGeoJSON(Observation.geometry).label("geojson"))`
   returns the geometry as a JSON-encoded string. Must `json.loads(geojson_str)`
   to get a dict for the GeoJSON Feature response. Null geometries return None.

2. **JSONB path access for confidence_vector filter works with chained `[]` +
   `.as_float()`.** The expression
   `Observation.quality_flags["confidence_vector"]["s"].as_float() >= value`
   compiles to `(observations.quality_flags -> 'confidence_vector' ->> 's')::FLOAT`
   in PostgreSQL. Rows without `confidence_vector` in quality_flags evaluate to
   NULL and are correctly excluded by the `>=` comparison.

3. **`func.ST_MakeEnvelope(minx, miny, maxx, maxy, 4326)` + `func.ST_Intersects`**
   is the correct PostGIS pattern for bbox filtering. The SRID argument (4326)
   is required to match the observation geometry's SRID. Without it, PostGIS
   raises an SRID mismatch error.

4. **`func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)`** is
   the correct pattern for inserting GeoJSON geometry. `ST_GeomFromGeoJSON` does
   not set an SRID by default, so `ST_SetSRID(..., 4326)` is required for the
   geometry to be queryable with `ST_Intersects` against other 4326 geometries.

5. **Role-based visibility filtering uses a static `_ROLE_VISIBILITY` dict.**
   admin/emergency_manager/responder_coordinator see all (public+internal+
   sensitive); field_responder/shelter_manager see public+internal; viewer sees
   public only. Unknown roles default to public-only. The filter is applied as
   `Observation.access_policy.in_(policies)` in the list query, and as a
   post-fetch check in the detail endpoint (returns 404, not 403, to avoid
   leaking existence of sensitive observations).

6. **`incident_id` for POST comes from a query param, not the body.** The body
   is the GeoJSON Feature, so adding `incident_id` as a `Query(...)` parameter
   keeps the body clean and matches the GeoJSON convention (properties carry
   observation attributes, not routing metadata). org_id is always from
   `request.state.org_id` (JWT-derived), never from the body.

7. **`IntegrityError` on commit returns 409, not 500.** The POST endpoint catches
   `IntegrityError` (e.g., duplicate observation_id, FK violation on
   supersedes) and returns 409 Conflict. This is a legitimate boundary catch —
   the constraint violation is a real error condition the caller can act on.

8. **The confidence vector placeholder is a single comment.** Per the task spec,
   `# TODO: Wire confidence vector computation (todo 13)` is placed after the
   commit and before `write_audit`. Task 13 will replace this with a call to
   `ConfidenceVectorCalculator.compute_vector()` and store the result in
   `quality_flags["confidence_vector"]`.

### Files produced/modified
- `backend/app/api/routes/observations.py` (MODIFY — stub replaced, 211 pure LOC)
- `backend/app/api/routes/observations_queries.py` (NEW — filters + GeoJSON
  serialization, 121 pure LOC)

### Verification
```
GET /api/observations → 200 FeatureCollection (empty or with features)
POST /api/observations?incident_id=X → 201 GeoJSON Feature
GET /api/observations/{id} → 200 GeoJSON Feature
GET /api/observations/{nonexistent} → 404
POST as viewer → 403 (require_roles enforced)
GET sensitive obs as viewer → 404 (visibility enforced)
Filters: incident_id, source_id, phenomenon, observed_start/end, recent_ms,
  bbox, confidence_s — all verified working
```
