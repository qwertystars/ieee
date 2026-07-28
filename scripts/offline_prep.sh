#!/usr/bin/env bash
# offline_prep.sh — Download and cache ALL assets so the system works offline.
#
# After running this script, `docker compose down && docker compose up -d --wait`
# starts every service with NO internet, and
# `curl http://localhost:8000/healthz` returns {"ok":true}.
#
# The script is idempotent (skip if already done) and resilient (log warnings
# on individual download failures, never exit non-zero for non-fatal errors).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=offline_prep_lib.sh
source "$SCRIPT_DIR/offline_prep_lib.sh"

cd "$ROOT_DIR"

# ── Paths ───────────────────────────────────────────────────────────────────
MODELS_CACHE="$ROOT_DIR/backend/models/cache"
VENDOR_PIP="$ROOT_DIR/backend/vendor"
DATA_DIR="$ROOT_DIR/backend/data"
BASEMAPS_DIR="$ROOT_DIR/frontend/public/basemaps"
TOTAL=12

# ── Model URLs (base pretrained weights only — NOT fine-tuned) ───────────────
DOFA_URL="https://huggingface.co/XShadow/DOFA/resolve/main/DOFA_V1.pth"
RESNET50_S1_URL="https://huggingface.co/torchgeo/resnet50_sentinel1_rgb/resolve/main/resnet50_sentinel1_rgb-1c8ed8c1.pth"
CLAY_URL="https://huggingface.co/made-with-clay/Clay/resolve/main/clay-v1-base.ckpt"
TERRAMIND_URL="https://huggingface.co/ibm-nasa-geospatial/TerraMind/resolve/main/terramind_v1_base.pth"
NER_URL="https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1.tar.gz"
SAR_SAMPLE_URL="https://raw.githubusercontent.com/rasterio/rasterio/main/tests/data/RGB.byte.tif"

# ── Step 1: Download ML model base pretrained weights ───────────────────────
step_01_models() {
    ensure_dir "$MODELS_CACHE"
    download_file "$DOFA_URL"        "$MODELS_CACHE/dofa_base.pth"      || log_warn "DOFA weights unavailable"
    download_file "$RESNET50_S1_URL" "$MODELS_CACHE/resnet50_s1_base.pth" || log_warn "ResNet50 S1 weights unavailable"
    download_file "$CLAY_URL"        "$MODELS_CACHE/clay_base.ckpt"     || log_warn "Clay weights unavailable"
    download_file "$TERRAMIND_URL"   "$MODELS_CACHE/terramind_base.pth"  || log_warn "TerraMind weights unavailable"
}

# ── Step 2: Generate PMTiles basemap ───────────────────────────────────────
# Mumbai bounding box (lon_min,lat_min,lon_max,lat_max) — matches the simulator
# waypoints in backend/app/simulator/scenarios.py (lon≈72.85, lat≈19.07) and
# the locked decision D6 (demo region = Mumbai).
MUMBAI_BBOX="72.7,18.9,73.0,19.3"
step_02_pmtiles() {
    local out="$BASEMAPS_DIR/mumbai.pmtiles"
    if [[ -f "$out" && -s "$out" ]]; then
        log_info "PMTiles already generated: $out"
        return 0
    fi
    if ! check_command tippecanoe; then
        log_warn "tippecanoe not installed — skipping PMTiles generation"
        log_info "Install: https://github.com/felt/tippecanoe"
        return 0
    fi
    ensure_dir "$BASEMAPS_DIR"
    local tmp_geojson="$BASEMAPS_DIR/mumbai.geojson"
    # OSM extract for the Mumbai bounding box via Overpass API. The bbox
    # query is preferred over `area[name="Mumbai"]` because area lookups
    # are flaky for the Mumbai administrative boundary and frequently
    # return empty results or rate-limit. The bbox covers Greater Mumbai.
    # Query is limited to basemap-relevant features (highways, buildings,
    # water, landuse) — querying all elements for a city of 20M people
    # always times out.
    local overpass="[out:json][timeout:120][bbox:${MUMBAI_BBOX}];(way[\"highway\"];way[\"building\"];way[\"natural\"=\"water\"];way[\"waterway\"];way[\"landuse\"];way[\"leisure\"];);out geom;"
    local overpass_url="https://overpass-api.de/api/interpreter?data=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$overpass")"
    if curl -fL --retry 3 --connect-timeout 30 --max-time 300 -o "$tmp_geojson" "$overpass_url" 2>/dev/null; then
        if tippecanoe -o "$out" -zg \
                --layer=mumbai \
                --drop-densest-as-needed \
                --extend-zooms-if-still-dropping \
                --force "$tmp_geojson" 2>/dev/null; then
            log_success "Generated PMTiles: $out"
        else
            log_warn "tippecanoe failed — PMTiles not generated"
        fi
        rm -f "$tmp_geojson"
    else
        log_warn "Overpass API unavailable — falling back to Geofabrik Mumbai extract"
        # Geofabrik fallback: download the India western-zone extract (~200 MB)
        # and filter to the Mumbai bbox using osmium + tippecanoe. Requires
        # osmium-tool (apt-get install osmium-tool on Debian/Ubuntu).
        local geofabrik_url="https://download.geofabrik.de/asia/india/western-zone-latest.osm.pbf"
        local tmp_pbf="$BASEMAPS_DIR/western-zone-latest.osm.pbf"
        local tmp_mumbai_pbf="$BASEMAPS_DIR/mumbai.osm.pbf"
        if curl -fL --retry 2 --connect-timeout 30 --max-time 600 -o "$tmp_pbf" "$geofabrik_url" 2>/dev/null; then
            if check_command osmium; then
                if osmium extract --bbox="${MUMBAI_BBOX}" -o "$tmp_mumbai_pbf" "$tmp_pbf" 2>/dev/null \
                        && osmium export -o "$tmp_geojson" "$tmp_mumbai_pbf" 2>/dev/null; then
                    if tippecanoe -o "$out" -zg \
                            --layer=mumbai \
                            --drop-densest-as-needed \
                            --extend-zooms-if-still-dropping \
                            --force "$tmp_geojson" 2>/dev/null; then
                        log_success "Generated PMTiles from Geofabrik extract: $out"
                    else
                        log_warn "tippecanoe failed on Geofabrik extract — PMTiles not generated"
                    fi
                else
                    log_warn "osmium extract/export failed — PMTiles not generated"
                fi
            else
                log_warn "osmium not installed — install with 'apt-get install osmium-tool' to use Geofabrik fallback"
            fi
            rm -f "$tmp_pbf" "$tmp_mumbai_pbf" "$tmp_geojson"
        else
            log_warn "Geofabrik extract also unavailable — PMTiles not generated (no Mumbai OSM data)"
        fi
    fi
}

# ── Step 3: Build custom Docker images ──────────────────────────────────────
step_03_build_images() {
    docker build -t resqnet-db -f Dockerfile.db . || log_warn "DB image build failed"
    docker compose build backend frontend || log_warn "Backend/frontend image build failed"
}

# ── Step 4: Pre-pull all Docker images ──────────────────────────────────────
# Use --profile full so ollama, prometheus, and grafana images are pre-pulled
# too. Without the profile flag, docker compose pull skips profile-gated
# services, leaving them to be pulled on-demand at start time (slow).
step_04_pull_images() {
    docker compose --profile full pull || log_warn "Some Docker images failed to pull"
}

# ── Step 5: Vendor pip packages ────────────────────────────────────────────
step_05_vendor_pip() {
    ensure_dir "$VENDOR_PIP"
    if dir_has_files "$VENDOR_PIP"; then
        log_info "pip vendor directory already populated"
        return 0
    fi
    # Try full download first; if GDAL build fails, retry without it.
    if pip download -r backend/requirements.txt -d "$VENDOR_PIP" 2>&1; then
        log_success "All pip packages vendored"
    else
        log_warn "Full pip download failed (likely GDAL) — retrying without GDAL"
        local tmp_req
        tmp_req="$(mktemp)"
        grep -vE '^\s*gdal' backend/requirements.txt > "$tmp_req"
        pip download -r "$tmp_req" -d "$VENDOR_PIP" 2>&1 \
            || log_warn "Some pip packages still failed to download"
        rm -f "$tmp_req"
    fi
}

# ── Step 6: Vendor npm packages ────────────────────────────────────────────
step_06_vendor_npm() {
    if [[ -f frontend/package-lock.json ]]; then
        log_info "package-lock.json already exists"
    else
        (cd frontend && npm install --package-lock-only) || log_warn "npm package-lock generation failed"
    fi
    if [[ -d frontend/node_modules ]]; then
        log_info "node_modules already populated"
    else
        (cd frontend && npm install) || log_warn "npm install failed"
    fi
}

# ── Step 7: Download sample Sentinel-1 scene ───────────────────────────────
step_07_sample_sar() {
    local sar_dir="$DATA_DIR/sample-sar"
    ensure_dir "$sar_dir"
    download_file "$SAR_SAMPLE_URL" "$sar_dir/sample.tif" \
        || log_warn "Sample SAR scene download failed (placeholder GeoTIFF used as fallback)"
}

# ── Step 8: Pull Ollama model ───────────────────────────────────────────────
step_08_ollama() {
    if ! docker compose up -d ollama 2>/dev/null; then
        log_warn "Could not start ollama service"
        return 0
    fi
    # Wait for the ollama HTTP server to respond, not just the container.
    # wait_for_service only checks that `docker compose exec` succeeds (container
    # running), but the ollama server inside takes a few more seconds to accept
    # API requests. Without this, `ollama pull` can race the server startup.
    local i=0
    while (( i < 30 )); do
        if docker compose exec ollama ollama list >/dev/null 2>&1; then
            break
        fi
        sleep 2
        ((i++))
    done
    if (( i >= 30 )); then
        log_warn "Ollama server did not become ready in time"
        return 0
    fi
    if docker compose exec ollama ollama list 2>/dev/null | grep -q "llama3.1:8b"; then
        log_info "llama3.1:8b already pulled"
        return 0
    fi
    docker compose exec ollama ollama pull llama3.1:8b \
        || log_warn "Ollama model pull failed (llama3.1:8b)"
}

# ── Step 9: Download Whisper model ──────────────────────────────────────────
step_09_whisper() {
    local whisper_dir="$MODELS_CACHE/whisper"
    if dir_has_files "$whisper_dir"; then
        log_info "Whisper model already cached"
        return 0
    fi
    ensure_dir "$whisper_dir"
    if check_python_pkg whisper; then
        python3 -c "import whisper; whisper.load_model('base', download_root='$whisper_dir')" \
            || log_warn "Whisper model download failed"
    else
        log_warn "whisper package not installed — skipping (install with: pip install openai-whisper)"
    fi
}

# ── Step 10: Download NER model ─────────────────────────────────────────────
step_10_ner() {
    local ner_dir="$MODELS_CACHE/ner"
    if dir_has_files "$ner_dir"; then
        log_info "NER model already cached"
        return 0
    fi
    ensure_dir "$ner_dir"
    download_file "$NER_URL" "$ner_dir/en_core_web_sm-3.7.1.tar.gz" \
        || log_warn "NER model (en_core_web_sm) download failed"
}

# ── Step 11: Verify resource limits in docker-compose.yml ───────────────────
step_11_verify_limits() {
    if grep -q "deploy:" docker-compose.yml && grep -q "limits:" docker-compose.yml; then
        log_success "docker-compose.yml has deploy.resources.limits"
    else
        log_warn "docker-compose.yml missing deploy.resources.limits — add manually"
    fi
}

# ── Step 12: Verify docs exist ──────────────────────────────────────────────
step_12_verify_docs() {
    if [[ -f docs/offline-prep.md ]]; then
        log_success "docs/offline-prep.md exists"
    else
        log_warn "docs/offline-prep.md missing"
    fi
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    echo "=== ResQNet-SAGE Offline Preparation ==="
    echo "Root: $ROOT_DIR"
    echo "Steps: $TOTAL"
    run_step 1  $TOTAL "Downloading ML model weights..."        step_01_models
    run_step 2  $TOTAL "Generating PMTiles basemap..."         step_02_pmtiles
    run_step 3  $TOTAL "Building custom Docker images..."       step_03_build_images
    run_step 4  $TOTAL "Pre-pulling Docker images..."           step_04_pull_images
    run_step 5  $TOTAL "Vendoring pip packages..."              step_05_vendor_pip
    run_step 6  $TOTAL "Vendoring npm packages..."              step_06_vendor_npm
    run_step 7  $TOTAL "Downloading sample SAR scene..."        step_07_sample_sar
    run_step 8  $TOTAL "Pulling Ollama model..."                step_08_ollama
    run_step 9  $TOTAL "Downloading Whisper model..."           step_09_whisper
    run_step 10 $TOTAL "Downloading NER model..."               step_10_ner
    run_step 11 $TOTAL "Verifying resource limits..."           step_11_verify_limits
    run_step 12 $TOTAL "Verifying docs..."                      step_12_verify_docs
    echo ""
    echo "=== Offline preparation complete ==="
    echo "Verify: docker compose down && docker compose up -d --wait"
    echo "        curl -s http://localhost:8000/healthz"
}

main "$@"
