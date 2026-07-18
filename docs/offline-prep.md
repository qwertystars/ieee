# Offline Pre-Deployment Preparation

This document describes how to prepare the ResQNet-SAGE stack for fully offline
operation. After running `scripts/offline_prep.sh`, the system starts with
**no internet connection** required.

## Quick start

```bash
bash scripts/offline_prep.sh
# ... wait for downloads to complete (warnings are OK) ...

# Verify offline boot:
docker compose down
docker compose up -d --wait
curl -s http://localhost:8000/healthz   # → {"ok":true,...}
```

## What gets downloaded / cached

| Step | Asset | Location | Notes |
|------|-------|----------|-------|
| 1 | ML model base weights (DOFA, ResNet50 S1, Clay, TerraMind) | `backend/models/cache/` | Base pretrained only — fine-tuning happens in Wave 4 (T18-T21) |
| 2 | PMTiles basemap (Rivertown) | `frontend/public/basemaps/rivertown.pmtiles` | Requires `tippecanoe`; skipped if not installed |
| 3 | Custom Docker images (db, backend, frontend) | Docker daemon | `resqnet-db` + `docker compose build` |
| 4 | Pre-pulled Docker images | Docker daemon | redis, redpanda, minio, ollama, benthos, prometheus, grafana |
| 5 | Vendored pip packages (`.whl` files) | `backend/vendor/` | GDAL/rasterio may fail without system libs — non-fatal |
| 6 | npm `package-lock.json` + `node_modules/` | `frontend/` | Enables offline `npm ci` |
| 7 | Sample SAR scene | `backend/data/sample-sar/` | Placeholder GeoTIFF for testing |
| 8 | Ollama model (`llama3.1:8b`) | `ollama_data` volume | ~4.7 GB |
| 9 | Whisper ASR model (`base`) | `backend/models/cache/whisper/` | Requires `openai-whisper` pip package |
| 10 | spaCy NER model (`en_core_web_sm`) | `backend/models/cache/ner/` | PII detection |

## Minimum hardware requirements

### Full stack (all services + ML inference)

| Resource | Minimum |
|----------|---------|
| CPU cores | 16 |
| RAM | 32 GB |
| Storage (SSD) | 256 GB |
| GPU | Not required (CPU-only inference via `torch --index-url .../whl/cpu`) |

### Reduced stack (no ML, no Grafana)

| Resource | Minimum |
|----------|---------|
| CPU cores | 8 |
| RAM | 16 GB |
| Storage (SSD) | 128 GB |

### Per-service resource limits (docker-compose.yml)

| Service | CPUs | Memory |
|---------|------|--------|
| db | 2 | 4G |
| redis | 0.5 | 512M |
| redpanda | 2 | 4G |
| minio | 1 | 1G |
| ollama | 4 | 8G |
| benthos | 0.5 | 512M |
| backend | 2 | 4G |
| frontend | 0.5 | 512M |
| prometheus | 0.5 | 512M |
| grafana | 0.5 | 512M |

> **Note:** Redpanda requires a minimum of 4 GB RAM. Setting it lower causes OOM.
> Ollama needs 8 GB for `llama3.1:8b` inference.

## Script behavior

- **Idempotent**: Running twice skips already-downloaded files. Safe to re-run.
- **Resilient**: Individual download failures log a warning and continue. The
  script exits 0 even if some assets are unavailable (e.g., model URL changed).
- **Progress**: Each step prints `[N/12] <name>` before executing.

## Verification

```bash
# 1. Script exits 0 (warnings are OK)
bash scripts/offline_prep.sh; echo "exit: $?"

# 2. YAML validates after resource limits added
docker compose config --quiet

# 3. Stack boots offline
docker compose down
docker compose up -d --wait

# 4. Health check passes
curl -s http://localhost:8000/healthz
# Expected: {"ok":true,"bindings":{...},"environment":"development"}
```

## Troubleshooting

### tippecanoe not installed

PMTiles generation is skipped. Install tippecanoe to generate basemaps:

```bash
# macOS
brew install tippecanoe
# Ubuntu/Debian
sudo apt-get install build-essential libsqlite3-dev zlib1g-dev
git clone https://github.com/felt/tippecanoe.git && cd tippecanoe && make -j && sudo make install
```

### GDAL / rasterio pip download fails

These packages require system GDAL libraries. The script logs a warning and
continues. The backend Docker image installs them via `apt-get` (see
`backend/Dockerfile`), so offline Docker builds still work.

### Ollama model pull fails

Ensure the Ollama service is healthy first:

```bash
docker compose up -d ollama
docker compose exec ollama ollama list   # should not error
docker compose exec ollama ollama pull llama3.1:8b
```

### Whisper model download fails

Install the `openai-whisper` package first:

```bash
pip install openai-whisper
```

Then re-run `bash scripts/offline_prep.sh` (step 9 is idempotent).

### ML model URLs changed

The script uses HuggingFace URLs for base pretrained weights. If a URL changes,
update the `*_URL` variable at the top of `scripts/offline_prep.sh` and re-run.
