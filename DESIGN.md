# Disaster Situational Awareness & Response Platform — Engineering Contract

This document is the **frozen interface contract** for parallel implementation. Workers MUST
implement against these signatures/paths so independently-built modules integrate cleanly.
If a worker needs to change a contract, message the team lead first.

Disaster focus for v1: **urban flooding**, single demo region.

---

## 1. Tech stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.x, GeoAlchemy2, Alembic, Pydantic v2,
  `pydantic-settings`, `python-jose` (JWT), `passlib[bcrypt]`, `shapely`, `geojson-pydantic`.
- **DB:** PostgreSQL 16 + PostGIS 3.4 (Docker image `postgis/postgis:16-3.4`).
- **Worker:** same Python image, APScheduler loop (no Celery for v1).
- **Frontend:** React 18 + Vite + TypeScript, MapLibre GL JS, TanStack Query, React Router,
  Tailwind CSS, `maplibre-gl`.
- **Realtime:** FastAPI WebSocket endpoint `/ws/events/{event_id}` + polling fallback.
- **Routing (v1):** in-process Dijkstra over a road graph built from RoadStatus segments
  (NetworkX). No external OSRM for v1 (extensible later).
- **Reports:** plain text + PDF via `reportlab`.

## 2. Repository layout (monorepo at repo root)

```
docker-compose.yml          # postgis, backend, worker, frontend
.env.example                # all env vars
README.md                   # run instructions
backend/
  Dockerfile
  requirements.txt
  alembic.ini
  alembic/env.py
  alembic/versions/
  app/
    __init__.py
    main.py                 # FastAPI app; includes routers; mounts /ws; CORS; startup
    config.py               # Settings via pydantic-settings
    db.py                   # engine, SessionLocal, Base import, get_db()
    deps.py                 # shared FastAPI deps (get_db re-export, pagination)
    models/                 # SQLAlchemy models (see §4) — owned by FOUNDATION
    schemas/                # Pydantic schemas (see §5) — owned by FOUNDATION
    auth/                   # security.py, deps.py, router.py
    audit/                  # log.py (write_audit helper)
    api/
      router.py             # aggregates all routes/*.py routers (FOUNDATION wires)
      routes/               # events, datasources, observations, reports, areas,
                            # recommendations, tasks, shelters, roads, teams,
                            # dashboard, audit  (one APIRouter per file)
    ingestion/              # base.py, connectors.py, normalize.py, verify.py,
                            # dedup.py, pipeline.py, router.py
    analysis/               # impact.py, scoring.py, engine.py
    recommend/              # rules.py, routing.py, shelter_alloc.py
    realtime/               # manager.py, events.py
    alerts/                 # rules.py
    reports_gen/            # situation.py + situation_report route
    seed/                   # seed_demo.py, data/*.geojson
  tests/
frontend/
  Dockerfile
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/
    main.tsx, App.tsx
    api/client.ts           # axios/fetch wrapper + typed endpoints
    auth/AuthContext.tsx
    types.ts                # TS mirror of API schemas
    lib/                    # helpers (geo, format, ws)
    components/             # Map/, panels, PriorityList, etc.
    pages/                  # Login, Dashboard, FieldResponder
```

### Boot contract (CRITICAL for parallelism)
The FOUNDATION task creates **every** module above with importable stubs so the app boots
and the frontend builds before features land:
- every `routes/*.py` exposes `router = APIRouter()` (may be empty)
- every engine module exposes the function signatures in §6 returning safe empty defaults
- `app/main.py` already includes all routers and mounts `/ws`
Feature workers fill in the stubs **without editing `main.py` or `api/router.py`**.

## 3. Conventions

- IDs: `UUID` primary keys (`uuid4`), column name `id`.
- Geometry: `geoalchemy2.Geometry(srid=4326)`. API exchanges GeoJSON geometry objects.
- Timestamps: `created_at`/`updated_at` server defaults (UTC, timezone-aware).
- All list endpoints support `?limit=&offset=`; geo endpoints support `?bbox=minx,miny,maxx,maxy`.
- Enums: Python `enum.Enum` (str) in `app/models/enums.py`, reused by schemas.
- Confidence scores: float `0..1`. Priority/score components: float `0..100`.
- Error model: FastAPI `HTTPException` with JSON `{ "detail": ... }`.
- Auth: `Authorization: Bearer <jwt>`. Roles in §7.

## 4. Database entities (SQLAlchemy models, `app/models/`)

Use these table/field names. Geometry SRID 4326. (Types abbreviated.)

- **User**(id, name, email[unique], hashed_password, role[enum], organization, phone,
  status, created_at, updated_at)
- **DisasterEvent**(id, name, type[enum], status, start_time, end_time, description,
  affected_region geometry(POLYGON/MULTIPOLYGON), created_by→User, created_at, updated_at)
- **DataSource**(id, name, type[enum], provider, refresh_interval_s, last_success_at,
  last_error, status, config[JSONB], created_at, updated_at)
- **RawIngestedRecord**(id, source_id→DataSource, event_id→DisasterEvent, raw_payload[JSONB],
  received_at, processing_status[enum: pending/processed/error], error_message)
- **NormalizedObservation**(id, event_id, source_id, observation_type[enum], geometry(GEOMETRY),
  timestamp, value[float, nullable], unit, description, confidence_score, metadata[JSONB],
  cluster_id[nullable UUID], created_at)
- **IncidentReport**(id, event_id, reporter_type[enum], report_category[enum], description,
  geometry(POINT), photo_url, urgency[enum: low/medium/high/critical],
  verification_status[enum: unverified/low/medium/high], confidence_score, pii_redacted_text,
  cluster_id[nullable], created_at, updated_at)
- **AreaAssessment**(id, event_id, area_name, geometry(POLYGON), hazard_score, exposure_score,
  access_score, infrastructure_score, vulnerability_score, trend_score, report_score,
  overall_priority_score, priority_level[enum: critical/high/medium/low/monitoring/unknown],
  summary, components[JSONB explainability], updated_at)
- **Recommendation**(id, event_id, area_assessment_id→AreaAssessment[nullable],
  recommendation_type[enum], title, description, reasoning, supporting_data[JSONB],
  confidence_score, urgency[enum], status[enum: draft/reviewed/approved/assigned/in_progress/
  completed/dismissed], assigned_to→ResponseTeam[nullable], created_at, updated_at)
- **Shelter**(id, name, geometry(POINT), total_capacity, current_occupancy,
  available_capacity[computed], food_status, water_status, medical_support[bool],
  accessibility_support[bool], status, updated_at)
- **Hospital**(id, name, geometry(POINT), emergency_capacity, status, access_status, contact,
  updated_at)
- **RoadStatus**(id, event_id, road_name, geometry(LINESTRING), status[enum: open/blocked/
  partially_blocked/unknown/dangerous], reason, confidence_score, updated_at)
- **ResponseTeam**(id, name, team_type[enum], current_location(POINT), status, capacity,
  assigned_task_id[nullable], updated_at)
- **Task**(id, event_id, recommendation_id[nullable], assigned_team_id[nullable], title,
  description, location(POINT), priority[enum], status[enum: assigned/accepted/en_route/
  on_site/completed/blocked/cancelled], created_at, updated_at)
- **AuditLog**(id, user_id[nullable], action, target_type, target_id, details[JSONB], created_at)
- **Alert**(id, event_id, alert_type, title, message, area geometry[nullable], severity,
  recommended_action, confidence_score, acknowledged[bool], created_at) — for §8 alerts.

Enums live in `app/models/enums.py`: UserRole, DisasterType, DataSourceType, ObservationType,
ReporterType, ReportCategory, Urgency, VerificationStatus, PriorityLevel, RecommendationType,
RecommendationStatus, RoadStatusEnum, TeamType, TaskStatus, ProcessingStatus.

## 5. Pydantic schemas (`app/schemas/`)
For each model: `XBase`, `XCreate`, `XUpdate`, `XRead` (with `model_config = ConfigDict(from_attributes=True)`).
Geometry fields typed via `geojson_pydantic` Geometry. A `DashboardSummary` and `MapLayers`
schema for the dashboard endpoints. A `SituationReportRequest`/`SituationReport` schema.

## 6. Engine interfaces (frozen signatures)

`app/ingestion/pipeline.py`
```python
def ingest_record(db, source_id, event_id, raw_payload) -> RawIngestedRecord
def process_record(db, raw: RawIngestedRecord) -> list[NormalizedObservation]  # normalize→dedup→verify→store
def run_source(db, source_id) -> int   # pull+process; returns #observations
```
`app/ingestion/normalize.py`: `normalize(source_type, raw_payload) -> list[NormalizedObsDict]`
`app/ingestion/verify.py`: `initial_confidence(reporter_type|source_type) -> float`,
  `adjust_confidence(db, obs) -> float` (corroboration, age decay, conflict).
`app/ingestion/dedup.py`: `find_cluster(db, obs) -> UUID|None` (distance+time+category+text).

`app/analysis/impact.py`: `estimate_impact(db, event_id, hazard_geom) -> ImpactDict`
  (population, buildings, schools, hospitals, shelters, road_length_m, ...).
`app/analysis/scoring.py`: `score_area(db, event_id, area_geom) -> ScoreDict` (7 components + overall + level + explanation).
`app/analysis/engine.py`: `recompute_assessments(db, event_id) -> list[AreaAssessment]`.

`app/recommend/rules.py`: `generate_recommendations(db, event_id) -> list[Recommendation]`.
`app/recommend/routing.py`: `safe_route(db, event_id, start, dest) -> RouteDict` (avoids blocked/dangerous roads).
`app/recommend/shelter_alloc.py`: `allocate_shelters(db, event_id, evac_area, people) -> AllocationDict`.

`app/realtime/manager.py`: `class ConnectionManager` with `connect/disconnect/broadcast(event_id, message)`;
  singleton `manager`. `app/realtime/events.py`: `async def emit(event_id, type, payload)` + EventType constants (§ realtime list).

`app/alerts/rules.py`: `evaluate_alerts(db, event_id) -> list[Alert]`.
`app/reports_gen/situation.py`: `build_situation_report(db, event_id, fmt) -> bytes|str`.
`app/audit/log.py`: `write_audit(db, user_id, action, target_type, target_id, details=None)`.

The processing pipeline (§26 of spec) is orchestrated in `pipeline.process_record` then
`analysis.engine.recompute_assessments` → `recommend.rules.generate_recommendations` →
`alerts.rules.evaluate_alerts` → `realtime.events.emit`. The worker calls `run_source` per source.

## 7. Roles & RBAC (`app/auth`)
Roles: `admin, emergency_manager, responder_coordinator, field_responder, shelter_manager, viewer`.
- `require_roles(*roles)` dependency factory.
- Sensitive (PII / individual reports) gated to admin, emergency_manager, responder_coordinator.
- Viewers see aggregated, redacted data only.
- Every state-changing action calls `write_audit`.
Seed users (one per role), password `demo1234`, emails `<role>@demo.disaster`.

## 8. API surface (must match spec §24)
Auth: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.
Events: `GET/POST /events`, `GET/PATCH /events/{id}`.
Data sources: `GET/POST /data-sources`, `PATCH /data-sources/{id}`.
Observations: `GET/POST /events/{eventId}/observations`.
Reports: `GET/POST /events/{eventId}/reports`, `GET /reports/{id}`, `PATCH /reports/{id}/verify`.
Areas: `GET /events/{eventId}/areas`, `GET /areas/{id}`.
Recommendations: `GET /events/{eventId}/recommendations`,
  `POST /events/{eventId}/recommendations/{id}/approve`,
  `POST /events/{eventId}/recommendations/{id}/dismiss`.
Tasks: `GET/POST /events/{eventId}/tasks`, `PATCH /tasks/{id}`.
Shelters: `GET /events/{eventId}/shelters`, `PATCH /shelters/{id}/status`.
Roads: `GET /events/{eventId}/roads/status`, `PATCH /roads/{id}/status`.
Teams: `GET /events/{eventId}/teams`, `PATCH /teams/{id}/location`, `PATCH /teams/{id}/status`.
Dashboard: `GET /events/{eventId}/dashboard-summary`, `GET /events/{eventId}/map-layers`.
Situation report: `POST /events/{eventId}/situation-report` (returns file or text).
Ingestion: `POST /events/{eventId}/ingest/{sourceType}` (manual trigger, owned by ingestion).
Audit: `GET /events/{eventId}/audit-logs`.
All under prefix `/api`. WebSocket at `/ws/events/{eventId}`.

## 9. Realtime event types
`new_observation, new_report, report_verified, area_priority_changed, recommendation_created,
recommendation_approved, task_assigned, task_status_changed, shelter_status_changed,
road_status_changed, team_location_updated, alert_created`.

## 10. Demo scenario (seed)
Urban flood, fictional "Rivertown". Seed: admin region polygon; ~12 road LINESTRINGs (some
blocked/dangerous); 3 shelters (varying capacity); 2 hospitals; population grid (GeoJSON polygons
with `population` prop); 2-3 flood hazard polygons; ~15 incident reports (citizen+responder mix:
trapped_person, road_blocked, flooding, power_outage, shelter_need); 4 response teams; a couple
weather/river observations. Running seed must yield: flood zone on map, affected population
estimate, blocked roads, ranked priority areas, evacuation + reroute + open-shelter recommendations,
an assigned rescue task, and a generatable situation report.

## 11. Frontend contract
- `api/client.ts` typed against §8. Auth token in memory + localStorage.
- Dashboard: MapLibre map (bbox/zoom-driven layer fetch), layer toggles (§20 list),
  left **priority list** (primary operational tool), right panels (recommendations w/ approve+dismiss,
  shelters, teams, alerts), timeline, situation-report export button, confidence + data-age badges everywhere.
- FieldResponder: mobile-first, low-bandwidth; assigned tasks; quick report form
  (category, location[geolocate], urgency, description; optional photo, water depth, people);
  mark road blocked/open; update task status; optimistic UI.
- Polling every 15s as realtime fallback; WebSocket when available.

## 12. Non-negotiables (spec §35)
Explainable recommendations; show confidence + data age + source; raw data retained; citizen
reports unverified until corroborated; human approval for life-critical actions; design for
missing data and low bandwidth.
