# Disaster Situational Awareness & Response Platform

Real-time situational awareness and response coordination for urban flooding (v1 demo
region: **Rivertown**). Monorepo: FastAPI backend + worker + React/Vite frontend on
PostgreSQL/PostGIS.

See [`DESIGN.md`](./DESIGN.md) for the frozen interface contract.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Services:
- **db** — PostGIS 16-3.4 on `localhost:5432`
- **backend** — FastAPI on http://localhost:8000 (docs at `/docs`, health at `/healthz`)
- **worker** — APScheduler ingestion loop
- **frontend** — Vite dev server on http://localhost:5173

The backend runs `alembic upgrade head` on start to create all tables and the PostGIS
extension. Seed the demo scenario after the stack is up:

```bash
docker compose exec backend python -m app.seed.seed_demo
```

Demo logins (password `demo1234`): `admin@demo.disaster`, `emergency_manager@demo.disaster`,
`responder_coordinator@demo.disaster`, `field_responder@demo.disaster`,
`shelter_manager@demo.disaster`, `viewer@demo.disaster`.

## Local backend development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Point DATABASE_URL at a local PostGIS, then:
alembic upgrade head
uvicorn app.main:app --reload
```

## Layout

```
backend/   FastAPI app, models, schemas, engines, alembic migrations
frontend/  React + Vite + MapLibre command center and field-responder views
```
