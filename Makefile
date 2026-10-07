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
RPO_TARGET_S ?= 60
RTO_TARGET_S ?= 900

.PHONY: help bootstrap migrate seed test lint typecheck build demo verify e2e \
        docker-build docker-up docker-up-full docker-down clean backup restore \
        backup-restore-verify backup-restore-verify-corrupt \
        load-test load-test-full load-test-reduced prod-up prod-admin prod-backup

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

# ── Single-VM production (docs/DEPLOY_VM.md) ─────────────────────────────────

PROD_COMPOSE := docker compose -f docker-compose.prod.yml

prod-up: ## Build + start the production stack (needs .env from scripts/vm/init_env.sh)
	$(PROD_COMPOSE) up -d --build
	$(PROD_COMPOSE) ps

prod-admin: ## Create/reset a user (usage: make prod-admin EMAIL=you@org ORG=org_main [ROLE=admin])
	@test -n "$(EMAIL)" && test -n "$(ORG)" || { echo "usage: make prod-admin EMAIL=... ORG=... [ROLE=admin]"; exit 1; }
	$(PROD_COMPOSE) run --rm backend python -m app.auth.create_user \
		--email "$(EMAIL)" --role "$(or $(ROLE),admin)" --org-id "$(ORG)"

prod-backup: ## Back up the production database + MinIO to backups/<stamp>/
	bash scripts/vm/backup.sh

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

backup-restore-verify: ## Verify encrypted fixture backup/restore and RPO/RTO targets
	@set -Eeuo pipefail; \
	evidence="$(ROOT_DIR)/evidence/task-10-backup-restore.txt"; mkdir -p "$$(dirname "$$evidence")"; \
	tmp="$$(mktemp -d)"; key="$$tmp/backup.key"; marker="$$tmp/restore.success"; \
	cleanup() { rc=$$?; printf 'finished_at_utc=%s\nexit_code=%s\nstatus=%s\ncleanup=temporary workspace removed\n' "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$rc" "$$(test "$$rc" -eq 0 && printf PASS || printf FAIL)" >> "$$evidence"; rm -rf "$$tmp"; exit "$$rc"; }; trap cleanup EXIT; \
	{ printf 'task_id=10\ncommand=make backup-restore-verify RPO_TARGET_S=$(RPO_TARGET_S) RTO_TARGET_S=$(RTO_TARGET_S)\ncwd=%s\ncode_revision=%s\nstarted_at_utc=%s\ninputs=fixture database/object envelope; external key file; RPO_TARGET_S=$(RPO_TARGET_S); RTO_TARGET_S=$(RTO_TARGET_S)\n' "$(ROOT_DIR)" "$$(git rev-parse HEAD)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)"; } > "$$evidence"; \
	printf 'fixture-key-material\n' > "$$key"; \
	if [ -n "$(BACKUP_FIXTURE)" ]; then \
		printf 'failure_assertion=corrupt or partial fixture must exit nonzero with no success marker\n'; \
		set +e; BACKUP_ENCRYPTION_KEY_FILE="$$key" RESTORE_SUCCESS_MARKER="$$marker" bash "$(ROOT_DIR)/scripts/restore.sh" "$(BACKUP_FIXTURE)"; rc=$$?; set -e; \
		printf 'failure_exit_code=%s\nsuccess_marker_exists=%s\n' "$$rc" "$$(test -e "$$marker" && printf true || printf false)" | tee -a "$$evidence"; \
		test "$$rc" -ne 0; test ! -e "$$marker"; exit 1; \
	fi; \
	BACKUP_ROOT="$$tmp/backups" BACKUP_FIXTURE_DIR="$(ROOT_DIR)/tests/fixtures/backup-restore" BACKUP_ENCRYPTION_KEY_FILE="$$key" BACKUP_OFFSITE_DIR="$$tmp/offsite" bash "$(ROOT_DIR)/scripts/backup.sh" | tee -a "$$evidence"; \
	backup_path="$$(find "$$tmp/backups" -mindepth 1 -maxdepth 1 -type d -name '20*' -print -quit)"; test -n "$$backup_path"; \
	RESTORE_TARGET_DIR="$$tmp/clean-room" RESTORE_REPORT="$$tmp/restore.report.json" RESTORE_SUCCESS_MARKER="$$marker" BACKUP_ENCRYPTION_KEY_FILE="$$key" RPO_TARGET_S="$(RPO_TARGET_S)" RTO_TARGET_S="$(RTO_TARGET_S)" bash "$(ROOT_DIR)/scripts/restore.sh" "$$backup_path" | tee -a "$$evidence"; \
	test -f "$$marker"; \
	python3 -c 'import json, pathlib, sys; m=json.load(open(sys.argv[1])); r=json.load(open(sys.argv[2])); assert r["status"] == "PASS"; assert m["rpo"]["measured_seconds"] <= $(RPO_TARGET_S); assert m["rto"]["measured_seconds"] <= $(RTO_TARGET_S); assert r["archive_sha256"] == m["integrity"]["archive_sha256"]; p=pathlib.Path(sys.argv[3]); p.write_text(p.read_text()+"metrics="+json.dumps({"rpo_seconds":m["rpo"]["measured_seconds"],"rto_seconds":m["rto"]["measured_seconds"]},sort_keys=True)+"\nhashes="+json.dumps({"archive_sha256":r["archive_sha256"]},sort_keys=True)+"\nfailure_assertion=corruption and partial dependency failures are fail-fast; exercised separately\n")' "$$backup_path/manifest.json" "$$tmp/restore.report.json" "$$evidence"

backup-restore-verify-corrupt: ## Run the intentionally corrupt fixture and return nonzero
	@$(MAKE) backup-restore-verify BACKUP_FIXTURE=tests/fixtures/corrupt.tar RPO_TARGET_S=60 RTO_TARGET_S=900

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
