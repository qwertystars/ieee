#!/usr/bin/env bash
# offline_prep_lib.sh — Helper functions for offline_prep.sh.
# Keeps the main script under 250 LOC by centralizing logging, download,
# and step-runner utilities here.

# ── Logging ──────────────────────────────────────────────────────────────────
log_info()    { echo "  $*"; }
log_warn()    { echo "  WARNING: $*" >&2; }
log_error()   { echo "  ERROR: $*" >&2; }
log_success() { echo "  OK: $*"; }

# ── Filesystem ──────────────────────────────────────────────────────────────
ensure_dir() { mkdir -p "$1"; }

# ── Command availability ────────────────────────────────────────────────────
check_command()   { command -v "$1" >/dev/null 2>&1; }
check_python_pkg() { python3 -c "import $1" 2>/dev/null; }

# ── Idempotent file download ────────────────────────────────────────────────
# Usage: download_file <url> <dest>
# Returns 0 if file already cached or download succeeds, 1 on failure.
download_file() {
    local url="$1" dest="$2"
    if [[ -f "$dest" && -s "$dest" ]]; then
        log_info "Already cached: $(basename "$dest")"
        return 0
    fi
    ensure_dir "$(dirname "$dest")"
    if curl -fL --retry 3 --retry-delay 5 --connect-timeout 30 \
            -o "$dest.tmp" "$url" 2>/dev/null; then
        mv "$dest.tmp" "$dest"
        log_success "Downloaded: $(basename "$dest")"
        return 0
    else
        rm -f "$dest.tmp"
        return 1
    fi
}

# ── Directory non-empty check ───────────────────────────────────────────────
dir_has_files() {
    [[ -d "$1" && -n "$(ls -A "$1" 2>/dev/null)" ]]
}

# ── Step runner ──────────────────────────────────────────────────────────────
# Usage: run_step <num> <total> <name> <function> [args...]
run_step() {
    local num="$1" total="$2" name="$3"
    shift 3
    echo ""
    echo "[$num/$total] $name"
    "$@"
}

# ── Wait for a Docker Compose service to be healthy ──────────────────────────
# Usage: wait_for_service <service> [max_attempts]
wait_for_service() {
    local service="$1" max="${2:-30}" i=0
    while (( i < max )); do
        if docker compose exec "$service" true >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        ((i++))
    done
    return 1
}
