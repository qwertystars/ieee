---
slug: resqnet-remaining-work
status: awaiting-approval
intent: clear
review_required: false
pending-action: write .omo/plans/resqnet-remaining-work.md after user approval
approach: 8-item gap-closure plan ordered by user priority. Items 1-2,4-7 are fully software-executable with concrete file references and fixes. Item 3 uses publicly available pre-trained models (user decision). Item 8 is fundamentally not software — plan updates deferred milestone docs only. 42 implementation todos + 4 final verification tasks across 7 waves.
---

# Draft: resqnet-remaining-work

## Components (topology ledger)

| id | outcome | status | evidence |
|----|---------|--------|----------|
| C1-tests | All automated tests pass (backend 0 failures, Playwright 21/21) | active | `backend/.pytest_cache/v/cache/lastfailed`, `frontend/tests/e2e.spec.ts:122-131` |
| C2-ml-gating | Placeholder models reported as degraded; manifests required; placeholder outputs blocked from alerts | active | `backend/app/api/routes/capabilities.py:60-85,134-148`, `backend/app/perception/serving.py:61-95` |
| C3-real-models | Real pre-trained ONNX models replace placeholders (3 public models) | active | `backend/data/models/` (3 stub files 137-200 bytes), HF model research complete |
| C4-ingest-perf | Ingestion sustains 100 obs/sec (currently 6.32) | active | `tests/load/locustfile.py`, `backend/app/api/routes/observations.py:139-141`, `backend/app/streaming/consumer.py:131-132` |
| C5-reliability | 1-hour soak + chaos tests with measured failover | active | `tests/load/locustfile.py:25-27`, `tests/load/combine_report.py:29-46,115-119` |
| C6-frontend-lint | Zero ESLint/TS warnings (4 current) | active | `frontend/eslint.config.js:76-82`, 4 violations identified |
| C7-auth-hardening | Hybrid fail-closed (admin) / fail-open (ops) + short-lived tokens + local revocation cache | active | `backend/app/deps.py:45,50`, `backend/app/config.py:36` (720min TTL!) |
| C8-field-validation | Real devices + physical tests + multi-agency trial | deferred (NOT software) | `docs/HARDWARE_SPECIFICATION.md`, `docs/PHYSICAL_TEST_PLAN.md`, `docs/FIELD_TRIAL_PROTOCOL.md` |

## Open assumptions (announced defaults)

| assumption | adopted default | rationale | reversible? |
|------------|-----------------|-----------|-------------|
| Docker resource limits for 100 obs/sec | Increase backend to 2 CPU / 4G RAM, worker to 1 CPU / 1G RAM, db to 2 CPU / 2G RAM | Current 1 CPU / 2G is likely the primary bottleneck for 6.32→100 obs/sec | Yes — docker-compose.yml |
| Access token TTL | 15 minutes (from current 720 minutes) | Standard short-lived access token + refresh token pattern; 720min (12h) is far too long | Yes — config.py |
| Local emergency revocation cache | In-memory Set with TTL matching token TTL, flushed on restart | Simplest durable-enough approach; survives Redis outage but not process restart | Yes |
| Soak test execution duration | 1 hour as user requires | User explicitly says "genuine one-hour soak test" — no CI shortcut | N/A — user requirement |
| Kafka partitions for ingest throughput | Increase from 1 to 6 partitions for observations.raw | 6 partitions allows 6 parallel consumer workers | Yes — create_topics.sh |
| Frontend clock hook | `useClock()` hook returning timestamp via state + interval | Eliminates both `Date.now()` purity warnings and set-state-in-effect warnings | Yes |
| Branch | `codex/resqnet-remaining-work` from current head | Follows repo convention of per-work branches | Yes |
| SAR flood model | Governor6191/sar-flood-extent-unet-resnet34 (HF, U-Net+ResNet34, Sen1Floods11, IoU 0.67) | Best available public model trained on the same dataset already downloaded for calibration | Yes |
| Building damage model | xView2 1st place solution weights (S3 public URL) | Highest-quality public building damage model; needs PyTorch→ONNX export | Yes |
| NLP model | sakibalfahim/CrisisPulse (HF, BERT, Apache-2.0, binary disaster classification) | Simplest public model that maps to incident-nlp task; needs fine-tuning for multi-class | Yes |
| Refresh token TTL | 7 days | Standard refresh token lifetime; allows re-issuance without re-login for active operators | Yes |

## Findings (cited - path:lines)

### C1 — Failing tests
- **Playwright**: `frontend/tests/e2e.spec.ts:128-130` — `.or()` locator unions "Situation Report" + "Alerts" h2 headings, both visible, strict mode violation (2 elements). Fix: replace `.or()` with `.first()`.
- **6 backend failures** (`backend/.pytest_cache/v/cache/lastfailed`):
  1. `test_capabilities.py::test_capabilities_does_not_crash_when_deps_down` — asserts redis/kafka unavailable, but Docker has them running
  2. `test_low_connectivity.py::test_get_redis_returns_none_when_unavailable` — asserts get_redis()=None, but Redis is running
  3. `test_low_connectivity.py::test_deep_health_check_reports_redis_and_redpanda_down` — asserts redis=False, but it's True
  4-6. `test_sota_routes.py` — three ML degradation tests fail due to TestClient(app) lifespan startup timing with Kafka/Redis
- **Root cause for 1-3**: Tests hardcode "deps are down" assertions but don't check actual service state. Need adaptive assertions or service-state detection.
- **Root cause for 4-6**: TestClient(app) lifespan triggers Kafka producer init + Redis connection; timing issues cause startup to hang/timeout.

### C2 — Placeholder ML model gating
- `capabilities.py:134-148` — `_check_model_weights()` reports `available` if ANY `.onnx` file exists, regardless of content
- `capabilities.py:60-85` — `_check_onnx_models()` same pattern
- `serving.py:61-95` — MODEL_CATALOG has hardcoded `calibration_metrics` but no manifest with checksum, training dataset, validation status
- Placeholder files: 168, 137, 200 bytes — all <1KB, trivial ops
- No manifest files exist

### C3 — Real ML models (public pre-trained, user decision D5)
- **SAR flood mapping**: `Governor6191/sar-flood-extent-unet-resnet34` on HuggingFace
  - U-Net + ResNet34, trained on Sen1Floods11 (same dataset already downloaded)
  - Input: (2, 512, 512) VV+VH standardized
  - Output: 2-class pixel logits (dry/water)
  - Test IoU 0.67, F1 0.80
  - PyTorch checkpoint → needs ONNX export via `torch.onnx.export()`
  - Requires `torch`, `segmentation_models_pytorch` installed
- **Building damage**: `DIUx-xView/xView2_first_place` (1st place xView2)
  - Weights at `https://vdurnov.s3.amazonaws.com/xview2_1st_weights.zip` (public S3)
  - Multi-model ensemble (localization + classification)
  - PyTorch → needs ONNX export
  - Requires `torch`, `torchvision`, `opencv-python`
  - Alternative: `DIUx-xView/xView2_baseline` (simpler, baseline weights on GitHub releases)
- **NLP**: `sakibalfahim/CrisisPulse` on HuggingFace
  - BERT fine-tuned on disaster tweets, Apache-2.0 license
  - Binary: 0=Not Disaster, 1=Disaster
  - Needs multi-class extension or replacement with CrisisTransformers for incident type classification
  - Alternative: `crisistransformers/CT-M2-Complete` (RoBERTa, 15B crisis tokens, needs fine-tuning)
  - PyTorch → needs ONNX export via `torch.onnx.export()`
- **Heavy deps needed**: torch, segmentation_models_pytorch, torchvision, transformers, opencv-python-headless
- **ONNX export**: All three can be exported via `torch.onnx.export()` on CPU (no GPU needed for export)
- **CPU inference**: All three can run inference on CPU with onnxruntime (slower but functional)

### C4 — Ingestion performance (6.32 → 100 obs/sec)
- `observations.py:139-141` — single `db.add(obs)` + `db.commit()` per observation (no batching)
- `consumer.py:131-132` — same single-row insert pattern in Kafka consumer
- `producer.py:45` — `send_and_wait()` per message (synchronous, no batching)
- `docker-compose.yml:183-185` — backend 1 CPU / 2G RAM (bottleneck)
- `docker-compose.yml:221-223` — worker 0.5 CPU / 512M RAM
- `create_topics.sh:24` — `TOPIC_PARTITIONS=1` (single partition, no parallelism)
- `locustfile.py:300-324` — IngestUser: 50 users, constant(0.1) wait, 1 POST per user per 0.1s = ~500 POSTs/sec theoretical, but DB is bottleneck
- No `bulk_insert`, `add_all`, `executemany`, or batch patterns exist anywhere in backend/app/
- **Bottleneck analysis**: Single-row commit per observation = 1 DB round-trip per obs. At 6.32 obs/sec, each insert takes ~158ms (includes commit + confidence vector + hypothesis update + audit write). Need to: (a) batch inserts, (b) move confidence/hypothesis/audit to async, (c) increase partitions for parallel consumption, (d) increase CPU/memory limits

### C5 — Reliability testing
- `locustfile.py:25-27` — SOAK_DURATION configurable, defaults 600s
- `combine_report.py:29-46` — failover read from `evidence/chaos/*.json`, hardcoded `recovered_within_30s=true` → 30.0
- `combine_report.py:115-119` — "precise measurement is in the chaos test evidence" but no actual precise measurement exists
- Previous load test ran ~60s instead of configured 600s (user reports)
- No overlapping failure tests, disk pressure tests, or intermittent network loss tests
- Need: genuine 1h soak, actual measured failover times (not hardcoded 30s), overlapping failures, container restarts, disk pressure, intermittent network loss

### C6 — Frontend lint warnings (4 total)
- `frontend/eslint.config.js:76-82` — `react-hooks/purity: 'warn'`, `react-hooks/set-state-in-effect: 'warn'`
- Warning 1 (purity): `frontend/src/components/MapView.tsx:127` — `useState(Date.now())` → fix: `useState(() => Date.now())` or use `useClock()` hook
- Warning 2 (purity): `frontend/src/components/state/StaleState.tsx:13` — `Date.now()` in render → fix: use `useClock()` hook
- Warning 3 (set-state-in-effect): `frontend/src/auth/AuthContext.tsx:27-48` — `setLoading`/`setUser` in useEffect → fix: derive state or use query
- Warning 4 (set-state-in-effect): `frontend/src/hooks/useOutbox.ts:90-105` — `refreshCount()` (calls setPendingCount) in useEffect → fix: use query or derived state

### C7 — Auth hardening (user decision D6: hybrid)
- `backend/app/deps.py:45` — `if client is None: return False` — fail-open
- `backend/app/deps.py:50` — `except Exception: return False` — fail-open
- `backend/app/config.py:36` — `ACCESS_TOKEN_EXPIRE_MINUTES: int = 720` (12 HOURS — far too long)
- `backend/app/auth/jwt.py:16` — `create_access_token(data, expires_delta)` — TTL from caller
- `backend/app/api/routes/auth.py:47-67` — logout calls `revoke_token()` (best-effort)
- `backend/app/auth/abac.py:99-142` — `grant_emergency_override()` requires admin
- Sensitive operations: alert approval (`alerts.py:132-178`), emergency override (`abac.py:99-142`), admin changes (various)
- `backend/app/lib/audit.py` — hash-chained audit log
- **User decision D6**: Hybrid — fail-closed for admin changes, fail-open for operational actions (alert approval, emergency overrides), with audit logging for all Redis-unavailable actions

### C8 — Field validation (deferred — NOT software)
- `docs/HARDWARE_SPECIFICATION.md` — 845 lines, 8 subsystems, spec only
- `docs/PHYSICAL_TEST_PLAN.md` — 668 lines, 5 protocols, deferred
- `docs/FIELD_TRIAL_PROTOCOL.md` — 643 lines, 6 sections, deferred
- All explicitly state "NOT EXECUTED", "DEFERRED MILESTONE"
- `backend/app/sensing/sensor_source.py` — SensorSource protocol exists
- `backend/app/sensing/adapters/mqtt_sensor.py` — MQTT adapter exists
- Software-readiness complete; remaining work is purely physical

## Decisions (with rationale)

| decision | rationale |
|----------|-----------|
| D1: Item 8 is deferred (not software) | All 6 sub-tasks require physical hardware, sensors, certified equipment, IRB approval, multi-agency coordination. Repo already has complete spec documents. A software worker cannot procure, build, or test physical devices. |
| D2: Model manifests as JSON files | JSON manifest files alongside ONNX files containing: model_type, version, checksum (SHA256), training_dataset, validation_status, input_schema, output_schema, accuracy_metrics. Checked by capabilities endpoint. |
| D3: Soak test must run full 1 hour | User explicitly requires "genuine one-hour soak test" — no CI shortcut. Worker runs it and records evidence. |
| D4: Branch `codex/resqnet-remaining-work` | From current gap-closure head. Follows repo convention. |
| D5: Use public pre-trained models (USER DECISION) | User said "We don't have any models. We need to make them. For now use public pre-trained models." SAR: Governor6191/sar-flood-extent-unet-resnet34 (HF). Building damage: xView2 1st place (S3 public). NLP: CrisisPulse or CrisisTransformers (HF). All need PyTorch→ONNX export on CPU. |
| D6: Hybrid auth policy (USER DECISION) | User chose "Hybrid: fail-closed for admin, fail-open for ops." Fail-closed for: user management, config changes, system admin. Fail-open for: alert approval, emergency overrides, operational dispatch. All Redis-unavailable sensitive actions logged to audit chain with break-glass flag. |
| D7: Short-lived access tokens (15 min) + refresh tokens (7 days) | Current 720-minute (12h) TTL is a security risk. 15-min access + 7-day refresh is standard. Refresh tokens stored in Redis with rotation. |
| D8: Local emergency revocation cache | In-memory Set with TTL, populated from Redis on startup and on revocation. Survives Redis outage but not process restart. Checked before Redis for fail-closed operations. |

## Scope IN

1. Fix Playwright polling-fallback test (replace `.or()` with `.first()`)
2. Stabilize 6 backend tests (service health waits, deterministic topic setup, proper cleanup, adaptive assertions)
3. Add model manifest JSON files (type, version, checksum, training dataset, validation status)
4. Make `/api/capabilities` return `degraded` when placeholders are installed (check manifest validation_status)
5. Prevent placeholder outputs from creating operational alerts or recommendations
6. Download and install 3 public pre-trained models, export to ONNX, validate, record metrics
7. Install heavy geospatial dependencies (torch, segmentation_models_pytorch, torchvision, transformers, opencv)
8. Profile and optimize ingestion pipeline to 100 obs/sec (batching, bulk inserts, 6 Kafka partitions, worker concurrency, Docker resource increases)
9. Run genuine 1-hour soak test at target operator and ingestion load
10. Measure actual Redis/Redpanda/MinIO recovery times (replace hardcoded 30s)
11. Test overlapping failures, container restarts, disk pressure, intermittent network loss
12. Fix 4 frontend lint warnings (useClock hook, derived state, lazy initializers)
13. Harden auth: 15-min access tokens, 7-day refresh tokens, local revocation cache, hybrid fail-closed/fail-open, break-glass audit
14. Update deferred milestone docs for item 8 (software-readiness is complete; document any remaining gaps)

## Scope OUT (Must NOT have)

- Build, procure, or manufacture physical rescue-ball hardware
- Perform physical floodwater/deployment/landing/recovery testing
- Procure or physically calibrate real sensors
- Claim certified human-detection capability
- Execute multi-agency field trials
- Fabricate model accuracy, weights, benchmarks, or rescue capability
- Weaken existing graceful-degradation fallbacks (model_unavailable, Kafka noop producer, PMTiles vector fallback)
- Push to main
- Modify merged Phase 1 or gap-closure commits/history
- Train models from scratch on CPU (user chose pre-trained models, not training)

## Open questions

NONE — both forks resolved by user decisions D5 and D6.

## Approval gate
status: awaiting-approval
approach: 7-wave plan with 42 implementation todos + 4 final verification tasks. Wave 1: test fixes (items 1-2). Wave 2: ML gating + manifests (item 2 continued). Wave 3: real model installation (item 3). Wave 4: ingestion performance (item 4). Wave 5: reliability testing (item 5). Wave 6: frontend lint + auth hardening (items 6-7). Wave 7: field validation doc update (item 8) + final verification.
next: user approves → write .omo/plans/resqnet-remaining-work.md → user starts execution via /start-work
