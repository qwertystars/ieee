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

**Degraded behavior:** ML inference endpoints return a `model_unavailable`
response: `{"status": "model_unavailable", "feature": "...", "message": "..."}`
(implemented in Task 32). The system continues to serve all non-ML endpoints
normally. No crash occurs.

**Activation steps:**
1. Install onnxruntime: `pip install onnxruntime`
2. Download model weights: `python scripts/download_models.py --download`
3. Verify via `GET /api/capabilities` — `onnx_models` status should be
   `available`.

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

**What is blocked:** ML model weight files (`.onnx`) are not present in the
local data directory (`backend/data/models/`). Even with onnxruntime
installed, inference cannot proceed without weight files.

**Degraded behavior:** Same as ONNX Models — ML inference endpoints return
`model_unavailable` response. The `ModelServing` class in
`app/perception/serving.py` attempts to download weights from MinIO on first
load; if MinIO is also unavailable, the load fails and the caller returns the
`model_unavailable` response.

**Activation steps:**
1. Run `python scripts/download_models.py --download` to fetch model weights
   from HuggingFace and upload to MinIO.
2. Alternatively, manually place `.onnx` files in `backend/data/models/`
   matching the `r2_key` paths in `MODEL_CATALOG` (e.g.,
   `models/sar-flood-mapping-v1.0.0.onnx`).
3. Verify via `GET /api/capabilities` — `model_weights` status should be
   `available`.

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

Model weights are downloaded from HuggingFace under the `resqnet` organization.
See `scripts/download_models.py --list` for the full catalog. Licensing
information for each model is available on its HuggingFace model card:

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
