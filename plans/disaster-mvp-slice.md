# Disaster MVP Slice

## TL;DR
> Summary:      Implement the smallest end-to-end disaster response loop: demo login, seeded Rivertown incident data, field responder report/road/task updates, and command-center dashboard/map visibility.
> Deliverables:
> - Minimal authenticated demo stack with idempotent seed data.
> - Backend APIs for events, reports, roads, teams, tasks, dashboard/map layers, shelters, recommendations, alerts, and text situation reports.
> - Frontend/backend contract alignment so `/dashboard` and `/field` work against real APIs.
> - Pytest coverage, frontend build checks, and real Chrome Playwright scenarios with evidence.
> Effort:       Large
> Risk:         Medium - GeoAlchemy/PostGIS geometry serialization and existing frontend/backend contract drift.

## Scope
### Must have
- Demo users can sign in with password `demo1234`, matching the documented accounts in `README.md:29-31` and the login defaults in `frontend/src/pages/Login.tsx:11-12`.
- `python -m app.seed.seed_demo` creates an idempotent Rivertown flood event with at least: one active event, six demo users, two roads, one response team, one shelter, one task, one priority area, one recommendation, and one initial incident report.
- The command-center `/dashboard` route can load events, dashboard summary, map layers, recommendations, alerts, shelters, teams, and text situation-report export without 404s.
- The field-responder `/field` route can select a team, list assigned tasks, submit a quick incident report, mark a road blocked/open/dangerous, update task status, and share team location.
- New report, report verification, road status, team location, and task status mutations write audit rows and emit the existing realtime event types from `backend/app/realtime/events.py:15-27`.
- Backend tests use FastAPI `TestClient` and dependency overrides following official FastAPI testing guidance, with focused PostGIS-backed integration tests where geometry is persisted.
- Frontend types and API expectations match the backend payloads used by the MVP slice.
- Manual QA is agent-executed through curl and real Chrome Playwright, with artifacts under `evidence/`.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not implement the full ingestion, deduplication, assessment, recommendation, routing, shelter allocation, alerts engine, worker scheduler, or PDF generator; those are explicitly broader stubs in `DESIGN.md:149-178` and `backend/app/seed/seed_demo.py:1-9`.
- Do not edit `backend/app/main.py` or `backend/app/api/router.py`; the design contract says feature workers add behavior inside route modules, not the wiring files (`DESIGN.md:76-82`, `backend/app/main.py:1-5`, `backend/app/api/router.py:1-5`).
- Do not introduce external routing services, OSRM, Celery, map tile keys, AI analysis, social-media ingestion, or real notification delivery.
- Do not add a landing page, hero page, decorative redesign, or unrelated UI overhaul; preserve the existing dense operational dashboard/field-responder surfaces in `frontend/src/pages/Dashboard.tsx:179-339` and `frontend/src/pages/FieldResponder.tsx:167-271`.
- Do not require a human to manually verify anything; every acceptance criterion and QA scenario must be executable by an agent.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: TDD + `pytest` for backend, `npm run build` for frontend type/build checks, and Playwright real Chrome for browser flows.
- QA policy: every task has agent-executed scenarios
- Evidence: `evidence/task-<N>-<slug>.<ext>`

## Execution strategy
### Parallel execution waves
> Target 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks to maximize parallelism.

Wave 1 (no dependencies):
- Task 1: Backend MVP test foundation and geometry utilities
- Task 2: API contract alignment for dashboard, map layers, and enums
- Task 3: Demo auth endpoints
- Task 4: Idempotent Rivertown seed and fixture factories
- Task 5: Events API

Wave 2 (after Wave 1):
- Task 6: Incident reports API and report verification, depends [1, 3, 4, 5]
- Task 7: Roads and teams APIs, depends [1, 3, 4, 5]
- Task 8: Tasks API and status transitions, depends [1, 3, 4, 5, 7]
- Task 9: Dashboard summary and map-layer APIs, depends [1, 2, 4, 5, 6, 7, 8]
- Task 10: Command-center side-panel APIs and text situation report, depends [1, 2, 4, 5, 7, 8]

Wave 3 (after Wave 2):
- Task 11: Frontend API/type integration, depends [2, 6, 7, 8, 9, 10]
- Task 12: Field responder mutation invalidation and UI flow hardening, depends [6, 7, 8, 11]
- Task 13: Real Chrome Playwright MVP scenario harness, depends [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

Critical path: Task 1 -> Task 4 -> Task 5 -> Task 6 -> Task 9 -> Task 11 -> Task 13

### Dependency matrix
| Task | Depends on | Blocks | Can parallelize with |
|------|------------|--------|----------------------|
| 1    | none       | 6, 7, 8, 9, 10 | 2, 3, 4, 5 |
| 2    | none       | 9, 10, 11 | 1, 3, 4, 5 |
| 3    | none       | 6, 7, 8, 13 | 1, 2, 4, 5 |
| 4    | none       | 6, 7, 8, 9, 10, 13 | 1, 2, 3, 5 |
| 5    | none       | 6, 7, 8, 9, 10, 13 | 1, 2, 3, 4 |
| 6    | 1, 3, 4, 5 | 9, 11, 12, 13 | 7, 8, 10 |
| 7    | 1, 3, 4, 5 | 8, 9, 10, 11, 12, 13 | 6 |
| 8    | 1, 3, 4, 5, 7 | 9, 10, 11, 12, 13 | 6, 10 |
| 9    | 1, 2, 4, 5, 6, 7, 8 | 11, 13 | 10 |
| 10   | 1, 2, 4, 5, 7, 8 | 11, 13 | 9 |
| 11   | 2, 6, 7, 8, 9, 10 | 12, 13 | none |
| 12   | 6, 7, 8, 11 | 13 | none |
| 13   | 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 | final verification | none |

## Todos
> Implementation + Test = ONE task. Never separate.
> Every task MUST have: References + Acceptance Criteria + QA Scenarios + Commit.

- [ ] 1. Backend MVP test foundation and geometry utilities

  What to do: Add backend test fixtures and shared helpers so later route tasks can run against an isolated database session and convert GeoJSON to/from GeoAlchemy/PostGIS safely. Create focused tests first for Point/LineString/Polygon round trips, bbox parsing, pagination defaults, and response JSON shape. Prefer a small `backend/app/api/geo.py` or similarly named helper module used by route modules; keep it under 250 pure LOC.
  Must NOT do: Do not change model definitions, Alembic wiring, `main.py`, or `api/router.py`. Do not fake geometry by returning strings from persisted models.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [6, 7, 8, 9, 10] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `backend/tests/test_boot.py:4` - existing FastAPI `TestClient` smoke-test pattern.
  - Pattern:  `backend/app/db.py:22` - canonical `get_db()` dependency to override in tests.
  - Pattern:  `backend/app/deps.py:19` - pagination dependency and `parse_bbox` behavior to harden.
  - API/Type: `backend/app/schemas/common.py:17` - API geometry must be GeoJSON in EPSG:4326.
  - API/Type: `backend/app/models/infrastructure.py:57` - persisted road geometry is a PostGIS LineString.
  - External: `https://fastapi.tiangolo.com/tutorial/testing/` - `TestClient` and pytest usage.
  - External: `https://fastapi.tiangolo.com/advanced/testing-dependencies/` - dependency overrides for test isolation.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_mvp_foundation.py -q`
  - [ ] `test -f evidence/task-1-foundation-red.txt && test -f evidence/task-1-foundation-green.txt`
  - [ ] `python - <<'PY'\nfrom app.deps import parse_bbox\nassert parse_bbox.__name__ == 'parse_bbox'\nPY`

  QA scenarios (MANDATORY - task incomplete without these):
  > Name the exact tool AND its exact invocation - not "verify it works". Browser use: use Chrome to drive the page; if Chrome is not available, download and use agent-browser (https://github.com/vercel-labs/agent-browser). Computer use: OS-level GUI automation for a non-browser desktop app.
  ```
  Scenario: geometry helper round-trips GeoJSON fixtures
    Tool:     bash
    Steps:    mkdir -p evidence && cd backend && pytest tests/test_mvp_foundation.py -q | tee ../evidence/task-1-foundation.txt
    Expected: pytest exits 0 and output includes all tests in tests/test_mvp_foundation.py passing.
    Evidence: evidence/task-1-foundation.txt

  Scenario: invalid bbox is rejected deterministically by helper tests
    Tool:     bash
    Steps:    mkdir -p evidence && cd backend && pytest tests/test_mvp_foundation.py::test_invalid_bbox_rejected_or_reported -q | tee ../evidence/task-1-foundation-error.txt
    Expected: pytest exits 0 and asserts invalid bbox input does not silently broaden a query.
    Evidence: evidence/task-1-foundation-error.txt
  ```

  Commit: YES | Message: `test(backend): add mvp integration foundation` | Files: [`backend/tests/conftest.py`, `backend/tests/test_mvp_foundation.py`, `backend/app/api/geo.py`, `backend/app/deps.py`]

- [ ] 2. API contract alignment for dashboard, map layers, and enums

  What to do: Create a single MVP contract that both backend and frontend use. Align `backend/app/schemas/dashboard.py`, `frontend/src/types.ts`, and any route response models with the fields the current UI reads: dashboard summary keys from `DashboardSummaryBar`, array-shaped `MapLayersResponse` expected by `MapView`, and enum values from backend `app.models.enums`. Add tests or type checks that catch the current mismatches (`medical_emergency` vs `medical`, `automated_sensor` vs `sensor`, frontend dashboard keys vs backend schema keys).
  Must NOT do: Do not broaden the MVP by adding new domain enum values to the backend unless the database enum migration is also planned and tested. Prefer aligning frontend to the existing backend contract for this slice.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [9, 10, 11] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - API/Type: `backend/app/models/enums.py:48` - backend reporter types are `citizen`, `field_responder`, `sensor`, `official`.
  - API/Type: `backend/app/models/enums.py:55` - backend report category uses `medical`, not `medical_emergency`.
  - API/Type: `backend/app/models/enums.py:89` - backend recommendation types differ from frontend names.
  - API/Type: `backend/app/models/enums.py:118` - backend team types differ from frontend names.
  - API/Type: `backend/app/schemas/dashboard.py:10` - current backend summary schema does not match frontend summary fields.
  - API/Type: `frontend/src/types.ts:14` - current frontend enum definitions drift from backend enum definitions.
  - Pattern:  `frontend/src/components/panels/DashboardSummaryBar.tsx:33` - UI reads `critical_areas`, `high_areas`, `pending_tasks`, `roads_blocked`, and `alerts_active`.
  - Pattern:  `frontend/src/components/Map/MapView.tsx:217` - map expects arrays for `areas`, `observations`, `roads`, `reports`, `shelters`, and `teams`.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_api_contract.py -q`
  - [ ] `cd frontend && npm run build`
  - [ ] `! rg -n "medical_emergency|automated_sensor|rescue_operation|shelter_activation|road_closure|resource_deployment|medical_response|utility_shutdown|engineering|coordination" frontend/src`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: frontend and backend contract checks pass
    Tool:     bash
    Steps:    mkdir -p evidence && (cd backend && pytest tests/test_api_contract.py -q) | tee evidence/task-2-contract.txt && (cd frontend && npm run build) | tee -a evidence/task-2-contract.txt
    Expected: both commands exit 0 and no TypeScript or pytest contract mismatch is reported.
    Evidence: evidence/task-2-contract.txt

  Scenario: old mismatched enum literals are absent from frontend source
    Tool:     bash
    Steps:    mkdir -p evidence && if rg -n "medical_emergency|automated_sensor|engineering|coordination" frontend/src > evidence/task-2-contract-error.txt; then exit 1; else echo "no stale enum literals" > evidence/task-2-contract-error.txt; fi
    Expected: command exits 0 and evidence says no stale enum literals.
    Evidence: evidence/task-2-contract-error.txt
  ```

  Commit: YES | Message: `fix(contract): align mvp api payload types` | Files: [`backend/app/schemas/dashboard.py`, `backend/tests/test_api_contract.py`, `frontend/src/types.ts`, `frontend/src/components/field/QuickReportForm.tsx`]

- [ ] 3. Demo auth endpoints

  What to do: Implement `POST /api/auth/login`, `GET /api/auth/me`, and `POST /api/auth/logout` in `backend/app/auth/router.py`. Accept `application/x-www-form-urlencoded` username/password because the frontend sends `URLSearchParams` in `frontend/src/api/client.ts:88-93`. Use existing password/JWT helpers from `backend/app/auth/security.py:19-42` and existing current-user dependency in `backend/app/auth/deps.py:21-33`. Add tests for successful login, invalid credentials, bearer token `/me`, and missing bearer token.
  Must NOT do: Do not add registration, password reset, refresh tokens, OAuth providers, cookies, or production-grade session revocation. Logout may be stateless for the MVP.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [6, 7, 8, 13] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `backend/app/auth/router.py:1` - auth router stub mounted at `/api/auth`.
  - API/Type: `backend/app/schemas/auth.py:9` - login/token response schemas.
  - API/Type: `backend/app/models/user.py:15` - user model and hashed password field.
  - Pattern:  `frontend/src/auth/AuthContext.tsx:45` - frontend logs in, stores access token, then calls `/auth/me`.
  - Pattern:  `frontend/src/api/client.ts:87` - frontend auth client paths and form encoding.
  - External: `https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/` - form username/password with bearer-token response.
  - External: `https://fastapi.tiangolo.com/tutorial/request-forms/` - FastAPI form-data request handling.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_auth_api.py -q`
  - [ ] `cd backend && pytest tests/test_boot.py::test_openapi_loads -q`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: demo user can log in and call /auth/me
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose up -d db backend && docker compose exec -T backend python -m app.seed.seed_demo && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=emergency_manager@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && curl -i http://localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN" | tee evidence/task-3-auth.txt
    Expected: response status is HTTP/1.1 200 OK and body contains emergency_manager@demo.disaster.
    Evidence: evidence/task-3-auth.txt

  Scenario: invalid credentials fail without issuing a token
    Tool:     bash
    Steps:    mkdir -p evidence && curl -i -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=emergency_manager@demo.disaster&password=wrong' | tee evidence/task-3-auth-error.txt
    Expected: response status is HTTP/1.1 401 Unauthorized and body contains {"detail":"Invalid credentials"}.
    Evidence: evidence/task-3-auth-error.txt
  ```

  Commit: YES | Message: `feat(auth): add demo bearer login endpoints` | Files: [`backend/app/auth/router.py`, `backend/tests/test_auth_api.py`]

- [ ] 4. Idempotent Rivertown seed and fixture factories

  What to do: Implement `backend/app/seed/seed_demo.py` as an idempotent seed command and expose reusable seed/factory helpers for tests. It must create the documented demo users, a Rivertown active flood event, roads, a shelter, a response team, one assigned task, one priority area, one recommendation, and one initial report. Print a deterministic JSON summary of created/updated counts so QA can assert behavior. Run the seed twice in tests to prove no duplicate rows.
  Must NOT do: Do not seed the full 15-report demo or build the complete analysis/recommendation scenario from `DESIGN.md:213-220`; this MVP seed is intentionally smaller.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [6, 7, 8, 9, 10, 13] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `README.md:25` - documented seed command.
  - Pattern:  `README.md:29` - demo accounts and password.
  - Pattern:  `backend/app/seed/seed_demo.py:1` - current seed stub.
  - API/Type: `backend/app/models/event.py:17` - disaster event model.
  - API/Type: `backend/app/models/observation.py:51` - incident report model.
  - API/Type: `backend/app/models/infrastructure.py:16` - shelter model and available-capacity property.
  - API/Type: `backend/app/models/response.py:16` - response team model.
  - API/Type: `backend/app/models/response.py:35` - task model.
  - API/Type: `backend/app/models/assessment.py:21` - priority area model.
  - API/Type: `backend/app/models/assessment.py:55` - recommendation model.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_seed_demo.py -q`
  - [ ] `docker compose exec -T backend python -m app.seed.seed_demo | python -m json.tool`
  - [ ] Running the seed twice leaves exactly six demo users and one active Rivertown event.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: seed creates MVP demo data
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose up -d db backend && docker compose exec -T backend python -m app.seed.seed_demo | tee evidence/task-4-seed.txt
    Expected: command exits 0 and JSON output includes "event":"Rivertown Urban Flood", "users":6, "roads" at least 2, "teams" at least 1, and "tasks" at least 1.
    Evidence: evidence/task-4-seed.txt

  Scenario: seed is idempotent
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose exec -T backend python -m app.seed.seed_demo >/dev/null && docker compose exec -T backend python -m app.seed.seed_demo | tee evidence/task-4-seed-error.txt
    Expected: command exits 0 and JSON output reports no duplicate active Rivertown event or duplicate demo users.
    Evidence: evidence/task-4-seed-error.txt
  ```

  Commit: YES | Message: `feat(seed): add deterministic rivertown mvp data` | Files: [`backend/app/seed/seed_demo.py`, `backend/tests/test_seed_demo.py`]

- [ ] 5. Events API

  What to do: Implement `GET /api/events`, `POST /api/events`, `GET /api/events/{id}`, and `PATCH /api/events/{id}` inside `backend/app/api/routes/events.py`. Use `DisasterEventCreate`, `DisasterEventUpdate`, and `DisasterEventRead`; support `limit`/`offset`; return 404 for unknown IDs; write audit entries for create/update when an authenticated user is available. Add tests for list, create, patch, pagination, and missing event.
  Must NOT do: Do not add event deletion, archived-event policy, complex spatial filtering, or changes to global route registration.

  Parallelization: Can parallel: YES | Wave 1 | Blocks: [6, 7, 8, 9, 10, 13] | Blocked by: []

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `backend/app/api/routes/events.py:1` - route stub to fill.
  - API/Type: `DESIGN.md:190` - event route surface.
  - API/Type: `backend/app/schemas/event.py:13` - event create/update/read schemas.
  - API/Type: `backend/app/models/event.py:17` - event model fields.
  - Pattern:  `backend/app/deps.py:19` - pagination dependency.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:40` - dashboard needs event list and auto-selects first active event.
  - Pattern:  `frontend/src/pages/FieldResponder.tsx:71` - field responder discovers an active event.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_events_api.py -q`
  - [ ] `cd backend && pytest tests/test_boot.py -q`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: seeded active event is listed
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose up -d db backend && docker compose exec -T backend python -m app.seed.seed_demo && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=emergency_manager@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && curl -i 'http://localhost:8000/api/events?limit=10&offset=0' -H "Authorization: Bearer $TOKEN" | tee evidence/task-5-events.txt
    Expected: response status is HTTP/1.1 200 OK and body contains Rivertown Urban Flood with status active.
    Evidence: evidence/task-5-events.txt

  Scenario: unknown event returns 404
    Tool:     bash
    Steps:    mkdir -p evidence && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=emergency_manager@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && curl -i http://localhost:8000/api/events/00000000-0000-0000-0000-000000000000 -H "Authorization: Bearer $TOKEN" | tee evidence/task-5-events-error.txt
    Expected: response status is HTTP/1.1 404 Not Found and body contains {"detail":"Event not found"}.
    Evidence: evidence/task-5-events-error.txt
  ```

  Commit: YES | Message: `feat(events): expose event lifecycle api` | Files: [`backend/app/api/routes/events.py`, `backend/tests/test_events_api.py`]

- [ ] 6. Incident reports API and report verification

  What to do: Implement `GET /api/events/{event_id}/reports`, `POST /api/events/{event_id}/reports`, `GET /api/reports/{id}`, and `PATCH /api/reports/{id}/verify` in `backend/app/api/routes/reports.py`. Force the stored `event_id` from the path, reject body/path event mismatches, require Point geometry on create, default verification to `unverified`, assign a deterministic confidence score when omitted, write audit entries, and emit `new_report` / `report_verified` events. Add tests for list/create/get/verify, event mismatch, invalid geometry, and unknown report.
  Must NOT do: Do not implement photo upload, PII redaction pipeline, report clustering, or automated verification; store `photo_url` only.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [9, 11, 12, 13] | Blocked by: [1, 3, 4, 5]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `backend/app/api/routes/reports.py:1` - route stub to fill.
  - API/Type: `DESIGN.md:193` - report endpoints.
  - API/Type: `backend/app/schemas/observation.py:59` - incident report create/read schema fields.
  - API/Type: `backend/app/models/observation.py:51` - incident report persisted fields.
  - Pattern:  `backend/app/audit/log.py:16` - state-changing actions must call `write_audit`.
  - Pattern:  `backend/app/realtime/events.py:15` - existing event constants include `NEW_REPORT` and `REPORT_VERIFIED`.
  - Pattern:  `frontend/src/components/field/QuickReportForm.tsx:80` - field report payload shape.
  - Pattern:  `frontend/src/api/client.ts:167` - frontend reports API paths.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_reports_api.py -q`
  - [ ] `cd backend && pytest tests/test_realtime_audit.py::test_report_mutations_write_audit_and_emit -q`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: field responder submits a report
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose up -d db backend && docker compose exec -T backend python -m app.seed.seed_demo && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=field_responder@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i -X POST "http://localhost:8000/api/events/$EVENT_ID/reports" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"event_id":"'"$EVENT_ID"'","reporter_type":"field_responder","report_category":"flooding","description":"Water rising at 3rd Street","geometry":{"type":"Point","coordinates":[-80.0007,26.0005]},"urgency":"high"}' | tee evidence/task-6-reports.txt
    Expected: response status is HTTP/1.1 201 Created and body contains "report_category":"flooding" and "verification_status":"unverified".
    Evidence: evidence/task-6-reports.txt

  Scenario: cross-event report payload is rejected
    Tool:     bash
    Steps:    mkdir -p evidence && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=field_responder@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i -X POST "http://localhost:8000/api/events/$EVENT_ID/reports" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"event_id":"00000000-0000-0000-0000-000000000000","reporter_type":"field_responder","report_category":"flooding","description":"bad event","geometry":{"type":"Point","coordinates":[-80.0,26.0]},"urgency":"high"}' | tee evidence/task-6-reports-error.txt
    Expected: response status is HTTP/1.1 400 Bad Request and body contains {"detail":"Report event_id must match path event_id"}.
    Evidence: evidence/task-6-reports-error.txt
  ```

  Commit: YES | Message: `feat(reports): add event incident report workflow` | Files: [`backend/app/api/routes/reports.py`, `backend/tests/test_reports_api.py`, `backend/tests/test_realtime_audit.py`]

- [ ] 7. Roads and teams APIs

  What to do: Implement `GET /api/events/{event_id}/roads/status`, `PATCH /api/roads/{id}/status`, `GET /api/events/{event_id}/teams`, `PATCH /api/teams/{id}/location`, and `PATCH /api/teams/{id}/status`. Use `RoadStatusRead`, `RoadStatusUpdate`, `ResponseTeamRead`, and `ResponseTeamUpdate`; reject unknown rows; write audits and emit `road_status_changed` / `team_location_updated`. Add tests for list/update/status validation/location update.
  Must NOT do: Do not implement safe route calculation, road graph generation, external routing, or team dispatch optimization.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [8, 9, 10, 11, 12, 13] | Blocked by: [1, 3, 4, 5]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `backend/app/api/routes/roads.py:1` - roads route stub.
  - Pattern:  `backend/app/api/routes/teams.py:1` - teams route stub.
  - API/Type: `DESIGN.md:200` - road status endpoints.
  - API/Type: `DESIGN.md:201` - team endpoints.
  - API/Type: `backend/app/schemas/infrastructure.py:87` - road status schemas.
  - API/Type: `backend/app/schemas/response.py:13` - response team schemas.
  - API/Type: `backend/app/models/infrastructure.py:57` - road model fields.
  - API/Type: `backend/app/models/response.py:16` - team model fields.
  - Pattern:  `frontend/src/components/field/RoadStatusUpdater.tsx:25` - field UI polls roads and patches status.
  - Pattern:  `frontend/src/components/field/LocationBeacon.tsx:28` - field UI patches team location.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_roads_teams_api.py -q`
  - [ ] `cd backend && pytest tests/test_realtime_audit.py::test_road_and_team_mutations_write_audit_and_emit -q`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: field responder marks a seeded road blocked
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose up -d db backend && docker compose exec -T backend python -m app.seed.seed_demo && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=field_responder@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && ROAD_ID=$(curl -s "http://localhost:8000/api/events/$EVENT_ID/roads/status" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i -X PATCH "http://localhost:8000/api/roads/$ROAD_ID/status" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"status":"blocked","reason":"Field report: road blocked","confidence_score":0.9}' | tee evidence/task-7-roads-teams.txt
    Expected: response status is HTTP/1.1 200 OK and body contains "status":"blocked" and "confidence_score":0.9.
    Evidence: evidence/task-7-roads-teams.txt

  Scenario: invalid road status is rejected
    Tool:     bash
    Steps:    mkdir -p evidence && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=field_responder@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && ROAD_ID=$(curl -s "http://localhost:8000/api/events/$EVENT_ID/roads/status" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i -X PATCH "http://localhost:8000/api/roads/$ROAD_ID/status" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"status":"washed_away"}' | tee evidence/task-7-roads-teams-error.txt
    Expected: response status is HTTP/1.1 422 Unprocessable Entity.
    Evidence: evidence/task-7-roads-teams-error.txt
  ```

  Commit: YES | Message: `feat(ops): add road and team update apis` | Files: [`backend/app/api/routes/roads.py`, `backend/app/api/routes/teams.py`, `backend/tests/test_roads_teams_api.py`, `backend/tests/test_realtime_audit.py`]

- [ ] 8. Tasks API and status transitions

  What to do: Implement `GET /api/events/{event_id}/tasks`, `POST /api/events/{event_id}/tasks`, and `PATCH /api/tasks/{id}` in `backend/app/api/routes/tasks.py`. Use `TaskCreate`, `TaskUpdate`, and `TaskRead`; force path `event_id` on create; validate legal status transitions used by `TaskCard`; write audits and emit `task_assigned` / `task_status_changed`. Add tests for list/create/patch, team filtering by client-side data shape, and invalid transition.
  Must NOT do: Do not implement dispatch optimization, recommendations-to-task automation, or role-specific task visibility beyond basic authenticated access unless local patterns already require it.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [9, 10, 11, 12, 13] | Blocked by: [1, 3, 4, 5, 7]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `backend/app/api/routes/tasks.py:1` - task route stub.
  - API/Type: `DESIGN.md:198` - task endpoints.
  - API/Type: `backend/app/schemas/response.py:45` - task create/update/read schema fields.
  - API/Type: `backend/app/models/response.py:35` - task persisted fields.
  - API/Type: `backend/app/models/enums.py:128` - legal task statuses.
  - Pattern:  `frontend/src/components/field/TaskList.tsx:15` - field UI lists event tasks.
  - Pattern:  `frontend/src/components/field/TaskCard.tsx:16` - UI expects exact task status transition sequence.
  - Pattern:  `frontend/src/api/client.ts:230` - frontend task API paths.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_tasks_api.py -q`
  - [ ] `cd backend && pytest tests/test_realtime_audit.py::test_task_mutations_write_audit_and_emit -q`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: field responder accepts an assigned task
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose up -d db backend && docker compose exec -T backend python -m app.seed.seed_demo && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=field_responder@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && TASK_ID=$(curl -s "http://localhost:8000/api/events/$EVENT_ID/tasks" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i -X PATCH "http://localhost:8000/api/tasks/$TASK_ID" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"status":"accepted"}' | tee evidence/task-8-tasks.txt
    Expected: response status is HTTP/1.1 200 OK and body contains "status":"accepted".
    Evidence: evidence/task-8-tasks.txt

  Scenario: illegal task transition is rejected
    Tool:     bash
    Steps:    mkdir -p evidence && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=field_responder@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && TASK_ID=$(curl -s "http://localhost:8000/api/events/$EVENT_ID/tasks" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i -X PATCH "http://localhost:8000/api/tasks/$TASK_ID" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"status":"completed"}' | tee evidence/task-8-tasks-error.txt
    Expected: response status is HTTP/1.1 409 Conflict and body contains {"detail":"Invalid task status transition"}.
    Evidence: evidence/task-8-tasks-error.txt
  ```

  Commit: YES | Message: `feat(tasks): add field task lifecycle api` | Files: [`backend/app/api/routes/tasks.py`, `backend/tests/test_tasks_api.py`, `backend/tests/test_realtime_audit.py`]

- [ ] 9. Dashboard summary and map-layer APIs

  What to do: Implement `GET /api/events/{event_id}/dashboard-summary` and `GET /api/events/{event_id}/map-layers` in `backend/app/api/routes/dashboard.py`. Return the contract from Task 2: summary fields consumed by `DashboardSummaryBar`, and array payloads consumed by `MapView` and `PriorityList`. Include reports, observations, areas, roads, shelters, teams, and tasks as arrays; empty arrays are valid for layers not in the MVP seed. Support `?bbox=minx,miny,maxx,maxy` and reject malformed bbox with 400. Add tests proving report/road/task mutations change summary and map-layer responses.
  Must NOT do: Do not implement expensive scoring/recommendation computation in these endpoints; aggregate from persisted rows only.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [11, 13] | Blocked by: [1, 2, 4, 5, 6, 7, 8]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `backend/app/api/routes/dashboard.py:1` - dashboard route stub.
  - API/Type: `DESIGN.md:202` - dashboard endpoints.
  - API/Type: `backend/app/schemas/dashboard.py:10` - dashboard summary schema to align in Task 2.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:82` - frontend polls dashboard summary every 15s.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:89` - frontend polls map layers with optional bbox.
  - Pattern:  `frontend/src/components/panels/DashboardSummaryBar.tsx:31` - exact summary fields rendered in KPI strip.
  - Pattern:  `frontend/src/components/Map/MapView.tsx:212` - exact map-layer arrays converted into GeoJSON.
  - Pattern:  `frontend/src/components/panels/PriorityList.tsx:15` - priority areas sort by `overall_priority_score`.
  - External: `https://vite.dev/config/server-options` - Vite dev proxy behavior for `/api` and `/ws` requests.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_dashboard_api.py -q`
  - [ ] After creating a report and blocking a road in tests, `total_reports` increases and `roads_blocked` increases.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: dashboard summary reflects seeded operational state
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose up -d db backend && docker compose exec -T backend python -m app.seed.seed_demo && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=emergency_manager@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i "http://localhost:8000/api/events/$EVENT_ID/dashboard-summary" -H "Authorization: Bearer $TOKEN" | tee evidence/task-9-dashboard.txt
    Expected: response status is HTTP/1.1 200 OK and body contains total_reports, roads_blocked, pending_tasks, shelters_open, and last_updated.
    Evidence: evidence/task-9-dashboard.txt

  Scenario: malformed bbox returns a clear client error
    Tool:     bash
    Steps:    mkdir -p evidence && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=emergency_manager@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i "http://localhost:8000/api/events/$EVENT_ID/map-layers?bbox=bad" -H "Authorization: Bearer $TOKEN" | tee evidence/task-9-dashboard-error.txt
    Expected: response status is HTTP/1.1 400 Bad Request and body contains {"detail":"Invalid bbox; expected minx,miny,maxx,maxy"}.
    Evidence: evidence/task-9-dashboard-error.txt
  ```

  Commit: YES | Message: `feat(dashboard): add summary and map layer apis` | Files: [`backend/app/api/routes/dashboard.py`, `backend/tests/test_dashboard_api.py`]

- [ ] 10. Command-center side-panel APIs and text situation report

  What to do: Implement the remaining command-center read/actions needed by the current dashboard: `GET /api/events/{event_id}/recommendations`, `POST /api/events/{event_id}/recommendations/{id}/approve`, `POST /api/events/{event_id}/recommendations/{id}/dismiss`, `GET /api/events/{event_id}/alerts`, `GET /api/events/{event_id}/shelters`, `PATCH /api/shelters/{id}/status`, and `POST /api/events/{event_id}/situation-report` for `format:"text"`. Return 501 or 400 for `format:"pdf"` with a clear `detail` because PDF is outside this MVP. Add tests for recommendations list/actions, alerts empty-list shape, shelters list/status, text report, and PDF rejection.
  Must NOT do: Do not implement generated PDF, automated alert creation, shelter allocation, or full recommendation rule engine.

  Parallelization: Can parallel: YES | Wave 2 | Blocks: [11, 13] | Blocked by: [1, 2, 4, 5, 7, 8]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `backend/app/api/routes/recommendations.py:1` - recommendations route stub.
  - Pattern:  `backend/app/api/routes/shelters.py:1` - shelters route stub.
  - Pattern:  `backend/app/api/routes/dashboard.py:1` - add `/events/{event_id}/alerts` here unless creating and registering a new alerts router is separately justified.
  - API/Type: `DESIGN.md:195` - recommendation endpoints.
  - API/Type: `DESIGN.md:199` - shelter endpoints.
  - API/Type: `DESIGN.md:203` - situation report endpoint.
  - API/Type: `backend/app/schemas/assessment.py:66` - recommendation schema fields.
  - API/Type: `backend/app/schemas/infrastructure.py:13` - shelter schema fields.
  - API/Type: `backend/app/schemas/audit.py:13` - alert read schema fields.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:98` - dashboard fetches recommendations.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:105` - dashboard fetches alerts.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:149` - dashboard text/PDF export behavior.

  Acceptance criteria (agent-executable only):
  - [ ] `cd backend && pytest tests/test_command_center_api.py -q`
  - [ ] `curl` QA for `format:"text"` returns `Content-Type` compatible with text and includes Rivertown summary.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: recommendation approval updates panel data
    Tool:     bash
    Steps:    mkdir -p evidence && docker compose up -d db backend && docker compose exec -T backend python -m app.seed.seed_demo && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=responder_coordinator@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && REC_ID=$(curl -s "http://localhost:8000/api/events/$EVENT_ID/recommendations" -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i -X POST "http://localhost:8000/api/events/$EVENT_ID/recommendations/$REC_ID/approve" -H "Authorization: Bearer $TOKEN" | tee evidence/task-10-command-center.txt
    Expected: response status is HTTP/1.1 200 OK and body contains "status":"approved".
    Evidence: evidence/task-10-command-center.txt

  Scenario: PDF situation report is explicitly out of scope
    Tool:     bash
    Steps:    mkdir -p evidence && TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=emergency_manager@demo.disaster&password=demo1234' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])") && EVENT_ID=$(curl -s http://localhost:8000/api/events -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])") && curl -i -X POST "http://localhost:8000/api/events/$EVENT_ID/situation-report" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"format":"pdf"}' | tee evidence/task-10-command-center-error.txt
    Expected: response status is HTTP/1.1 501 Not Implemented and body contains {"detail":"PDF situation reports are outside the MVP slice"}.
    Evidence: evidence/task-10-command-center-error.txt
  ```

  Commit: YES | Message: `feat(command-center): add panel apis and text situation report` | Files: [`backend/app/api/routes/recommendations.py`, `backend/app/api/routes/shelters.py`, `backend/app/api/routes/dashboard.py`, `backend/app/api/routes/reports.py`, `backend/tests/test_command_center_api.py`]

- [ ] 11. Frontend API/type integration

  What to do: Update frontend code to consume the agreed MVP contract from Task 2 and the implemented route payloads from Tasks 6-10. Fix enum literals in `QuickReportForm`, nullable/optional field handling in `types.ts`, dashboard summary keys, map-layer shapes, and text report handling. Keep the existing dark operational UI layout. Add or update lightweight frontend checks so `npm run build` catches contract drift.
  Must NOT do: Do not replace the dashboard/field layout, add marketing copy, or introduce unrelated component libraries. Do not make the frontend depend on mocked data when real backend APIs exist.

  Parallelization: Can parallel: NO | Wave 3 | Blocks: [12, 13] | Blocked by: [2, 6, 7, 8, 9, 10]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `frontend/src/api/client.ts:50` - Axios base URL and auth header behavior.
  - Pattern:  `frontend/src/types.ts:1` - TypeScript mirror of backend schemas.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:81` - dashboard data queries.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:149` - situation report export behavior.
  - Pattern:  `frontend/src/components/panels/DashboardSummaryBar.tsx:31` - summary field reads.
  - Pattern:  `frontend/src/components/Map/MapView.tsx:212` - map-layer conversion expectations.
  - Pattern:  `frontend/src/components/field/QuickReportForm.tsx:15` - report category options that must match backend enums.
  - Pattern:  `frontend/package.json:6` - build script used for verification.
  - External: `https://vite.dev/guide/build.html` - production build command behavior.

  Acceptance criteria (agent-executable only):
  - [ ] `cd frontend && npm run build`
  - [ ] `cd frontend && npm run lint || test $? -eq 2` is documented in evidence if ESLint config is still absent; if executor adds ESLint config, lint must pass normally.
  - [ ] `! rg -n "backend may not be live|silently ignore" frontend/src/pages/Dashboard.tsx frontend/src/components`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: frontend builds against real MVP contract
    Tool:     bash
    Steps:    mkdir -p evidence && cd frontend && npm run build | tee ../evidence/task-11-frontend.txt
    Expected: command exits 0 and Vite build completes without TypeScript errors.
    Evidence: evidence/task-11-frontend.txt

  Scenario: stale enum literals and silent backend-ignore paths are absent
    Tool:     bash
    Steps:    mkdir -p evidence && if rg -n "medical_emergency|automated_sensor|backend may not be live|silently ignore" frontend/src > ../evidence/task-11-frontend-error.txt; then exit 1; else echo "no stale frontend contract literals" > ../evidence/task-11-frontend-error.txt; fi
    Expected: command exits 0 and evidence confirms stale literals are absent.
    Evidence: evidence/task-11-frontend-error.txt
  ```

  Commit: YES | Message: `fix(frontend): wire ui to mvp api contract` | Files: [`frontend/src/types.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/panels/DashboardSummaryBar.tsx`, `frontend/src/components/Map/MapView.tsx`, `frontend/src/components/field/QuickReportForm.tsx`]

- [ ] 12. Field responder mutation invalidation and UI flow hardening

  What to do: Make field mutations refresh the data surfaces users expect: report submit invalidates report/map/summary data, road update invalidates roads/map/summary, task update invalidates event-specific tasks/summary, and team location update invalidates teams/map data. Harden loading/error states so the field screen still shows the report and roads tabs when there are no teams or tasks. Preserve offline queue behavior from `frontend/src/lib/offlineQueue.ts`.
  Must NOT do: Do not rewrite the offline queue, add service workers, or implement real background sync.

  Parallelization: Can parallel: NO | Wave 3 | Blocks: [13] | Blocked by: [6, 7, 8, 11]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `frontend/src/pages/FieldResponder.tsx:37` - offline queue sync currently invalidates only `reports`.
  - Pattern:  `frontend/src/components/field/QuickReportForm.tsx:107` - report mutation success/error flow.
  - Pattern:  `frontend/src/components/field/RoadStatusUpdater.tsx:32` - road status mutation invalidation.
  - Pattern:  `frontend/src/components/field/TaskCard.tsx:51` - task mutation invalidation.
  - Pattern:  `frontend/src/components/field/LocationBeacon.tsx:19` - location mutation flow.
  - Pattern:  `frontend/src/lib/offlineQueue.ts:14` - persisted offline queue helpers.
  - Pattern:  `frontend/src/App.tsx:9` - global 15s polling defaults.

  Acceptance criteria (agent-executable only):
  - [ ] `cd frontend && npm run build`
  - [ ] `rg -n "invalidateQueries\\(\\{ queryKey: \\['dashboard-summary'|invalidateQueries\\(\\{ queryKey: \\['map-layers'" frontend/src/components frontend/src/pages`
  - [ ] Field screen remains reachable when `/events/{event_id}/teams` returns an empty array.

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: mutation invalidation targets dashboard and map data
    Tool:     bash
    Steps:    mkdir -p evidence && cd frontend && npm run build | tee ../evidence/task-12-field-flow.txt && rg -n "dashboard-summary|map-layers|tasks|roads" src/components src/pages | tee -a ../evidence/task-12-field-flow.txt
    Expected: build exits 0 and evidence contains invalidation paths for dashboard-summary, map-layers, tasks, and roads after relevant mutations.
    Evidence: evidence/task-12-field-flow.txt

  Scenario: no-team state does not block report and roads tabs
    Tool:     bash
    Steps:    mkdir -p evidence && cd frontend && npm run build | tee ../evidence/task-12-field-flow-error.txt
    Expected: build exits 0 and component logic has no unconditional early return that hides report/roads forever when teams is [].
    Evidence: evidence/task-12-field-flow-error.txt
  ```

  Commit: YES | Message: `fix(field): refresh operational data after mutations` | Files: [`frontend/src/pages/FieldResponder.tsx`, `frontend/src/components/field/QuickReportForm.tsx`, `frontend/src/components/field/RoadStatusUpdater.tsx`, `frontend/src/components/field/TaskCard.tsx`, `frontend/src/components/field/LocationBeacon.tsx`]

- [ ] 13. Real Chrome Playwright MVP scenario harness

  What to do: Add a Playwright e2e harness that drives the real app through Chrome against the Docker stack: login, dashboard load, field report submission with typed coordinates, road status update, task accept, and dashboard visibility refresh. Configure artifacts under `evidence/`. Use role/label selectors matching current UI text where stable; add minimal test IDs only where necessary. Include a negative login test.
  Must NOT do: Do not replace backend pytest coverage with e2e tests. Do not use jsdom or mocked API responses for this MVP scenario.

  Parallelization: Can parallel: NO | Wave 3 | Blocks: [final verification] | Blocked by: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

  References (executor has NO interview context - be exhaustive):
  - Pattern:  `frontend/src/pages/Login.tsx:55` - login form fields and submit button.
  - Pattern:  `frontend/src/pages/Dashboard.tsx:179` - dashboard root layout after login.
  - Pattern:  `frontend/src/pages/FieldResponder.tsx:211` - tab bar for tasks/report/roads.
  - Pattern:  `frontend/src/components/field/QuickReportForm.tsx:182` - report form controls.
  - Pattern:  `frontend/src/components/field/RoadStatusUpdater.tsx:98` - road action buttons.
  - Pattern:  `frontend/src/components/field/TaskCard.tsx:99` - task action buttons.
  - Pattern:  `docker-compose.yml:27` - backend service runs migrations before Uvicorn.
  - Pattern:  `docker-compose.yml:80` - frontend service exposes port 5173.
  - External: `https://playwright.dev/docs/test-cli` - exact Playwright CLI behavior and project selection.
  - External: `https://playwright.dev/docs/screenshots` - screenshot artifact capture.

  Acceptance criteria (agent-executable only):
  - [ ] `docker compose up -d --build`
  - [ ] `docker compose exec -T backend python -m app.seed.seed_demo`
  - [ ] `cd frontend && npx playwright test tests/e2e/disaster-mvp.spec.ts --project=chrome --output ../evidence/task-13-playwright`
  - [ ] `test -f evidence/task-13-playwright/dashboard-after-report.png && test -f evidence/task-13-playwright/field-after-road-update.png`

  QA scenarios (MANDATORY - task incomplete without these):
  ```
  Scenario: field report and road update are visible to command center
    Tool:     playwright(real Chrome)
    Steps:    mkdir -p evidence/task-13-playwright && docker compose up -d --build && docker compose exec -T backend python -m app.seed.seed_demo && cd frontend && npx playwright test tests/e2e/disaster-mvp.spec.ts --project=chrome --grep "mvp field to dashboard loop" --output ../evidence/task-13-playwright
    Expected: Playwright exits 0; screenshots include dashboard-after-report.png and field-after-road-update.png; dashboard shows increased Reports count and blocked road state.
    Evidence: evidence/task-13-playwright/dashboard-after-report.png

  Scenario: invalid login shows user-facing error
    Tool:     playwright(real Chrome)
    Steps:    mkdir -p evidence/task-13-playwright && docker compose up -d --build && cd frontend && npx playwright test tests/e2e/disaster-mvp.spec.ts --project=chrome --grep "invalid login" --output ../evidence/task-13-playwright
    Expected: Playwright exits 0 and screenshot shows Invalid credentials. Please try again.
    Evidence: evidence/task-13-playwright/invalid-login.png
  ```

  Commit: YES | Message: `test(e2e): cover disaster mvp response loop` | Files: [`frontend/package.json`, `frontend/package-lock.json`, `frontend/playwright.config.ts`, `frontend/tests/e2e/disaster-mvp.spec.ts`, `frontend/src/pages/Login.tsx`, `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/FieldResponder.tsx`, `frontend/src/components/field/QuickReportForm.tsx`, `frontend/src/components/field/RoadStatusUpdater.tsx`, `frontend/src/components/field/TaskCard.tsx`]

## Final verification wave (MANDATORY - after all implementation tasks)
> Runs in PARALLEL. ALL must APPROVE. Surface results to the caller and wait for an explicit "okay" before declaring complete.
- [ ] F1. Plan compliance audit - every task done, every acceptance criterion met
- [ ] F2. Code quality review - diagnostics clean, idioms match, no dead code
- [ ] F3. Real manual QA - every QA scenario executed with evidence captured
- [ ] F4. Scope fidelity - nothing extra shipped beyond Must-Have, nothing Must-NOT-Have introduced

## Commit strategy
- One logical change per commit. Conventional Commits (`<type>(<scope>): <subject>` body + footer).
- Atomic: every commit builds and passes tests on its own.
- No "WIP" / "fix typo squash later" commits on the final branch - clean up before merge.
- Reference the plan file path in the final commit footer: `Plan: plans/disaster-mvp-slice.md`.

## Success criteria
- All Must-Have shipped; all QA scenarios pass with captured evidence; F1-F4 approved; commit history clean.
