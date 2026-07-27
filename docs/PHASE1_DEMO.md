# Phase 1 Demo Guide

End-to-end walkthrough of the alert-to-task loop on the Rivertown cyclone-flood
scenario. Exercises the full pipeline: seed data, authenticate, start the
rescue-ball simulator, validate a draft alert, approve it, and inspect the
dispatched task.

## Prerequisites

- PostgreSQL 16 with PostGIS at `localhost:5432` (db: `resqnet`, user: `resqnet`,
  pw: `resqnet123`)
- Python venv at `backend/.venv/` (run `make bootstrap`)
- `curl` and `jq` installed
- Backend running at `http://localhost:8000`

If the backend is not running, start it:

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
```

## Automated demo

The fastest path. Runs every step below in sequence and prints a summary:

```bash
make demo
```

Or directly:

```bash
bash scripts/demo_phase1.sh
```

The script exits non-zero on any failure. Override defaults with env vars:

```bash
BACKEND_URL=http://localhost:8000 \
ADMIN_EMAIL=admin@demo.disaster \
ADMIN_PASSWORD=demo1234 \
SIM_DURATION=5 \
bash scripts/demo_phase1.sh
```

## Manual walkthrough

### Step 1: Reset demo state

Re-seed the Rivertown scenario. This is idempotent (delete-then-insert per
org+incident scope):

```bash
cd backend && .venv/bin/python -m app.seed.seed_demo
```

Output confirms entity counts: 1 incident, 5 zones, 20 roads, 3 shelters,
2 hospitals, 10 buildings, 50 observations, 5 hypotheses, 3 scenarios,
1 draft alert, 1 assigned task.

### Step 2: Authenticate

```bash
TOKEN=$(curl -sf -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@demo.disaster&password=demo1234" \
  | jq -r '.access_token')

echo "Token length: ${#TOKEN}"
AUTH="Authorization: Bearer $TOKEN"
```

The JWT carries `org_id=org_demo`, `role=admin`, and a 12-hour expiry. The
`org_context` middleware resolves `org_id` server-side from the signed token,
never from the client.

### Step 3: Fetch the incident

```bash
curl -sf -H "$AUTH" http://localhost:8000/api/incidents | jq '.incidents[0]'
```

The Rivertown cyclone-flood incident is the seeded scenario. Note the
`id` field for subsequent calls.

### Step 4: Start the rescue-ball simulator

```bash
INCIDENT_ID=$(curl -sf -H "$AUTH" http://localhost:8000/api/incidents \
  | jq -r '.incidents[0].id')

curl -sf -X POST http://localhost:8000/api/simulator/start \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"org_id\": \"org_demo\", \"incident_id\": \"$INCIDENT_ID\", \"device_count\": 2, \"seed\": 42}" \
  | jq .
```

Returns `device_ids` for the two rescue-ball devices. The simulator publishes
observations to the `observations.raw` Kafka topic every second. If Kafka is
unavailable, the engine logs a warning and continues (best-effort).

### Step 5: Wait for observations

```bash
curl -sf -H "$AUTH" \
  "http://localhost:8000/api/observations?incident_id=$INCIDENT_ID&limit=5" \
  | jq '.features | length'
```

Observations appear within a few seconds. Each carries
`provenance_chain: {"simulated": true}` so downstream consumers can distinguish
simulated from real data.

### Step 6: Validate the draft alert

```bash
curl -sf -H "$AUTH" \
  "http://localhost:8000/api/incidents/$INCIDENT_ID/alerts?status=draft" \
  | jq '.alerts[0]'
```

The seed creates one draft alert (trapped-person report). Its `status` is
`draft` until a human approves it. All AI-generated content lands as
`review_status=draft` until human approval.

### Step 7: Approve the alert

```bash
ALERT_ID=$(curl -sf -H "$AUTH" \
  "http://localhost:8000/api/incidents/$INCIDENT_ID/alerts?status=draft" \
  | jq -r '.alerts[0].id')

curl -sf -X POST \
  "http://localhost:8000/api/incidents/$INCIDENT_ID/alerts/$ALERT_ID/approve" \
  -H "$AUTH" \
  -H "Content-Type: application/json" \
  -d '{"review_rationale": "Phase 1 demo approval"}' \
  | jq '.status'
```

Returns `"approved"`. The approval is logged to the hash-chained audit trail
with the approver's user ID and timestamp.

### Step 8: Inspect the dispatched task

```bash
curl -sf -H "$AUTH" \
  "http://localhost:8000/api/incidents/$INCIDENT_ID/tasks" \
  | jq '.tasks[0]'
```

The seed creates one assigned rescue task linked to the alert. The task
carries priority, assigned responder, and location (precision depends on
viewer role, see [SECURITY_MODEL.md](SECURITY_MODEL.md)).

### Step 9: Stop the simulator

```bash
curl -sf -X POST http://localhost:8000/api/simulator/stop -H "$AUTH"
```

Returns 204 No Content. The background asyncio task is cancelled and the
Kafka producer is stopped.

### Step 10: Check capabilities

```bash
curl -sf http://localhost:8000/api/capabilities | jq '.features[]
  | {feature, status}'
```

Reports runtime availability of ONNX models, Ollama LLM, PMTiles basemap,
model weights, Kafka, and Redis. Each feature is checked at request time,
not hardcoded. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for
activation steps.

## Frontend walkthrough

Open http://localhost:5173 in a browser. Log in with any demo account
(password `demo1234`).

- **Command center** (admin, emergency_manager): full map, all incidents,
  alert approval workflow, task dispatch
- **Field responder**: task list, exact rescue locations for assigned tasks,
  offline outbox for mutations
- **Shelter manager**: shelter occupancy, assigned-person info (name, phone)

The map renders vector overlays (incidents, observations, entities). If a
PMTiles basemap file is configured, satellite imagery renders underneath.
Otherwise, a solid dark background with vector overlays is shown.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Login returns 401 | Demo users not seeded. Run `make seed` |
| No incidents returned | Seed did not run. Run `make seed` |
| Simulator start returns 500 | Known sync-route + asyncio issue. Seeded observations are still present |
| No observations after simulator | Kafka may be down. Observations are also seeded directly in PostgreSQL |
| `make demo` fails on healthz | Backend not running. Start with `uvicorn app.main:app --reload` |
| Frontend blank map | PMTiles not configured. Vector overlays still render. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) |

## Demo data summary

The seed creates the Rivertown cyclone-flood scenario:

| Entity | Count |
|---|---|
| Incident | 1 |
| Zones | 5 |
| Roads | 20 |
| Shelters | 3 |
| Hospitals | 2 |
| Buildings | 10 |
| Substations | 3 |
| Cell towers | 5 |
| Responders | 5 |
| Vehicles | 3 |
| Rescue-ball devices | 2 |
| Observations | 50 |
| Hypotheses | 5 (2 contradictory) |
| Scenarios | 3 (best/expected/worst) |
| Draft alerts | 1 |
| Tasks | 1 (assigned) |

All fixtures are local files. No internet connection is required for the demo.
