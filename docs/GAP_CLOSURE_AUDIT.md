# Gap-Closure Audit — ResQNet Phase 1 → Production Readiness

**Branch:** `codex/resqnet-gap-closure`
**Audit date:** 2026-07-27
**Auditor:** Sisyphus-Junior (autonomous)
**Baseline evidence:** `evidence/baseline/2026-07-27/`
**Prior audit:** `docs/IMPLEMENTATION_AUDIT.md` (2026-07-26)
**Parent commit:** `c6b9805` (merge: resqnet phase 1 completion)

## Methodology

This audit identifies the gaps between the Phase 1 completion state (commit
`c6b9805`) and a production-deployable system. Each gap is cited with
file:line evidence from the current source tree. Baseline evidence was
gathered on 2026-07-27 by running the actual test suites, migration
check, capabilities endpoint, and Docker availability checks — see
`evidence/baseline/2026-07-27/` for raw output.

Unlike the 2026-07-26 audit, Docker IS available in this environment
(v29.6.2 + Compose v5.3.1, confirmed via `docker run hello-world`).
This unblocks Gate A runtime verification for subsequent waves.

## Baseline evidence summary

| Check | Command | Result | Evidence file |
|---|---|---|---|
| Backend tests | `cd backend && .venv/bin/python -m pytest tests/ -q` | 491 passed, 8 warnings | `pytest_count.txt` |
| Frontend tests | `cd frontend && npm run test` | 45 passed (3 files) | `npm_test_count.txt` |
| Migration head | `cd backend && PYTHONPATH=. .venv/bin/alembic current` | 0004 (head) | `alembic_current.txt` |
| Capabilities | `curl -s http://localhost:8000/api/capabilities` | 6 features: 2 degraded, 4 unavailable, 0 available | `capabilities_snapshot.json` |
| No runtime DDL | `grep -rn "create_all\|ensure_table" backend/app/` | Zero results (exit 1) | `create_all_ensure_table_proof.txt` |
| Docker | `docker --version && docker compose version && docker run hello-world` | v29.6.2 + Compose v5.3.1 + hello-world OK | `docker_availability.txt` |

## Classification legend

| Classification | Meaning |
|----------------|---------|
| gap | Phase 1 delivered a simulation/placeholder; production requires real implementation |
| cleanup | Phase 1 code works but has a known defect or optimization debt |
| verified | Confirmed working at runtime in this audit |

## Capability table

| # | Gap | Phase 1 state | File:line evidence | Production requirement | Recommended action |
|---|-----|---------------|---------------------|----------------------|-------------------|
| 1 | Physical rescue-ball hardware | **gap** — digital twin only; no physical device, no hardware integration | `backend/app/simulator/rescue_ball.py:1-13` (docstring: "DIGITAL SIMULATION — physical rescue ball, mobility, communications, thermal accuracy, and landing mechanism have NOT been validated"); `:126` `heading_noise = rng.gauss(0.0, 2.0)` (synthetic position perturbation); `:133` `self.altitude += rng.gauss(0.0, 0.1)` (synthetic altitude random walk); `:151` `self.signal_quality + rng.gauss(0.0, 2.0)` (synthetic signal); `:169-174` IMU readings are `rng.gauss(0.0, 0.05)` around rest (synthetic); `:182-183` acoustic `db_level = 60.0 + rng.gauss(0.0, 2.0)` (synthetic) | Physical rescue-ball device with real sensors (IMU, acoustic, thermal, camera), real communications (LoRa/satellite), real power management | Procure/build physical device; create hardware abstraction layer; field-test in real flood scenario |
| 2 | Real sensor abstraction | **gap** — no SensorBase/SensorAdapter/SensorSource exists; all sensor data is synthetic from `rng.gauss()` | `grep -rn "SensorBase\|SensorAdapter\|SensorSource" backend/` → **zero results** (confirmed 2026-07-27); `rescue_ball.py:165-185` `_update_imu()` and `_update_acoustic()` generate synthetic readings from `random.Random` instead of reading real sensor hardware | Pluggable sensor abstraction: `SensorBase` protocol, `SensorAdapter` for hardware drivers, `SensorSource` registry for multi-source fusion | Design sensor abstraction layer; implement adapters for physical device sensors; wire to rescue-ball and ingestion pipeline |
| 3 | Production ML models | **gap** — model catalog defined but no weights downloaded; onnxruntime hard-imported at inference time | `backend/app/perception/serving.py:61-95` `MODEL_CATALOG` lists 3 models (sar-flood-mapping, building-damage, incident-nlp) with `source_url` pointing to `huggingface.co/resqnet/...` but no weights are cached locally; `:233-240` `_create_session()` does `import onnxruntime as ort` (hard import, not guarded) — if onnxruntime is not installed, inference crashes rather than degrading; capabilities endpoint reports `onnx_models: degraded` and `model_weights: unavailable` (see `capabilities_snapshot.json`) | Downloaded model weights cached in MinIO or local filesystem; onnxruntime installed; graceful degradation when weights missing | Run `scripts/download_models.py --download`; install onnxruntime in venv; add graceful fallback in `_create_session()` when onnxruntime missing |
| 4 | Offline-deployment assets | **gap** — offline prep script exists but PMTiles generation depends on external API; observability services behind `full` profile | `scripts/offline_prep.sh:44-70` `step_02_pmtiles()` calls Overpass API (`overpass-api.de/api/interpreter`) at `:59` — requires internet, defeating offline purpose; `:50-53` silently skips if `tippecanoe` not installed; `docker-compose.yml:108` `ollama: profiles: ["full"]`, `:244` `prometheus: profiles: ["full"]`, `:261` `grafana: profiles: ["full"]` — observability + LLM not started by default `docker compose up`; capabilities reports `pmtiles_basemap: unavailable` | Self-contained offline assets: PMTiles basemap pre-generated and bundled; all critical services start by default; no external API calls during offline operation | Pre-generate PMTiles and bundle in image; vendor tippecanoe or pre-build tiles in CI; move observability to default profile or document activation steps |
| 5 | Full-stack verification | **gap** — Gate E checkpoint never created; Playwright e2e deferred; F1-F4 final wave not started | `docs/FINAL_REPORT.md:433-435` "Docker is not available in this environment. Gates A, B, C, and D were verified through static analysis and local TestClient runs"; `:445-447` "Gate E requires all fusion, perception, twin, optimizer, sensing, privacy, ABAC, fairness, and eval tests to pass against PostgreSQL. The individual tests pass (included in the 491 backend tests), but the formal Gate E checkpoint evidence file (`evidence/gate-e/`) has not been created"; `:449-454` F1-F4 all "not started"; `evidence/gate-e/` directory does not exist | All gates (A-E) formally checkpointed with runtime evidence; Playwright e2e passing against running backend; F1-F4 final wave complete | Docker is now available — run `docker compose up -d --wait`, execute Gate A-E checkpoints, create `evidence/gate-e/`, run Playwright suite, execute F1-F4 |
| 6 | Production validation | **gap** — no load testing, backup, or disaster recovery scripts exist | `grep -rn "load_test\|backup_script\|disaster_recovery" .` → **zero results** (confirmed 2026-07-27); no `scripts/backup.sh`, no `scripts/load_test.py`, no `scripts/restore.sh` in the repository; `docs/FINAL_REPORT.md:431-454` lists deferred items but no production validation scripts were created | Load testing (k6/locust), automated backup (pg_dump + MinIO sync), disaster recovery runbook, restore testing | Create load test suite; add backup script with cron; write DR runbook; test restore procedure |
| 7 (cleanup) | Frontend chunk size | **cleanup** — single 1.87 MB JS chunk, no code-splitting | `frontend/vite.config.ts:1-11` — entire config is 11 lines with only `react()` plugin, `server` block, no `build.rollupOptions.output.manualChunks` configuration; `docs/FINAL_REPORT.md:456-458` "The production build produces a single 1.87 MB JS chunk (527 KB gzipped). This exceeds the 500 KB warning threshold." | Chunks under 500 KB; vendor code split from app code; route-level lazy loading | Add `build.rollupOptions.output.manualChunks` to `vite.config.ts`; implement route-level `React.lazy()` code-splitting |
| 8 (cleanup) | Outbox ULID race condition | **cleanup** — module-level mutable state in ULID generator causes race under concurrent access | `frontend/src/lib/outbox.ts:44-45` `let lastTs = 0` and `let lastRand: Uint8Array = new Uint8Array(10)` — module-level mutable state shared across all callers; `:56-75` `ulid()` function reads and writes `lastTs`/`lastRand` without synchronization — if two async calls interleave within the same millisecond, the increment logic at `:61-65` can produce duplicate or non-monotonic IDs; `docs/FINAL_REPORT.md:460-462` "The frontend test `src/lib/outbox.test.ts > ULID monotonicity > generates strictly increasing IDs within the same millisecond` occasionally fails when 20 ULIDs are generated within a single timestamp tick" | Thread-safe (or single-threaded-guaranteed) ULID generation; no module-level mutable state | Use a mutex/queue for ULID generation, or use `crypto.randomUUID()` + monotonic counter, or accept the flakiness and fix the test |

## Summary counts

| Classification | Count |
|----------------|-------|
| gap (production blocker) | 6 |
| cleanup (tech debt) | 2 |
| **Total** | **8** |

## Key findings

1. **Docker is now available** — v29.6.2 + Compose v5.3.1 confirmed via
   `docker run hello-world`. This unblocks all runtime verification that was
   deferred during the 2026-07-26 audit. Gate A can now proceed.

2. **Phase 1 cleanup is solid** — `grep -rn "create_all\|ensure_table"
   backend/app/` returns zero results, confirming all runtime DDL was
   removed and Alembic (head: 0004) is the sole schema authority.

3. **All 491 backend tests pass** — including fusion, perception, twin,
   optimizer, sensing, privacy, ABAC, fairness, and eval tests. The
   individual Gate E test components are green; only the formal checkpoint
   evidence file is missing.

4. **Capabilities endpoint reports 0 available features** — 2 degraded
   (onnx_models, kafka), 4 unavailable (ollama_llm, pmtiles_basemap,
   model_weights, redis). No feature is fully available in the current
   runtime. This is the core gap: the engine layer is complete but no
   production dependency is activated.

5. **No sensor abstraction exists** — `SensorBase`, `SensorAdapter`, and
   `SensorSource` return zero grep results across the entire backend. All
   sensor data is synthetic (`rng.gauss()` in `rescue_ball.py`). This is
   the fundamental gap between digital twin and real-world deployment.

6. **No production validation scripts exist** — `load_test`,
   `backup_script`, `disaster_recovery` return zero grep results. No load
   testing, backup, or DR infrastructure has been created.

7. **Offline prep depends on external API** — `offline_prep.sh:59` calls
   the Overpass API to fetch OSM data for PMTiles generation, which
   defeats the offline-first requirement if run at deploy time.

8. **Frontend has no build optimization** — `vite.config.ts` is 11 lines
   with no `manualChunks` configuration, producing a single 1.87 MB chunk.

## Wave 2 readiness

This audit establishes the baseline for Wave 2 gap-closure work. The
branch `codex/resqnet-gap-closure` is created from `main` head (`c6b9805`)
and contains only this audit document and baseline evidence. No
application code has been modified.

**Ready for Wave 2:** Docker available, tests green, migration head
confirmed, baseline evidence captured. All gaps cited with file:line
evidence for targeted closure.
