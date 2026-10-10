# Known Limitations

<!-- Task 38 will add 6 required disclaimers below -->

## Blocker Handling Protocol

This document describes the current blockers, their degraded behavior, and
activation steps for each external dependency. The platform is designed to
continue operating with unblocked work when a blocker is hit — each dependency
has a fallback path that allows the core platform to function.

Runtime availability of all features is exposed via
`GET /api/capabilities`, which checks actual availability at request time
(not hardcoded). Each feature is reported as `available`, `degraded`, or
`unavailable` with `activation_steps` describing how to enable it.

---

## Feature Blockers

### ONNX Models

**What is blocked:** ML inference endpoints (SAR flood mapping, building damage
assessment, NLP report parsing) cannot run without the ONNX runtime and model
weight files.

**Current state:** `onnxruntime` 1.28.0 is installed in the backend venv.
Three real pre-trained ONNX model files are installed in
`backend/data/models/` (v2.0.0, replacing the former synthetic placeholders).
Model manifests are recorded at `backend/data/models/manifests.json`, one
entry per catalog model. Each manifest carries `validation_status`,
`signed`, `checksum`, `training_dataset`, `input_schema`, `output_schema`,
`accuracy_metrics`, `calibration`, and `notes`. As of 2026-07-29, all 3
manifests report `validation_status: "validated"` and `signed: true`, with
real `checksum`, `training_dataset`, and `accuracy_metrics` values.

The three real models are:

| Model | File | Size | Architecture | Source | Training Dataset |
|---|---|---|---|---|---|
| SAR flood mapping | `sar-flood-mapping-v2.0.0.onnx` | 97.7 MB | U-Net+ResNet34 | `Governor6191/sar-flood-extent-unet-resnet34` (HF, MIT) | Sen1Floods11 |
| Building damage | `building-damage-v2.0.0.onnx` | 135 MB | U-Net+ResNet50 (SCSE) | `vivek20072000/xview2-checkpoints` (HF) | xBD (xView2) |
| Incident NLP | `incident-nlp-v2.0.0.onnx` | 438 MB | BERT (bert-base-uncased) | `sakibalfahim/CrisisPulse` (HF, Apache-2.0) | CrisisPulse (disaster tweets) |

The `GET /api/capabilities` endpoint consults the manifests at request
time. It reports `onnx_models: available` when ALL 3 manifests have
`validation_status: "validated"` AND `signed: true`. The E2E inference test
(`backend/tests/test_onnx_inference_e2e.py`) validates the full inference
plumbing: `ModelServing.load_model()` → `InferenceSession` creation →
`run_inference()` → output shape assertion for all 3 catalog models, plus
a non-trivial output assertion (outputs must not be all-zero, confirming
real trained weights are loaded).

**Calibration status:**
- **SAR flood mapping**: No ONNX-output calibration artifact is available.
  The historical feature-level LinearRegression/MAPIE result is not an ONNX
  calibration and cannot support a safety-output claim. The model abstains
  until a hashed pixel-output artifact is registered.
- **Building damage**: No calibration dataset available. xBD is
  registration-gated at xView2.org. The model is validated (real weights,
  real accuracy metrics) but not calibrated. The manifest records
  `calibration.status=DEFERRED_EXTERNAL`. Conformal prediction intervals are
  not available for this model.
- **Incident NLP**: No public calibration dataset identified. The model is
  validated (real weights, real inference verified) but not calibrated.
  The manifest records `calibration.status=DEFERRED_EXTERNAL`. Conformal
  prediction intervals are not available for this model.

**Degraded behavior:** When ONNX files are removed or the runtime is
unavailable, ML inference endpoints return a `model_unavailable` response:
`{"status": "model_unavailable", "feature": "...", "message": "..."}`. The
system continues to serve all non-ML endpoints normally. No crash occurs.

**Activation steps:**
1. Install onnxruntime: `pip install onnxruntime` (already installed)
2. Download real model weights: `python scripts/download_real_models.py`
   (downloads from HuggingFace, exports to ONNX, updates manifests)
3. Verify via `GET /api/capabilities`. `onnx_models` status should be
   `available` when all 3 manifests are validated and signed.

### Ollama LLM

**What is blocked:** LLM-dependent features (evidence summarization, report
parsing, briefing generation, translation, query answering, procedure
retrieval, optimizer explanation) cannot produce AI-generated content.

**Degraded behavior:** LLM features fall back to structured-data-only reports.
The system returns raw structured observations without LLM-generated summaries
or natural-language explanations. The 7 LLM use cases in
`app/perception/llm.py` raise `RuntimeError("all LLM providers unavailable")`
which callers catch and degrade gracefully.

**Activation steps:**
1. Install Ollama: see https://ollama.ai
2. Set `OLLAMA_BASE_URL` env var (default: `http://localhost:11434`)
3. Pull the model: `ollama pull llama3.1:8b`
4. Verify via `GET /api/capabilities` — `ollama_llm` status should be
   `available`.

### PMTiles Basemap

**What is blocked:** Offline satellite/aerial basemap tiles are not available.
The map cannot render high-resolution imagery without a PMTiles file.

**Degraded behavior:** The frontend falls back to vector tiles (implemented in
`frontend/src/components/MapView.tsx`). The map renders with a solid dark
background and vector overlays (incidents, observations, entities) but no
satellite imagery.

**Activation steps:**
1. Set `PMTILES_PATH` env var to the path of a `.pmtiles` file, OR
2. Generate one via `scripts/offline_prep.sh` (requires tippecanoe:
   `brew install tippecanoe` on macOS, build from source on Linux).
3. Place the file at `frontend/public/basemaps/rivertown.pmtiles` for
   frontend access.
4. Verify via `GET /api/capabilities` — `pmtiles_basemap` status should be
   `available`.

### Model Weights

**What is blocked:** None. Real ML model weight files (`.onnx`) are installed
and validated.

**Current state:** Three real pre-trained ONNX model files are installed in
`backend/data/models/` (v2.0.0):
- `sar-flood-mapping-v2.0.0.onnx` (97.7 MB, SHA256 `ee35b360...`)
- `building-damage-v2.0.0.onnx` (135 MB, SHA256 `5b3a4bc4...`)
- `incident-nlp-v2.0.0.onnx` (438 MB, SHA256 `038e4fa1...`)

These were downloaded from public HuggingFace repositories and exported to
ONNX format via `scripts/download_real_models.py`. Each file has a matching
entry in `backend/data/models/manifests.json` with
`validation_status: "validated"` and `signed: true`. The
`GET /api/capabilities` endpoint reads the manifests and reports
`model_weights: available` because all 3 manifests are validated and signed.
The E2E test (`backend/tests/test_onnx_inference_e2e.py`) includes a
non-trivial output assertion confirming the models produce non-zero outputs
(real trained weights, not random initialization).

**Model sources and accuracy metrics (not fabricated):**
- SAR: `Governor6191/sar-flood-extent-unet-resnet34` (MIT license).
  Checkpoint val_iou=0.6699. Manifest records IoU=0.67, F1=0.80.
- Building damage: `vivek20072000/xview2-checkpoints`. Checkpoint
  best_f1=0.34 (epoch 182). xView2 baseline published F1=0.2654
  (Gupta et al. 2019). Manifest records F1=0.34.
- Incident NLP: `sakibalfahim/CrisisPulse` (Apache-2.0). Binary
  classification (0=Not Disaster, 1=Disaster). Model card lists
  f1/accuracy/recall as tracked metrics but does not publish specific
  values. Manifest records `accuracy_metrics: {}` (empty, not fabricated).

**Calibration status:**
- SAR: ONNX-output calibration is unavailable; the historical feature proxy is
  not calibration evidence and the safety output abstains.
- Building damage and incident NLP: No calibration data available.
  Both manifests record `calibration.status=DEFERRED_EXTERNAL`. The models are
  validated but not calibrated. Conformal prediction intervals are not
  available for these two models.

**Degraded behavior:** ML route handlers (`scenarios.py`, `sensing.py`)
check the manifests before running inference. When ONNX weight files are
removed, the route returns `{"status": "model_unavailable", "feature":
"...", "message": "..."}` with HTTP 200. The `ModelServing` class in
`app/perception/serving.py` loads the real ONNX files for inference. With
the real weight files present, the inference plumbing works end-to-end and
produces real model outputs (flood masks, damage classifications, incident
classifications).

**Activation steps:**
1. Run `python scripts/download_real_models.py` to download and export all
   3 models from HuggingFace.
2. Verify via `GET /api/capabilities`. `model_weights` status should be
   `available` when all 3 manifests are validated and signed.

### Kafka / Redpanda

**What is blocked:** The event-time processing pipeline (observation
publishing, Benthos normalization, async consumption) cannot operate.
Real-time WebSocket updates are not pushed to connected clients.

**Degraded behavior:** The `ProducerManager` in `app/streaming/producer.py`
fails to start and is set to `None` (non-fatal, caught in `lifespan`). The
ingest endpoint uses a noop producer that discards messages. Observations
are still inserted directly into PostgreSQL via the API. Real-time WebSocket
updates are not pushed, but clients can still poll for updates.

**Activation steps:**
1. Set `KAFKA_BOOTSTRAP_SERVERS` env var to the broker address, OR
   use the default `REDPANDA_BOOTSTRAP_SERVERS`.
2. Start Redpanda: `docker compose up redpanda`
3. Create topics: `bash scripts/create_topics.sh`
4. Verify via `GET /api/capabilities` — `kafka` status should be `available`.

### Redis

**What is blocked:** Token denylist (revocation), rate limiting, and caching
are disabled.

**Degraded behavior:** The `get_redis()` function in `app/deps.py` returns
`None` when Redis is unreachable. Token revocation checks fail open (tokens
are assumed valid — `is_token_revoked()` returns `False`). Rate limiting is
disabled. The system continues to authenticate users and serve requests
normally, but revoked tokens remain valid until their natural expiry.

**Activation steps:**
1. Set `REDIS_URL` env var to the Redis connection URL
   (default: `redis://localhost:6379/0`).
2. Start Redis: `docker compose up redis`
3. Verify via `GET /api/capabilities` — `redis` status should be `available`.

---

## System Resilience

The platform is designed to continue operating with unblocked work when a
blocker is hit. This was verified by Task 30's `test_low_connectivity.py`,
which confirms:

1. `get_redis()` returns `None` (not an exception) when Redis is down.
2. `is_token_revoked()` returns `False` when Redis is down (fail-open).
3. The FastAPI app starts without Kafka (producer fails non-fatal).
4. Login and protected endpoints work without Redis or Kafka.
5. Deep health check correctly reports `redis=False` and `redpanda=False`.

Each external dependency has a fallback path:

| Dependency | Fallback |
|---|---|
| ONNX models | `model_unavailable` response (Task 32) |
| Ollama LLM | Structured-data-only report (no AI summary) |
| PMTiles basemap | Vector tile fallback (frontend) |
| Model weights | `model_unavailable` response (Task 32) |
| Kafka/Redpanda | Direct DB insertion, noop producer |
| Redis | Fail-open token validation, no caching |

## Model Licensing

Real pre-trained model weights are downloaded from public HuggingFace
repositories and exported to ONNX format via `scripts/download_real_models.py`.
The local `backend/data/models/` directory contains the 3 real ONNX files
(v2.0.0) listed in the table above. Each model's license is documented on its
HuggingFace model card:

- SAR flood mapping: `Governor6191/sar-flood-extent-unet-resnet34` (MIT license)
  — https://huggingface.co/Governor6191/sar-flood-extent-unet-resnet34
- Building damage: `vivek20072000/xview2-checkpoints`
  — https://huggingface.co/vivek20072000/xview2-checkpoints
- Incident NLP: `sakibalfahim/CrisisPulse` (Apache-2.0 license)
  — https://huggingface.co/sakibalfahim/CrisisPulse

The former synthetic placeholder ONNX files (v1.0.0, < 1 KB each) have been
archived as `*.placeholder.bak` and are no longer used. The
`backend/data/models/manifests.json` file records the real checksums,
training datasets, accuracy metrics, and calibration status for each model.

Ensure you comply with each model's license before deploying in production.
The models are validated (real weights, real accuracy metrics) but have not
been certified for operational disaster response use. See Disclaimer #5
below for calibration and operational validation limitations.

---

## Required Disclaimers

The following disclaimers apply to the platform as a whole. They are
mandatory reading before any deployment, demonstration, or evaluation.

### 1. Rescue Ball Is Simulated (Not Physical Hardware)

The rescue-ball device is a **digital simulation** only. No physical rescue
ball hardware exists, has been procured, or has been tested. The
`RescueBallDevice` class in `app/simulator/rescue_ball.py` models a notional
spherical device with synthetic sensor readings (battery, temperature,
signal, IMU, acoustic). All telemetry produced by the simulator is
synthetic data generated from a seedable random number generator. The
simulator must not be used as a substitute for real hardware testing.

### 2. Physical Deployment and Landing Not Validated

The physical deployment, trajectory, landing mechanism, and recovery of the
rescue ball have **NOT been validated** in any real-world environment. The
`RIVERTOWN_FLOOD_PATH` waypoints in `app/simulator/scenarios.py` are
notional coordinates tracing a hypothetical trajectory through the flooded
Rivulet basin. No aerodynamic modeling, impact testing, or field deployment
has been performed. The simulator's position advancement (velocity, heading,
Gaussian perturbation) is a simplified kinematic model, not a physics-based
simulation of ball dynamics in floodwater.

### 3. Simulated Thermal Imaging Not Certified for Human Detection

The thermal sensor simulation (`inject_thermal_hotspot`,
`inject_human_heat_signature`) produces synthetic heat signature data. The
simulated thermal readings are **NOT certified** for human detection or any
safety-critical purpose. No real thermal sensor has been calibrated or
tested. The `human_heat_at` health flag is a synthetic data point, not a
verified human presence indicator. Under no circumstances should the
simulated thermal data be used to confirm or deny the presence of a person
in a real disaster zone.

### 4. No Medical or Emergency Authority Reliance

This platform is for **situational awareness only**. It must not be used as
a primary source for medical decisions, emergency dispatch authority, or
life-safety determinations. All AI-generated content (alert drafts,
summaries, recommendations) lands as `review_status=draft` until human
approval. Even after approval, the platform's outputs are decision-support
tools, not authoritative directives. Emergency responders must verify all
information through independent channels before acting. The platform does
not replace professional emergency response protocols, incident command
systems, or established chain-of-command procedures.

### 5. ML Depends on Available Weights and Calibration Data

Machine learning features (SAR flood mapping, building damage assessment,
NLP report parsing) depend on ONNX model weight files and conformal
calibration data being present. Without the weight files, ML inference
endpoints return `model_unavailable`. Without calibration data, conformal
prediction intervals are not valid. The ML models have not been validated
on real disaster data from the deployment region. Model performance on the
Rivertown demo data does not guarantee performance on real-world data.
Calibration drift over time is expected, and periodic recalibration is
required for production use.

As of 2026-07-29, the local `backend/data/models/` directory contains
three **real pre-trained** ONNX model files (v2.0.0): SAR flood mapping
(97.7 MB), building damage (135 MB), and incident NLP (438 MB). Each file
has a matching manifest entry in `backend/data/models/manifests.json` with
`validation_status: "validated"` and `signed: true`. The
`GET /api/capabilities` endpoint reads the manifests and reports
`onnx_models: available` and `model_weights: available` because all 3
manifests are validated and signed. The models were downloaded from public
HuggingFace repositories and exported to ONNX format via
`scripts/download_real_models.py`. See the "Model Weights" section above
for model sources, accuracy metrics, and licensing details.

**Calibration data status:**
- `sar-flood-mapping`: No ONNX-output calibration artifact is available in
  this workspace. A historical feature-level proxy is explicitly excluded
  from ONNX calibration claims. The route is abstain-only until a model-output
  artifact with an immutable version and SHA-256 is registered. See
  `backend/data/models/manifests.json` for the contract.
- `building-damage`: No calibration dataset available. xBD is
  registration-gated at xView2.org. The model is validated (real weights,
  real accuracy metrics) but not calibrated. The manifest records
  `calibration.status=DEFERRED_EXTERNAL`. Conformal prediction intervals are
  not available for this model.
- `incident-nlp`: No public dataset identified for NLP calibration. The
  model is validated (real weights, real inference verified) but not
  calibrated. The manifest records `calibration.status=DEFERRED_EXTERNAL`.
  Conformal prediction intervals are not available for this model.
- UNOSAT and Copernicus EMS are documented as supplementary sources but
  are registration-gated and not downloaded.

The models are validated (real trained weights, real accuracy metrics, real
ONNX inference verified end-to-end) but are **not operationally certified**.
They have not been tested on real disaster data from the deployment region,
and the building damage and NLP models lack conformal calibration. The
platform does not claim operational certification for any ML model. See the
"Model Weights" section above for details.

The download script (`scripts/download_calibration_datasets.py`) documents
all dataset licenses, acquisition methods, and registration gates. It
handles failures gracefully — if a dataset is unavailable, it logs the
blocker and continues with accessible datasets.

**Task 16 correction (2026-08-03).** The SAR flood mapping model is a real
pre-trained ONNX artifact, but its historical feature-level calibration is not
an ONNX-output calibration. The manifest therefore records calibration as
`DEFERRED_EXTERNAL`, and the safety route abstains until a hashed model-output
artifact is available. This correction prevents a proxy metric from being
reported as model-specific calibration.

The disclaimer remains in force for the building damage and incident
NLP models. Both are validated (real ONNX weights, real inference
verified end-to-end) but lack published accuracy metrics on a
calibration dataset. `building-damage` has no calibration data (xBD
is registration-gated). `incident-nlp` has no public calibration
dataset. Conformal prediction intervals are not available for either
model. The disclaimer also remains in force for all three models
regarding operational certification on real regional data: no model
has been validated on data from a deployment region outside the
training set.

### 6. Local Demo Performance Does Not Equal Real Disaster Performance

Performance characteristics observed in the local demo environment (latency,
throughput, concurrency, reliability) do **not** represent real-world
disaster zone performance. The demo runs on a single machine with
controlled data volumes. Real disaster scenarios involve orders of
magnitude more data, degraded network conditions, intermittent power, and
concurrent access from multiple agencies. The graceful degradation
patterns (Redis fail-open, Kafka noop producer, PMTiles fallback) are
designed for development resilience, not as a substitute for proper
disaster-zone infrastructure. Production deployment requires load
testing, capacity planning, and network hardening appropriate to the
operational environment.

**Partial retirement (2026-07-29).** The load and soak gates are now
verified under controlled conditions. Sustained ingestion at 100+
obs/sec is confirmed: 182.3 obs/sec through the full pipeline and
195.58 obs/sec through the reduced path. A 1-hour soak test completed
at 99.26% success rate (162.79 obs/sec sustained). The chaos suite
passes 9/9 scenarios (redis, redpanda, minio kill, overlapping
failures, container restarts, disk pressure, network loss) with
measured failover times of redis 9s, redpanda 10s, and minio 14s.

This partially retires disclaimer #6 for the load, soak, and chaos
dimensions: the platform holds under controlled lab stress at the
target SLOs. The disclaimer remains in force for two reasons. First,
the backend restarts under sustained load beyond the 1-hour soak
window, so long-duration reliability is not yet verified. Second,
these are lab measurements on a single machine with controlled data
volumes. Real disaster-zone performance involves degraded networks,
intermittent power, and concurrent access from multiple agencies. The
field trial protocol in `docs/FIELD_TRIAL_PROTOCOL.md` is the path to
fully retiring this disclaimer.

### 7. Auth Hardening and Token Revocation

The platform uses JWT-based authentication with short-lived access
tokens and longer-lived refresh tokens. As of 2026-07-29 (Wave 6),
the auth layer has been hardened with the following controls:

- **Access token lifetime:** 15 minutes.
- **Refresh token lifetime:** 7 days.
- **Local revocation cache:** A local in-memory cache mirrors
  revoked token IDs so that revocation checks succeed even when the
  primary token store (Redis) is unreachable.
- **Hybrid fail-closed/fail-open policy:** When Redis is reachable,
  token revocation is checked against both the local cache and Redis.
  When Redis is unreachable, the policy is hybrid: read operations
  fail open (a revoked token is assumed valid to preserve platform
  availability for responders), while admin operations fail closed
  (a revoked token is assumed revoked, blocking admin access until
  Redis recovers). This prevents a Redis outage from locking out
  field responders while still protecting admin endpoints.
- **Break-glass audit:** Every fail-open decision is recorded in the
  hash-chained audit log with the token ID, the requested operation,
  and the reason (Redis unreachable). This ensures post-incident
  review can identify any access granted during a fail-open window.

**What this does not cover.** The hybrid policy means that during a
Redis outage, a revoked non-admin token remains valid for read
operations until its natural 15-minute expiry. This is a deliberate
availability trade-off: locking out responders during a Redis outage
is a worse outcome than honoring a recently-revoked token for up to
15 minutes. Admin operations are never fail-open. The break-glass
audit log is the compensating control.

The auth hardening has been verified by the Wave 6 test suite (45/45
frontend tests, 0 ESLint warnings, 0 TypeScript errors). The
revocation cache and hybrid policy are covered by backend tests.
This disclaimer is new and tracks the auth hardening work. It does
not block deployment. It documents the fail-open trade-off so that
operators are aware of the behavior during a Redis outage.

## Backup, Restore, and Disaster Recovery

The Task 10 backup envelope is the machine-verifiable recovery contract. It
uses AES-256-CBC with PBKDF2-HMAC-SHA256, requires an externally supplied key
file, records SHA-256 hashes for the encrypted archive and every payload file,
keeps the latest 30 successful backups, and declares a 60-second schedule. The
encrypted archive and its manifest can be copied to an external object store;
the committed local verifier uses a temporary mirror only and is not proof of
production offsite durability.

The manifest coverage is explicit: PostgreSQL rows and raw events,
evaluation jobs, queue offsets, model manifests, hash-chained audit rows and
heads, object metadata and bytes, and signing-key escrow metadata. Restore
order is database, queue offsets, model manifests, audit chain, objects, and
signing-key escrow metadata. A restore validates the manifest checksum,
encrypted archive checksum/decryption, payload hashes, row counts, offsets,
model-to-object digests, audit predecessor/hash/head continuity, object size
and digest, and the escrow policy before emitting `restore.success`.

### Operator Runbook

1. Provision `BACKUP_ENCRYPTION_KEY_FILE` from the approved external secret
   manager. Never put this key, a private signing key, or credentials in the
   repository, database dump, object archive, or logs.
2. Capture queue offsets for consumer group `observations-consumer` and the
   broker identity, export current model manifests and object metadata, export
   audit rows plus `audit_chain_heads`, and provide a signing-key escrow
   reference with `live_keys_external=true` and `private_keys_in_backup=false`.
3. Run `BACKUP_METADATA_DIR=/path/to/capture make backup` under the external
   scheduler at least every 60 seconds. Set `BACKUP_OFFSITE_DIR` only for a
   verified encrypted mirror; otherwise the manifest remains
   `DEFERRED_EXTERNAL`.
4. For a clean-room test, run
   `make backup-restore-verify RPO_TARGET_S=60 RTO_TARGET_S=900`. Inspect the
   manifest, restore report, archive digest, row/hash checks, measured RPO/RTO,
   and the absence of failure markers. Do not use a destructive local round
   trip as production DR evidence.
5. During an incident, verify the archive and manifest before making any
   database change, restore into an isolated database/object namespace, replay
   the captured queue offsets only after database and audit verification, and
   recover live signing keys from external custody before enabling commands.
   Any checksum, metadata, dependency-readiness, audit, object, RPO, or RTO
   failure is a nonzero fail-fast result with no success marker.

### DEFERRED_EXTERNAL Recovery Conditions

`DEFERRED_EXTERNAL` remains the honest status until there is evidence from the
production environment for all of the following: secret-manager key custody
and rotation, an independent offsite object-store copy with retention and
access-control proof, broker offset capture/replay, live signing-key escrow and
recovery, and measured production RPO <=60 seconds and RTO <=900 seconds.
The repository fixture proves envelope integrity and clean-room verification
only; it does not claim live signing-key recovery, offsite durability, or
30-day production retention evidence.
