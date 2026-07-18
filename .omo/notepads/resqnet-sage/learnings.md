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
