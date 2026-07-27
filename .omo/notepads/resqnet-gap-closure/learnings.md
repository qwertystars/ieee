# Learnings — resqnet-gap-closure

Conventions, patterns, and successful approaches discovered during work on this plan.

_Auto-scaffolded by /start-work. Append new entries below - never overwrite._

---

## 2026-07-27 — Wave 1, Todo 1: Gap-closure audit + baseline evidence

### Environment discoveries

- **Docker IS available** in this environment: v29.6.2 + Compose v5.3.1.
  `docker run hello-world` succeeds. This unblocks Gate A runtime
  verification that was deferred during the 2026-07-26 audit.
- **PostgreSQL 15 is running locally** on localhost:5432 with database
  `resqnet`, user `resqnet`, password `resqnet123`. Migration head is
  `0004`. The backend connects successfully and serves `/healthz` and
  `/api/capabilities`.
- **Alembic requires PYTHONPATH=.** — `cd backend && .venv/bin/alembic
  current` fails with `ModuleNotFoundError: No module named 'app'` because
  `alembic/env.py` imports `app.config` and the venv doesn't have the app
  package installed. Fix: `PYTHONPATH=. .venv/bin/alembic current`.
- **Backend can be started locally** via `cd backend && PYTHONPATH=.
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`. Use tmux
  or `setsid` to keep it running across bash tool timeouts.

### Baseline evidence (2026-07-27)

- Backend tests: **491 passed**, 8 warnings, 64.53s
- Frontend tests: **45 passed** (3 files), 3.57s
- Migration head: **0004**
- Capabilities: 6 features, 0 available, 2 degraded, 4 unavailable
- `create_all`/`ensure_table` grep: **zero results** (Phase 1 cleanup confirmed)
- Docker: **v29.6.2 + Compose v5.3.1**, hello-world OK

### Key audit findings

1. **No sensor abstraction exists** — `SensorBase`, `SensorAdapter`,
   `SensorSource` all return zero grep results. All sensor data is
   synthetic via `rng.gauss()` in `rescue_ball.py`.
2. **No production validation scripts** — `load_test`, `backup_script`,
   `disaster_recovery` all return zero grep results.
3. **Capabilities endpoint reports 0 fully-available features** — the
   engine layer is complete but no production dependency is activated.
4. **Offline prep depends on external API** — `offline_prep.sh:59` calls
   Overpass API for PMTiles generation, defeating offline-first.
5. **Frontend has no build optimization** — `vite.config.ts` is 11 lines,
   no `manualChunks`, single 1.87 MB chunk.
6. **Outbox ULID race** — `outbox.ts:44-45` module-level mutable state
   (`lastTs`, `lastRand`) causes flaky monotonicity test under concurrency.

### Approach notes

- Branch `codex/resqnet-gap-closure` created from `main` head `c6b9805`.
- Evidence stored in `evidence/baseline/2026-07-27/` (6 files, dated).
- Prior `evidence/baseline/2026-07-26/` left untouched.
- Audit doc at `docs/GAP_CLOSURE_AUDIT.md` mirrors the IMPLEMENTATION_AUDIT.md
  pattern but focuses on production-readiness gaps rather than implementation
  completeness.

