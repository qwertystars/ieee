---
slug: resqnet-gap-closure
status: review-approved
intent: clear
review_required: true
classification: architecture
pending-action: none (dual high-accuracy review approved; plan ready for execution)
plan_path: .omo/plans/resqnet-gap-closure.md
review_round_id: gap-closure-round-1
round_status: approved
plan_sha256: 00433c91fe1e1ac0bc8b1f2aa500baa4b739a7b003eb857ea0787ff70a88f0ca
review:
  momus:
    status: approved
    workspace_root: /root/srijan/ieee
    runtime_home: null
    target: .omo/plans/resqnet-gap-closure.md
    round_id: gap-closure-round-1
    plan_sha256: 00433c91fe1e1ac0bc8b1f2aa500baa4b739a7b003eb857ea0787ff70a88f0ca
    launch_id: momus-gap-closure-r1
    session: ses_05c7d0f5fffeDwAer4tTme0BBm
    verdict: OKAY — 1 moderate finding (T7 .onnx flat-placement vs capabilities flat os.listdir), folded in
  independent:
    status: approved
    workspace_root: /root/srijan/ieee
    runtime_home: null
    target: .omo/plans/resqnet-gap-closure.md
    round_id: gap-closure-round-1
    plan_sha256: 00433c91fe1e1ac0bc8b1f2aa500baa4b739a7b003eb857ea0787ff70a88f0ca
    launch_id: oracle-gap-closure-r1
    session: ses_05c7419eaffeiiuQwglt3y3Yb0
    verdict: OKAY — same 1 moderate finding (T7 path discrepancy), independently identified, folded in
fixes_applied:
  - "T7: corrected .onnx local placement from nested backend/data/models/models/*.onnx to FLAT backend/data/models/*.onnx + set ModelServing(cache_dir=backend/data/) so capabilities flat os.listdir finds them; added recursive-rglob alternative"
notes:
  - "Both reviewers independently identified the SAME single moderate finding (T7 .onnx placement) — high concordance. No critical findings. No CHANGES_REQUESTED. Plan is executable end-to-end."
  - "Note: plan_sha256 was computed by Momus reviewer on read (planner had no shell). The T7 fix changed the file post-review; the digest above reflects the pre-fix reviewed artifact. The fix is a tightening of acceptance criteria within an already-approved plan, not a structural change."
prior_plan: .omo/plans/resqnet-sage.md (Phase 1 — 39/41 todos done, gates A-D passed, Gate E + F1-F4 deferred for lack of Docker)
approach: |
  Phase-2 gap-closure plan. Phase 1 software is merged (491 backend tests, 45
  frontend tests, 5 migrations, 93 commits). Six gaps remain: (1) physical
  rescue-ball hardware, (2) real thermal/seismic sensing, (3) production ML
  models, (4) complete offline-deployment assets, (5) unambiguous full-stack
  verification + FINAL_REPORT reconciliation, (6) real-world production
  validation. Plus minor frontend cleanup (code-splitting + flaky ULID test).

  Three of the six gaps (1, 2, and the physical/organizational parts of 6)
  are fundamentally NOT software work a code-executing worker can perform
  (hardware procurement/manufacturing, physical floodwater testing, real
  sensor calibration against certified targets, multi-agency field-trial
  execution). The plan therefore splits each such gap into: (a) the
  software-readiness work a worker CAN execute (integration seams, ingestion
  adapters, calibration harnesses, test/observability scaffolding, honest
  documentation), and (b) an explicit, documented deferred milestone for the
  physical/organizational work that is out of software scope.

  The fully-software gaps (3-deploy side, 4, 5, 6-test side, cleanup) are
  planned to completion: install onnxruntime + deploy pre-trained ONNX
  weights + validate inference E2E; enable PMTiles/Ollama/Redpanda/Redis and
  verify offline boot; rerun the full Docker demo + Playwright e2e + create
  Gate E + F1-F4 evidence + reconcile FINAL_REPORT.md; add load/soak tests,
  backup/restore scripts, secrets hardening; fix frontend code-splitting
  and the ULID race.
---

# Draft: resqnet-gap-closure

## Components (topology ledger)

| id | outcome (one line) | status | evidence path |
|----|-------------------|--------|----------------|
| G1-hw-readiness | Software readiness for real hardware: a `SensorSource` protocol/ABC + a real-device ingestion adapter seam (serial/MQTT/SensorThings bridge) + calibration-data ingest pipeline; physical device build/procurement/floodwater testing explicitly documented as out-of-software-scope deferred milestone | active | `backend/app/simulator/rescue_ball.py` (100% synthetic RNG, lines 126,133,151,169-174,182-183), `backend/app/simulator/scenarios.py` (10 fault injections, all synthetic), NO `SensorBase`/`SensorAdapter`/`Protocol` exists, NO serial/MQTT/BLE/GPIO seam anywhere; `backend/app/ingestion/adapters/sensorthings.py:31` is the only real-sensor path (HTTP pull) |
| G2-sensor-readiness | Real thermal/seismic/vibration/acoustic sensing readiness: calibration-data schema + ingest + a calibration-validation harness; certified human-detection testing explicitly documented as deferred (physical, safety-critical, cannot be executed by a code worker) | active | `inject_thermal_hotspot`/`inject_human_heat_signature` (`scenarios.py:79-100`) write metadata flags only; `human_heat_at` is synthetic; `backend/app/fusion/calibration.py:39-80` ConformalCalibrator needs X/y arrays at `fit()` (no calibration-data files exist); disclaimers #3,#5 in `docs/KNOWN_LIMITATIONS.md:198-232` |
| G3-ml-deployment | Production ML deployment: install onnxruntime, fetch pre-trained ONNX weights from HF `resqnet` org, validate inference E2E for all 3 catalog models, build calibration-validation harness; real regional dataset sourcing/licensing + fine-tuning documented as deferred | active | `backend/app/perception/serving.py:61-95` MODEL_CATALOG (3 models, HF URLs, r2_key paths), `_create_session:233-240` hard `import onnxruntime`, `_get_model_bytes:211-231` local-cache-then-MinIO; `scripts/download_models.py:56-94` downloads to MinIO; `backend/app/fusion/calibration.py` needs fit() data; `docs/FINAL_REPORT.md:387-399` confirms onnxruntime uninstalled + no .onnx files |
| G4-offline-assets | Complete offline deployment assets: generate/obtain PMTiles basemap, enable Ollama+Redpanda+Redis in compose, verify offline boot + capabilities endpoint all-green | active | `scripts/offline_prep.sh` (12 steps, step_02_pmtiles:44-70 needs tippecanoe + Overpass, step_08_ollama:127-142), `docker-compose.yml` ollama/prometheus/grafana under `profiles:["full"]` (lines 108,244,261), `backend/app/api/routes/capabilities.py:207-214` checks onnx/ollama/pmtiles/weights/kafka/redis at runtime |
| G5-verification | Unambiguous full-stack verification: rerun complete Docker demo end-to-end, run Playwright e2e, create Gate E + F1-F4 evidence, reconcile FINAL_REPORT.md (currently says Docker runtime + Playwright deferred) | active | `docs/FINAL_REPORT.md:433-455` (Docker/Playwright/Gate E/F1-F4 all deferred — no Docker in prior env), `scripts/demo_phase1.sh` (9-step demo, notes simulator sync-route issue at line 110), `frontend/playwright.config.ts` (webServer starts frontend only, NOT backend), evidence dirs `evidence/gate-{a,b,c,d}/` exist, `evidence/gate-e/` MISSING |
| G6-prod-validation | Production-readiness validation (software-executable): load tests, soak/failure-injection tests, backup/restore scripts+verify, secrets hardening audit + secure secret management, regional-calibration validation harness, field-trial PROTOCOL doc; multi-agency field-trial EXECUTION + regional model validation on real data documented as deferred | active | NO locust/k6/pg_dump/load-test scripts exist (grep empty); `Makefile` has no load/backup targets; `backend/app/config.py` JWT_SECRET defaults `dev-secret-change-me`, `docker-compose.yml:164` hardcodes `JWT_SECRET` default; `docs/offline-prep.md` hardware spec (full 16CPU/32GB, reduced 8CPU/16GB); disclaimer #6 `docs/KNOWN_LIMITATIONS.md:234-246` |
| G7-frontend-cleanup | Minor cleanup: frontend code-splitting (manualChunks + React.lazy) to drop the 1.87MB single chunk below 500KB gzip warning; fix the flaky ULID monotonicity test (shared-state race in outbox.ts) | active | `frontend/vite.config.ts` (11 lines, NO build/manualChunks), `frontend/src/App.tsx:6-14` (9 static imports), `frontend/src/lib/outbox.ts:44-45,56-75` (lastTs/lastRand globals + unsynchronized increment loop), `frontend/src/lib/outbox.test.ts:272-282` (asserts lex-sort under Promise.all); `docs/FINAL_REPORT.md:255-262,456-462` |

## Findings (cited - path:lines)

### What Phase 1 actually delivered (verified)
- 5 Alembic migrations at head `0004` (`backend/alembic/versions/000{1,2a,2b,3,4}_*.py`)
- 491 backend tests pass (`docs/FINAL_REPORT.md:222`), 45 frontend tests pass (`docs/FINAL_REPORT.md:237`)
- Zero `create_all`/`ensure_table` in production code (`docs/FINAL_REPORT.md:276`)
- `GET /api/capabilities` checks onnx/ollama/pmtiles/weights/kafka/redis at REQUEST TIME, not hardcoded (`backend/app/api/routes/capabilities.py:207-239`)
- Rescue-ball simulator is 100% synthetic RNG, explicitly flagged `provenance_chain:{"simulated":True}` (`backend/app/simulator/engine.py:271`)

### Gap 1+2 — hardware & sensors are synthetic-only (confirmed by explore subagent)
- `backend/app/simulator/rescue_ball.py:126,133,151,169-174,182-183` — every numeric reading is `constant + rng.gauss()` or linear drain
- `backend/app/simulator/scenarios.py:34-133` — 10 fault-injection functions are in-place dict mutations, all `"""Deterministic."""`
- NO `SensorBase`/`SensorAdapter`/`Protocol` class anywhere; NO serial/MQTT/BLE/GPIO/pyserial/paho/bleak imports
- `backend/app/ingestion/adapters/sensorthings.py:31` SensorThingsClient is the ONLY real-sensor path (HTTP pull from remote SensorThings servers)
- `inject_thermal_hotspot`/`inject_human_heat_signature` (`scenarios.py:79-100`) write metadata flags only — not actual thermal readings
- Disclaimers #1-3 (`docs/KNOWN_LIMITATIONS.md:178-208`) already honestly state: no physical device, no deployment/landing validation, thermal NOT certified for human detection

### Gap 3 — ML layer is wired but unactivated
- `backend/app/perception/serving.py:61-95` — MODEL_CATALOG has 3 models with HF `resqnet` org source_urls + r2_key MinIO paths
- `serving.py:233-240` — `_create_session` does a hard `import onnxruntime` inside the method (RuntimeError if missing)
- `serving.py:211-231` — `_get_model_bytes` tries local `cache_dir` first, then MinIO (so `backend/data/models/` local path works)
- `scripts/download_models.py:56-94` — downloads each model from `source_url` to MinIO bucket `models`
- `backend/app/fusion/calibration.py:39-80` — ConformalCalibrator wraps MAPIE; `fit(X,y)` needs calibration arrays at runtime (no calibration-data files referenced)
- `docs/FINAL_REPORT.md:387-399` — onnxruntime NOT installed; no `.onnx` files in `backend/data/models/`

### Gap 4 — offline assets partially scripted but unrun
- `scripts/offline_prep.sh:44-70` — step_02_pmtiles needs `tippecanoe` + Overpass API (Rivertown is a placeholder name — Overpass may return nothing)
- `scripts/offline_prep.sh:127-142` — step_08_ollama starts ollama service + pulls `llama3.1:8b` (~4.7GB)
- `docker-compose.yml:108,244,261` — ollama/prometheus/grafana under `profiles:["full"]`; db/redis/redpanda/minio/benthos/backend/worker/frontend always-on
- `scripts/create_topics.sh` exists (creates observations.raw/.normalized/.dlq)
- Redpanda/Redis images NOT pre-pulled in current state (offline_prep step_04 needed)

### Gap 5 — verification deferred, report inconsistent
- `docs/FINAL_REPORT.md:433-455` — Docker runtime verification DEFERRED (no Docker in prior env); Playwright e2e DEFERRED; Gate E checkpoint NOT created; F1-F4 NOT started
- `scripts/demo_phase1.sh:110` — notes a pre-existing "sync route + asyncio.create_task" simulator issue
- `frontend/playwright.config.ts:21-26` — webServer auto-starts frontend preview ONLY, NOT the backend (e2e needs separate running backend at :8000)
- `evidence/gate-e/` directory MISSING; `evidence/gate-{a,b,c,d}/` exist

### Gap 6 — no production-validation tooling exists
- Grep for locust/k6/pg_dump/load/soak/backup: ZERO results in scripts/ or Makefile
- `Makefile:78-134` — no load-test, no backup, no soak target
- `backend/app/config.py` JWT_SECRET defaults `dev-secret-change-me`; `docker-compose.yml:164` `JWT_SECRET: ${JWT_SECRET:-dev-secret-change-me}`
- `docs/offline-prep.md:36-52` — hardware spec: full 16CPU/32GB/256GB, reduced 8CPU/16GB/128GB
- Disclaimer #6 (`docs/KNOWN_LIMITATIONS.md:234-246`) — demo performance ≠ disaster-zone performance

### Cleanup — frontend
- `frontend/vite.config.ts` (11 lines) — NO `build` key, NO `manualChunks`, NO `rollupOptions`
- `frontend/src/App.tsx:6-14` — 9 static imports (AuditPage, DashboardPage, DeviceDetailPage, FieldPage, HypothesesPage, LoginPage, NotFoundPage, PlanningPage, SimulationPage)
- `frontend/src/lib/outbox.ts:44-45` — `let lastTs`, `let lastRand` module-level mutable globals; `:56-75` `ulid()` increments without synchronization
- `frontend/src/lib/outbox.test.ts:272-282` — `Promise.all` of 20 `addToOutbox` calls asserts `ids === sorted` (race on shared globals)
- Build: 1.87MB single JS chunk / 527KB gzip (`docs/FINAL_REPORT.md:255-258`)

## Decisions (locked — user answered 2026-07-27)

| decision | locked value | rationale |
|----------|--------------|-----------|
| D1 Hardware & sensor scope | Software-readiness work (SensorSource protocol/ABC, real-device ingestion adapter seam, calibration-data ingest, calibration-validation harness, expanded simulator fidelity) PLUS a hardware procurement/manufacturing/deployment SPECIFICATION document (BOM, mechanical enclosure, comms, power, deployment/landing/recovery, battery, mobility) and a physical test-plan document — as SPECIFICATION documents only. Physical build/procurement/floodwater testing/certified human-detection calibration remain documented deferred milestones a worker cannot execute. | User chose "Also produce a hardware spec doc". Worker cannot build physical things, so the spec is a deliverable document, not executed work. |
| D2 ML weights & calibration data | Deploy pre-trained ONNX weights from HF `resqnet` org + install onnxruntime + validate inference E2E + calibration-validation harness; PLUS a task to source + license public real flood/damage datasets (candidates: xBD, Sen1Floods11, UNOSAT flood products, Copernicus EMS) and wire them into `ConformalCalibrator.fit()` for regional calibration. RISK: dataset availability/licensing not guaranteed — if blocked, fall back to fixture calibration and document the blocker. | User chose "Acquire datasets as a task". |
| D3 Load-test SLOs | 50 concurrent operators, 100 observations/sec sustained ingest, <2s p95 dashboard load, <500ms p95 API read, 99% request success over a 1-hour soak, failover/recovery <30s. Both full-stack (16CPU/32GB) and reduced (8CPU/16GB) profiles tested. | User chose "Adopt recommended SLOs". Derived from `docs/offline-prep.md:36-52`. |
| D4 Branch | `codex/resqnet-gap-closure` (Phase 1 was `codex/resqnet-phase1-completion`) | New phase, new branch; does not touch merged Phase 1 history. |
| D5 Review | High-accuracy dual review NOT auto-required (no "high accuracy" modifier in request); will OFFER at delivery per CLEAR path. | Skill routing: review_required=false. |
| D6 Demo region | Mumbai (the `RIVERTOWN_FLOOD_PATH` waypoints at lon≈72.85/lat≈19.07 in `backend/app/simulator/scenarios.py:22-31` are Mumbai coordinates; "Rivertown" is a fictional label). PMTiles basemap + OSM extract target Mumbai. | Discoverable fact — no user question needed. |
| D7 Test strategy | Tests-after for infra/verification todos; follow existing pytest (PostgreSQL/PostGIS) + vitest + Playwright patterns; agent-executed QA per todo (happy + failure, exact command + evidence path). | Matches Phase 1 conventions. |

## Scope IN
- Gap 1+2 software side: `SensorSource` protocol/ABC, real-device ingestion adapter seam (MQTT/serial/SensorThings bridge), calibration-data schema + ingest, calibration-validation harness, expanded simulator fidelity (real-physics kinematics option), honest hardware-gap milestone doc
- Gap 3: onnxruntime install, download_models.py execution, inference E2E validation for 3 catalog models, calibration-validation harness with fixture data, capabilities-endpoint green-check
- Gap 4: PMTiles generation/obtaining, Ollama/Redpanda/Redis enablement + offline-boot verification, capabilities all-green
- Gap 5: full Docker demo rerun, Playwright e2e (with backend auto-start), Gate E checkpoint + F1-F4 evidence, FINAL_REPORT.md reconciliation
- Gap 6 software side: locust/k6 load tests, soak + failure-injection tests, backup/restore scripts + verification, secrets hardening audit + secure secret management, field-trial PROTOCOL doc
- Cleanup: vite manualChunks + React.lazy route splitting, ULID race fix in outbox.ts

## Scope OUT (Must NOT have)
- Do NOT build, procure, or manufacture a physical rescue-ball device (out of software scope)
- Do NOT perform physical floodwater/deployment/landing/recovery testing (physical, cannot be executed by a code worker)
- Do NOT procure or physically calibrate real thermal/seismic sensors (physical procurement)
- Do NOT claim certified human-detection capability (safety-critical; physical certification required)
- Do NOT execute multi-agency field trials (organizational/physical)
- Do NOT acquire real regional flood/damage datasets without explicit user provision (licensing/owner decision)
- Do NOT fabricate model accuracy, trained weights, benchmark outcomes, or real-world rescue capability
- Do NOT weaken the existing graceful-degradation fallbacks (model_unavailable, Redis fail-open, Kafka noop producer, PMTiles vector fallback)
- Do NOT modify the merged Phase 1 commits/history
- Do NOT push to main

## Open questions
None. All 3 owner-decision forks answered (see Decisions table D1-D3). Clearance check: objective defined ✓, scope IN/OUT explicit ✓, approach decided ✓, test strategy confirmed ✓, no blocking ambiguity ✓.

## Approval gate
status: awaiting-approval
approach: 6 gate-ordered waves (~23 implementation todos + F1-F4 final verification): (1) foundation + frontend cleanup, (2) offline-deployment assets, (3) ML deployment + real-dataset calibration, (4) hardware/sensor software-readiness + hardware spec docs, (5) full-stack verification + FINAL_REPORT reconciliation, (6) production-validation (load/soak/backup/secrets + field-trial protocol doc). Physical build/procurement/floodwater testing/field-trial execution remain documented deferred milestones.
next-action: user explicit okay → write .omo/plans/resqnet-gap-closure.md → mandatory Metis gap analysis → append todos → fill TL;DR last → offer high-accuracy review at delivery.
