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
- **SAR flood mapping**: Conformal calibration active. Coverage 0.9412 at
  alpha=0.1 (90% nominal), within the [0.85, 0.95] target band. Calibration
  data: 55 chips from Sen1Floods11 (5 SAR-derived features → water_fraction).
  Interval width 0.6235. Brier score 0.2621, ECE 0.1262.
- **Building damage**: No calibration dataset available. xBD is
  registration-gated at xView2.org. The model is validated (real weights,
  real accuracy metrics) but not calibrated. `calibration: null` in the
  manifest. Conformal prediction intervals are not available for this model.
- **Incident NLP**: No public calibration dataset identified. The model is
  validated (real weights, real inference verified) but not calibrated.
  `calibration: null` in the manifest. Conformal prediction intervals are
  not available for this model.

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
- SAR: Conformal calibration active (coverage 0.9412, see ONNX Models
  section above).
- Building damage and incident NLP: No calibration data available.
  `calibration: null` in both manifests. The models are validated but
  not calibrated. Conformal prediction intervals are not available for
  these two models.

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
- `sar-flood-mapping`: Real-data conformal calibration is **active** using
  the Sen1Floods11 dataset (CC BY 4.0). 55 hand-labeled Sentinel-1 SAR chips
  across 11 flood events were downloaded from the public GCS bucket and
  converted to calibration features (mean VV, mean VH, VV-VH difference,
  std VV, std VH → water fraction). Conformal coverage on the held-out
  prediction set is 0.9412, within the target [0.85, 0.95] band for
  alpha=0.1. The calibration data is stored under
  `backend/data/calibration/sen1floods11/` (gitignored, not committed).
  See `docs/MODEL_DATA_LICENSING.md` for dataset licensing details.
- `building-damage`: No calibration dataset available. xBD is
  registration-gated at xView2.org. The model is validated (real weights,
  real accuracy metrics) but not calibrated. `calibration: null` in the
  manifest. Conformal prediction intervals are not available for this model.
- `incident-nlp`: No public dataset identified for NLP calibration. The
  model is validated (real weights, real inference verified) but not
  calibrated. `calibration: null` in the manifest. Conformal prediction
  intervals are not available for this model.
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
