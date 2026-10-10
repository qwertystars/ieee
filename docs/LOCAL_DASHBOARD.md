# Local dashboard

Open http://localhost:5173/dashboard. All eight workspaces use the real local API.
The BLE mesh and thermal panels connect to separate services on ports 8001 and
8765; they wait for incoming phone/detection events when no hardware is sending.

This workstation uses Python 3.11 in `backend/.venv`, managed with uv, and an
isolated PostgreSQL/Redis runtime extracted under `/tmp/ieee-runtime`. The local
PostgreSQL version is 18.6 with PostGIS, AGE and h3. It is a development runtime,
not the production PostgreSQL 16/TimescaleDB stack.

To restart the prepared services:

```bash
backend/.venv/bin/python scripts/start_dashboard_local.py
```

It reuses running services and starts missing ones. Ctrl-C stops only the
processes it started. Logs are in `/tmp/ieee-runtime/logs`. The extracted runtime
and its database live in `/tmp`; preserve that directory if your system clears
it on restart. If it is missing, provision PostgreSQL/Redis with the repository's
Docker stack or recreate the extracted runtime before using this script.

The gitignored `backend/.env` points to PostgreSQL on 55432, Redis on 56379,
and sets `ENVIRONMENT=development`, `SIMULATOR_TRANSPORT=database`. This explicit
transport persists draft digital-twin observations through the canonical
idempotency, raw-event and audit contracts. Production requires Kafka transport.
Kafka, object storage and Ollama are not running in this local setup.

The gitignored `frontend/.env.local` contains:

```dotenv
VITE_LOCAL_DEMO_LOGIN=true
```

This flag is honored only by Vite's development server. It obtains a real JWT
for the seeded local admin and renews it as needed, so no login screen is needed.
Backend authorization and tenant checks remain active. Build artifacts do not
use this development login.

For a fresh database, run migrations and seed once after configuring the URLs:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed.seed_demo
```

Do not run backend pytest against the dashboard database: its fixtures rebuild
the schema. Use a separate test database and Redis logical database.

Real-service verification:

```bash
backend/.venv/bin/python scripts/check_dashboard_live.py
cd frontend
npm run test:dashboard-live
```

The API check starts/stops the simulator, injects faults and persists clearly
marked draft observations in the local scenario. The browser check opens every
workspace, checks mobile layouts and exercises simulator/device/audit controls
without request mocks. Evidence is written to `evidence/unified-dashboard/`.
Set `PLAYWRIGHT_EXECUTABLE_PATH` when using a preinstalled Chromium binary.

Physical drone flight, BLE model inference and thermal video analysis need their
hardware/model dependencies. The field services' ingestion paths are running;
empty feeds represent no received events, not generated example detections.
