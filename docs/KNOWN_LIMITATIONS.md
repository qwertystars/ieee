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
Three synthetic placeholder ONNX files exist in `backend/data/models/` with
correct I/O schemas (tensor names, shapes, dtypes) matching `MODEL_CATALOG`.
Model manifests are recorded at `backend/data/models/manifests.json`, one
entry per catalog model. Each manifest carries `validation_status`,
`signed`, `checksum`, `training_dataset`, `input_schema`, `output_schema`,
`accuracy_metrics`, and `notes`. As of 2026-07-29, all 3 manifests report
`validation_status: "placeholder"` and `signed: false`, with
`accuracy_metrics: null` and `training_dataset: null`.

The `GET /api/capabilities` endpoint consults the manifests at request
time. It reports `onnx_models: degraded` (not `available`) when any
manifest has `validation_status != "validated"` or `signed: false`. It only
reports `available` when ALL 3 manifests have
`validation_status: "validated"` AND `signed: true`. The E2E inference test
(`backend/tests/test_onnx_inference_e2e.py`) validates the full inference
plumbing: `ModelServing.load_model()` → `InferenceSession` creation →
`run_inference()` → output shape assertion for all 3 catalog models.

**CRITICAL: placeholders are NOT trained models.** The placeholder ONNX files
are < 1 KB each and use trivial ops (Identity, ReduceMean, Constant). They
produce correctly-shaped outputs from correctly-shaped inputs but have **NO
trained weights**. The manifests pin their `validation_status` to
`"placeholder"` and `signed` to `false`, which is why `/api/capabilities`
reports `degraded` and the ML route handlers refuse to produce operational
outputs (see Model Weights below). They validate the inference plumbing only.
**Do not use them for any real disaster response.** Production deployment
requires replacing them with real trained weights AND updating each manifest
to `validation_status: "validated"` with `signed: true`.

**Degraded behavior:** ML inference endpoints return a `model_unavailable`
response with a placeholder-specific reason:
`{"status": "model_unavailable", "reason": "placeholder_model_not_validated",
"feature": "...", "message": "..."}`. The guard fires before the weights
check, so it triggers even when the placeholder `.onnx` files are present.
The system continues to serve all non-ML endpoints normally. No crash occurs.

**Activation steps:**
1. Install onnxruntime: `pip install onnxruntime` (already installed)
2. Download real model weights: `python scripts/download_models.py --download`
   (requires HuggingFace authentication, see Model Weights below)
3. Update each manifest in `backend/data/models/manifests.json` to
   `validation_status: "validated"` and `signed: true`, with real
   `checksum`, `training_dataset`, and `accuracy_metrics` values.
4. Verify via `GET /api/capabilities`. `onnx_models` status should be
   `available` only after all 3 manifests are validated and signed.

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

**What is blocked:** Real ML model weight files (`.onnx`) are not available.
The HuggingFace `resqnet` model repos are **private/gated** — all 3
`source_url`s in `MODEL_CATALOG` return HTTP 401 ("Invalid username or
password") when accessed without authentication. The `resqnet` HF org page
loads (HTTP 200) but `api/models?author=resqnet` returns an empty list `[]`,
confirming zero public models.

**HF URL verification (2026-07-28):**
- `https://huggingface.co/resqnet/sar-flood-mapping/resolve/v1.0.0/model.onnx` → 401
- `https://huggingface.co/resqnet/building-damage/resolve/v1.0.0/model.onnx` → 401
- `https://huggingface.co/resqnet/incident-nlp/resolve/v1.0.0/model.onnx` → 401

**Current state:** Three synthetic placeholder ONNX files exist in
`backend/data/models/` (flat, not nested):
- `sar-flood-mapping-v1.0.0.onnx` (168 bytes)
- `building-damage-v1.0.0.onnx` (137 bytes)
- `incident-nlp-v1.0.0.onnx` (200 bytes)

These were generated by a one-off script using the `onnx` Python package
(build-time tool, not a runtime dependency). They have the correct I/O
schemas but contain **NO trained weights**. They use trivial ops
(Identity, ReduceMean, Constant) to produce correctly-shaped outputs.
Each file has a matching entry in `backend/data/models/manifests.json`
with `validation_status: "placeholder"` and `signed: false`. The
`GET /api/capabilities` endpoint reads the manifests and reports
`model_weights: degraded` (not `available`) because the placeholders are
not validated. The E2E test (`backend/tests/test_onnx_inference_e2e.py`)
includes a honesty guard that asserts each placeholder file is < 1 KB,
preventing anyone from mistaking them for real trained models.

**Degraded behavior:** ML route handlers (`scenarios.py`, `sensing.py`)
check the manifests before running inference. When any manifest has
`validation_status: "placeholder"` or `signed: false`, the route
short-circuits and returns `{"status": "model_unavailable", "reason":
"placeholder_model_not_validated", "feature": "...", "message": "..."}`
with HTTP 200. This blocks placeholder outputs from creating operational
alerts or recommendations. The `ModelServing` class in
`app/perception/serving.py` can still load the placeholder files for
plumbing tests, but the route guard prevents those outputs from
influencing operational decisions. With the placeholder files present,
the inference plumbing works end-to-end but produces meaningless outputs
(zeros, identity copies, channel-mean reductions), not real flood masks,
damage classifications, or incident classifications.

**Activation steps:**
1. Obtain HuggingFace authentication (token or credentials) for the `resqnet`
   organization, OR obtain the trained `.onnx` files through another channel.
2. Replace the placeholder files in `backend/data/models/` with the real
   trained weights (same filenames: `sar-flood-mapping-v1.0.0.onnx`,
   `building-damage-v1.0.0.onnx`, `incident-nlp-v1.0.0.onnx`).
3. Alternatively, run `python scripts/download_models.py --download` with
   `HF_TOKEN` env var set to authenticate the download.
4. Update each manifest in `backend/data/models/manifests.json`: set
   `validation_status: "validated"`, `signed: true`, and fill in real
   `checksum`, `training_dataset`, and `accuracy_metrics` values.
5. Verify via `GET /api/capabilities`. `model_weights` status should be
   `available` only after all 3 manifests are validated and signed.

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

Model weights are nominally hosted on HuggingFace under the `resqnet` organization.
See `scripts/download_models.py --list` for the full catalog. As of 2026-07-28,
the `resqnet` model repos are **private/gated** (HTTP 401 on all 3 `source_url`s)
and cannot be downloaded without HuggingFace authentication. The local
`backend/data/models/` directory contains **synthetic placeholder** ONNX files
that validate the inference plumbing but are NOT trained models — see the
"Model Weights" section above for details.

When the real weights become available, licensing information for each model
will be available on its HuggingFace model card:

- `sar-flood-mapping`: https://huggingface.co/resqnet/sar-flood-mapping
- `building-damage`: https://huggingface.co/resqnet/building-damage
- `incident-nlp`: https://huggingface.co/resqnet/incident-nlp

Ensure you comply with each model's license before deploying in production.

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
calibration data being present. Without the weight files (downloaded via
`scripts/download_models.py --download`), ML inference endpoints return
`model_unavailable`. Without calibration data, conformal prediction
intervals are not valid. The ML models have not been validated on real
disaster data from the deployment region. Model performance on the
Rivertown demo data does not guarantee performance on real-world data.
Calibration drift over time is expected, and periodic recalibration is
required for production use.

As of 2026-07-29, the local `backend/data/models/` directory contains
**synthetic placeholder** ONNX files (< 1 KB each) that validate the
inference plumbing but contain **NO trained weights**. Each file has a
matching manifest entry in `backend/data/models/manifests.json` with
`validation_status: "placeholder"` and `signed: false`. The
`GET /api/capabilities` endpoint reads the manifests and reports
`onnx_models: degraded` and `model_weights: degraded` (not `available`)
because the placeholders are not validated. ML route handlers
(`scenarios.py`, `sensing.py`) check the manifests before inference and
return `{"status": "model_unavailable", "reason":
"placeholder_model_not_validated"}` when any manifest is a placeholder or
unsigned. This blocks unvalidated AI outputs from creating operational
alerts or recommendations. The HuggingFace `resqnet` model repos are
private/gated (HTTP 401). Real trained weights require HF authentication
to download, after which the manifests must be updated to
`validation_status: "validated"` and `signed: true`. See the "Model
Weights" blocker section above for details.

**Calibration data status (T9, 2026-07-28):** Real-data conformal calibration
is **active** for the `sar-flood-mapping` model using the Sen1Floods11 dataset
(CC BY 4.0). 55 hand-labeled Sentinel-1 SAR chips across 11 flood events
were downloaded from the public GCS bucket and converted to calibration
features (mean VV, mean VH, VV-VH difference, std VV, std VH → water
fraction). Conformal coverage on the held-out prediction set is 0.9412,
within the target [0.85, 0.95] band for alpha=0.1. The calibration data is
stored under `backend/data/calibration/sen1floods11/` (gitignored, not
committed). See `docs/MODEL_DATA_LICENSING.md` for dataset licensing details.

**Remaining calibration gaps:**
- `building-damage`: xBD dataset is registration-gated at xView2.org — not
  downloaded. Conformal calibration for building damage uses fixture data
  only (T8 synthetic samples). Marked `degraded` for this model.
- `incident-nlp`: No public dataset identified for NLP calibration.
  Conformal intervals are not available for NLP predictions. Marked
  `degraded` for this model.
- UNOSAT and Copernicus EMS are documented as supplementary sources but
  are registration-gated and not downloaded.

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
