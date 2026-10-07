# Backend (FastAPI + aiokafka worker)

Canonical runtime: Python 3.11 FastAPI, **sync SQLAlchemy 2.x**, PostgreSQL 16
+ PostGIS/AGE/TimescaleDB/h3. Runs in Docker (`alembic upgrade head` + uvicorn
on start) or locally via `backend/.env` + venv.

## WHERE TO LOOK
| Task | Location |
|------|----------|
| Route registration | `app/main.py` — `api_router` built inline; no `api/router.py` |
| API routes (30 modules) | `app/api/routes/` — each exports `router`; helpers: `observations_queries.py`, `observations_validation.py`, `command_helpers.py`, `calibration_helpers.py` |
| Auth | `app/auth/` (jwt, roles, abac, passwords, command_authorization), `app/deps.py` (get_current_user, get_db, Redis revocation) |
| ORM models | `app/models/` — one file per table; mixins `TenancyMixin`/`TimestampMixin` in `models/__init__.py` |
| Canonical event contract | `app/models/events.py` — frozen `RawEvent`, RFC 8785 canonical bytes |
| ML serving | `app/perception/` — `serving_runtime.py` (ModelServing) + `serving_contracts.py`/`serving_execution.py`/`serving_storage.py`; manifest `data/models/manifests.json` |
| Worker | `app/worker/main.py` — `python -m app.worker.main`, aiokafka ConsumerManager |
| Realtime | `app/realtime/` — manager (WS router), fanout, sync, edge_sync, routes (polling fallback) |

## CONVENTIONS
- **Sync DB in routes**: `def` handlers + `Session = Depends(get_db)` run in the threadpool; never use sync DB calls inside `async def` (exception: `asyncio.to_thread`)
- **Canonical inference contracts**: models resolve to `available|abstain|unavailable|incompatible`; calibration DEFERRED_EXTERNAL ⇒ `abstain` — safety output abstains, never fakes
- Hash-chained audit via `lib/audit.py` + `lib/canonical_json.py`; write_audit on every state change
- Idempotency via `lib/idempotency.py` keyed `(org_id, source, external_id)`
- `*_types.py` split per domain module (fusion, optimizer, twin, sensing, eval, audit)
- Alembic migrations 0001–0012, forward-only; `downgrade()` raises for 0006+

## ANTI-PATTERNS
- No raw `dict[str, Any]` request bodies on new routes — use pydantic schemas
- No `type: ignore` unless pinned to a narrow code; mypy is gradual but gated in F2
- No `time.sleep` / blocking network calls in async paths (service_health, realtime, ingest)

## COMMANDS
```bash
cd backend && .venv/bin/python -m pytest tests/ -q   # full suite (needs docker stack up)
cd backend && .venv/bin/python -m app.worker.main     # worker
cd backend && .venv/bin/python -m app.seed.seed_demo  # reseed demo
```
