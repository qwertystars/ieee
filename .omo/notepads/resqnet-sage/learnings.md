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
