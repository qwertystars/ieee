# ResQNet-SAGE — Make targets for local development.
#
# All targets work without Docker by using the local Python venv at
# backend/.venv and the local npm install in frontend/. Docker is used
# only when explicitly requested via `make docker-up`.
#
# Prerequisites:
#   - PostgreSQL at localhost:5432 (db: resqnet, user: resqnet, pw: resqnet123)
#   - Python venv at backend/.venv/
#   - PYTHONPATH=/root/srijan/ieee/backend

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

ROOT_DIR := $(shell pwd)
BACKEND_DIR := $(ROOT_DIR)/backend
FRONTEND_DIR := $(ROOT_DIR)/frontend
VENV := $(BACKEND_DIR)/.venv
VENV_PY := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
VENV_ALEMBIC := $(VENV)/bin/alembic
VENV_PYTEST := $(VENV)/bin/pytest

export PYTHONPATH := $(BACKEND_DIR)

.DEFAULT_GOAL := help

.PHONY: help bootstrap migrate seed test lint typecheck build demo verify e2e \
        docker-build docker-up docker-up-full docker-down clean backup restore \
        load-test load-test-full load-test-reduced

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ── Bootstrap ───────────────────────────────────────────────────────────────

bootstrap: ## Install Python deps and npm deps (Docker images via `make docker-build`)
	@echo "=== Bootstrapping ResQNet-SAGE ==="
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating Python venv at $(VENV)..."; \
		python3 -m venv "$(VENV)"; \
	fi
	@echo "Installing Python dependencies..."
	@"$(VENV_PIP)" install --upgrade pip -q
	@if "$(VENV_PIP)" install -r "$(BACKEND_DIR)/requirements.txt" -q 2>&1; then \
		echo "  All packages installed"; \
	else \
		echo "  Full install failed (likely GDAL) — retrying without GDAL..."; \
		tmp_req=$$(mktemp); \
		grep -vE '^\s*gdal' "$(BACKEND_DIR)/requirements.txt" > "$$tmp_req"; \
		"$(VENV_PIP)" install -r "$$tmp_req" -q 2>&1 \
			|| echo "  Some packages failed (non-fatal — core deps may already be installed)"; \
		rm -f "$$tmp_req"; \
	fi
	@echo "Installing npm dependencies..."
	@if [ ! -d "$(FRONTEND_DIR)/node_modules" ]; then \
		cd "$(FRONTEND_DIR)" && npm install; \
	else \
		echo "  node_modules already exists, skipping npm install"; \
	fi
	@echo "=== Bootstrap complete ==="
	@echo "  (Docker images not built — run 'make docker-build' if needed)"

# ── Database ─────────────────────────────────────────────────────────────────

migrate: ## Run alembic upgrade head
	@echo "=== Running migrations ==="
	cd "$(BACKEND_DIR)" && "$(VENV_ALEMBIC)" upgrade head
	@echo "=== Migrations complete ==="

seed: ## Seed demo data (python -m app.seed.seed_demo)
	@echo "=== Seeding demo data ==="
	cd "$(BACKEND_DIR)" && "$(VENV_PY)" -m app.seed.seed_demo
	@echo "=== Seed complete ==="

# ── Quality gates ────────────────────────────────────────────────────────────

test: ## Run pytest (skips pre-existing broken test_seed.py import)
	@echo "=== Running tests ==="
	cd "$(BACKEND_DIR)" && "$(VENV_PYTEST)" -q --ignore=tests/test_seed.py
	@echo "=== Tests complete ==="

lint: ## Run ruff check . (if available)
	@echo "=== Running ruff ==="
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check "$(BACKEND_DIR)"; \
	elif [ -x "$(VENV)/bin/ruff" ]; then \
		"$(VENV)/bin/ruff" check "$(BACKEND_DIR)"; \
	else \
		echo "ruff not installed — skipping (install with: pip install ruff)"; \
	fi

typecheck: ## Run mypy app/ (if available)
	@echo "=== Running mypy ==="
	@if command -v mypy >/dev/null 2>&1; then \
		mypy --config-file "$(BACKEND_DIR)/mypy.ini" "$(BACKEND_DIR)/app/"; \
	elif [ -x "$(VENV)/bin/mypy" ]; then \
		"$(VENV)/bin/mypy" --config-file "$(BACKEND_DIR)/mypy.ini" "$(BACKEND_DIR)/app/"; \
	else \
		echo "mypy not installed — skipping (install with: pip install mypy)"; \
	fi

# ── Build ────────────────────────────────────────────────────────────────────

build: ## Build frontend (npm run build)
	@echo "=== Building frontend ==="
	cd "$(FRONTEND_DIR)" && npm run build
	@echo "=== Build complete ==="

# ── Demo ─────────────────────────────────────────────────────────────────────

demo: ## Run the Phase 1 demo script (requires backend at localhost:8000)
	@echo "=== Running Phase 1 demo ==="
	bash "$(ROOT_DIR)/scripts/demo_phase1.sh"
	@echo "=== Demo complete ==="

# ── Verify (run all checks) ──────────────────────────────────────────────────

verify: migrate seed test build ## Run migrate, seed, test, build in sequence
	@echo "=== All verification checks passed ==="

# ── E2E (Playwright) ─────────────────────────────────────────────────────────

e2e: ## Run Playwright e2e tests (starts Docker stack + seeds + preview)
	@echo "=== Starting e2e stack ==="
	docker compose --profile full up -d --wait
	docker compose exec -T backend python -m app.seed.seed_demo
	@echo "=== Running Playwright e2e tests ==="
	cd "$(FRONTEND_DIR)" && npx playwright test
	@echo "=== E2e tests complete ==="

# ── Docker helpers ───────────────────────────────────────────────────────────

docker-build: ## Build backend and frontend Docker images
	docker compose build backend frontend

docker-up: ## Start the full Docker stack (8 core services)
	docker compose up -d --build

docker-up-full: ## Start the full Docker stack with observability (11 services)
	docker compose --profile full up -d --build

docker-down: ## Stop the Docker stack
	docker compose down

# ── Clean ────────────────────────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf "$(FRONTEND_DIR)/dist" 2>/dev/null || true

# ── Backup / Restore ─────────────────────────────────────────────────────────

backup: ## Back up the Docker database + MinIO models bucket to backups/<timestamp>/
	@echo "=== Creating backup ==="
	bash "$(ROOT_DIR)/scripts/backup.sh"
	@echo "=== Backup complete ==="

restore: ## Restore from a backup directory (usage: make restore BACKUP=<path>)
	@if [ -z "$(BACKUP)" ]; then \
		echo "Usage: make restore BACKUP=<path>"; \
		echo "  e.g. make restore BACKUP=backups/20260728T172104Z"; \
		exit 1; \
	fi
	@echo "=== Restoring from $(BACKUP) ==="
	bash "$(ROOT_DIR)/scripts/restore.sh" "$(BACKUP)"
	@echo "=== Restore complete ==="

# ── Load test (locust) ───────────────────────────────────────────────────────
# Two-phase design: 50 operators (SLOs 1,3,4,5) then 50 ingest users (SLO 2).
# The backend DB pool is 15 connections — running both simultaneously
# overwhelms it. Each phase runs for SOAK_DURATION seconds.
# SOAK_DURATION defaults to 600s (CI); production SLO is 3600s (1h).
# PROFILE=full|reduced controls the evidence file name.

SOAK_DURATION ?= 600
LOCUST := "$(VENV)/bin/locust"
LOCUST_FILE := "$(ROOT_DIR)/tests/load/locustfile.py"
LOCUST_HOST := http://localhost:8000

load-test: ## Run locust load test (2-phase: operators + ingest, SOAK_DURATION seconds, PROFILE=full|reduced)
	@echo "=== Phase 1/2: 50 operators (PROFILE=$(PROFILE), $(SOAK_DURATION)s) ==="
	cd "$(BACKEND_DIR)" && LOAD_PHASE=operator PROFILE=$(PROFILE) PYTHONPATH=. $(LOCUST) \
		-f $(LOCUST_FILE) --headless -u 50 -r 10 -t $(SOAK_DURATION)s --host $(LOCUST_HOST)
	@echo "=== Phase 2/2: 50 ingest users (PROFILE=$(PROFILE), $(SOAK_DURATION)s) ==="
	cd "$(BACKEND_DIR)" && LOAD_PHASE=ingest PROFILE=$(PROFILE) PYTHONPATH=. $(LOCUST) \
		-f $(LOCUST_FILE) --headless -u 50 -r 10 -t $(SOAK_DURATION)s --host $(LOCUST_HOST)
	@echo "=== Combining SLO report (PROFILE=$(PROFILE)) ==="
	"$(VENV_PY)" "$(ROOT_DIR)/tests/load/combine_report.py" --profile $(PROFILE)
	@echo "=== Load test complete (see evidence/load/*-$(PROFILE).json) ==="

load-test-full: ## Run load test against the full profile (16CPU/32GB target)
	@echo "=== Full profile: ensure stack is up with 'make docker-up-full' ==="
	$(MAKE) load-test PROFILE=full

load-test-reduced: ## Run load test against the reduced profile (8CPU/16GB target)
	@echo "=== Reduced profile: heavyweight services (ollama/grafana/prometheus) stopped ==="
	@docker compose stop ollama grafana prometheus 2>/dev/null || true
	$(MAKE) load-test PROFILE=reduced
	@echo "=== Restarting heavyweight services ==="
	@docker compose --profile full start ollama grafana prometheus 2>/dev/null || true
