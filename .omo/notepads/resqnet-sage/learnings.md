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
