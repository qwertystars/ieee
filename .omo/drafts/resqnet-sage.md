# resqnet-sage — Draft

## Intent
- **intent**: clear
- **review_required**: false
- **routing**: CLEAR — user provided an extremely detailed SOTA research synthesis (17 sections, 9 architectural layers, evaluation framework, implementation blueprint). The outcome is unambiguous.

## User decisions (from interview)

### Decision 1: Stack Strategy = FULL PIVOT to Python/PostGIS
User chose to abandon the Cloudflare Workers platform entirely and build ResQNet-SAGE on the spec's recommended Python stack: FastAPI + PostgreSQL/PostGIS + Redpanda/Kafka + PyTorch + OR-Tools.

**Rationale**: The SOTA spec requires capabilities (PyTorch ML, OR-Tools optimization, PostGIS geospatial, probabilistic programming) that fundamentally cannot run on Cloudflare Workers. A full pivot gives a unified single-stack architecture with no inter-service complexity.

**Impact**: All existing CF platform work (P0-P1 complete, 41 routes, 7 DOs, 180-task plan) is abandoned. The `platform/` directory becomes dead code. New code goes into `backend/` + `frontend/` (directories described in DESIGN.md but never built — the team pivoted to CF before building them).

### Decision 2: Plan Relationship = REPLACE
User chose to create a new plan that supersedes the CF replatform plan entirely. The existing `.omo/plans/disaster-cf-replatform.md` is archived. All work is planned fresh against the SOTA spec.

**Impact**: The existing boulder work (`disaster-cf-replatform-ba88eca3`) should be cancelled. The new plan is the sole active plan.

## Components ledger (topology lock)
| ID | Component | Outcome | Status |
|----|-----------|---------|--------|
| C1 | Observation schema + federated ingestion | 23-field event model + CAP/SensorThings/OGC/STAC/HDX adapters | new |
| C2 | Probabilistic evidence fusion | Confidence vector (6D), Beta source reliability, Bayesian world-state, conformal calibration | new |
| C3 | Temporal crisis knowledge graph | Entity/relationship graph preserving contradictory hypotheses | new |
| C4 | Hazard & infrastructure digital twin | Scenario ensemble, cascading dependency DAG, telecom silence residual | new |
| C5 | Decision optimization | Rolling-horizon risk-aware optimizer (CVaR), route reliability, stability threshold | new |
| C6 | Active sensing / EVI | Expected value of information for sensing actions | new |
| C7 | Multimodal ML perception | SAR flood mapping ensemble, building/road damage, social media NLP | new |
| C8 | Human-centered explainable decision support | 4 interface modes, action cards with evidence/alternatives/uncertainty | new |
| C9 | Evaluation testbed | Replayable digital twin, failure injection, 4 baselines, 6 metric categories, ablation | new |

## Additional constraint (from user approval)
**Local hardware deployment, low internet connectivity, offline-first.**
- All services in Docker Compose on local hardware (no cloud runtime dependencies)
- ML models pre-downloaded/cached, ONNX Runtime for CPU inference
- Satellite data acquisition = "sync when connected" pattern (not real-time cloud API)
- Frontend = PWA with offline capabilities (IndexedDB outbox, store-and-forward)
- System must work in degraded mode when internet is unavailable
- MinIO (S3-compatible, self-hosted) for object storage, not R2
- Redpanda single-node (not cloud Kafka)
- All Python ML/optimization runs locally

## Approval gate
- **status**: APPROVED
- **pending action**: write `.omo/plans/resqnet-sage.md`
- **approach**: Full pivot to Python/PostGIS. Build all 9 SOTA layers + evaluation testbed. Local-hardware-first Docker Compose stack. New project structure under `backend/` (FastAPI + SQLAlchemy + PostGIS + PyTorch + OR-Tools) and `frontend/` (React + Vite + MapLibre + deck.gl). Redpanda + Benthos for streaming. MinIO for object storage. All services self-hosted, offline-capable.

## Research tasks dispatched
- bg_2871bc92: OR-Tools CP-SAT patterns for resource allocation + routing — COMPLETE
  Key findings: `add_cumulative` (availability), `add_multiple_circuit` (VRP), `add_reservoir_constraint` (capacities), CVaR via Rockafellar-Uryasev + `add_max_equality`, rolling-horizon via `add_hint` warm-start + deviation penalty, FastAPI BackgroundTasks async solve pattern.
- bg_ba8ac5cb: Bayesian evidence fusion libraries — COMPLETE
  Key findings: pgmpy v1.1.2 active, `DBNInference.forward_inference()` for P(X_t|O), BUT only discrete (TabularCPD). PyMC v6.1.0 for Beta source reliability (analytic conjugate updates for streaming). pyds ARCHIVED — implement DS directly. MAPIE v1.4.1 for conformal calibration with `partial_fit()`. Bean Machine DEAD.
- bg_bac2773d: SAR flood mapping with TorchGeo — COMPLETE
  Key findings: sentinelsat DEAD — use CDSETool. DOFA built into TorchGeo (wavelength-aware, supports SAR). Tessera + ResNet50 S1 weights available. Clay via `claymodel.module.ClayMAEModule`. TerraMind via rslearn. No off-the-shelf pretrained flood segmentation model — need to fine-tune. Monte Carlo Dropout for uncertainty.
- bg_835b8072: Redpanda+Benthos streaming for FastAPI — COMPLETE
  Key findings: Redpanda single-node Docker (4GB min), aiokafka for FastAPI, Benthos YAML pipeline (bloblang normalize + dedup + switch routing), built-in Schema Registry. Apache AGE for graph queries in PostgreSQL. Hybrid: PostgreSQL store + Redpanda/Benthos processing + LISTEN/NOTIFY for realtime.

## Metis gap analysis — COMPLETE (bg_2f6a4c86)
19 gaps identified. Critical findings folded into plan:
- GAP 3: Apache AGE v1.8.0 requires PG 18, PostGIS may not support PG 18 → Added T51 spike with fallback to graph_edges + recursive CTEs
- GAP 5: pyds archived/unmaintained/not on PyPI → Dropped from stack, will implement DS combination directly
- GAP 8: Missing seed data → Added T52 seed data package
- GAP 11: Missing offline prep → Added T53 offline pre-deployment script
- GAP 12: Redpanda 1GB too low → Fixed to 4GB minimum
- GAP 14: Wave 4 depends on T9 (STAC) → Updated dependency matrix
- GAP 15: Missing LLM offline strategy → Added Ollama local model for offline to T36
- GAP 7: DESIGN.md contradicts plan → Added supersession note to Must NOT have
- All Metis directives folded into Scope/Must-NOT-Have/dependency matrix silently

## Plan status
- **status**: COMPLETE
- **plan file**: `.omo/plans/resqnet-sage.md`
- **todos**: 53 (T1-T50 + T51 spike + T52 seed + T53 offline prep; T27 merged into T26)
- **waves**: 10 + Wave 0 spike + final verification (F1-F4)
- **Metis**: folded in silently (19 gaps)
- **high-accuracy review**: Round 1 COMPLETE, fixes applied, Round 2 dispatched

## High-accuracy review — Round 2
- **Momus** (bg_736e9036): **OKAY** ✅ — All 11 fixes verified. 4 minor issues (T50→T27 stale ref, Wave 4 per-todo deps, T53 QA scenario, ONNX sequencing wording). Zero critical.
- **Oracle** (bg_750dca9f): **APPROVE** ✅ — All 12 fixes verified. Several MEDIUM/MINOR issues (T50→T27, T53 offline test, ONNX conversion gap, T1 missing spike dep, T36 fallback ordering, spike numbering). Zero critical.
- **Both verdicts: APPROVED.** Dual review passed. T50→T27 stale reference fixed.
- **Fix summary**: T50's "Blocked by: T27" changed to "Blocked by: T26 (optimizer + constraints, formerly T27)". All other remaining issues are MINOR and can be resolved during execution.

### Critical issues fixed (Round 1 → Round 2):
1. T15 math error: F=exp(-t/τ) at t=τ gives 0.368, not >0.9 → Fixed thresholds with correct math
2. T53 `--no-internet`: non-existent Docker flag → Replaced with `docker network create --internal`
3. Ollama missing from stack → Added to T1 Docker Compose + requirements
4. T53 ONNX conversion timing: can't convert fine-tuned models at Wave 1 → Clarified T53 downloads base weights only, ONNX conversion in T22
5. T26↔T27 circular dependency: optimizer needs constraints, constraints blocked by optimizer → Merged T26+T27 into one todo
6. T43 baselines 1-2 not automatable → Replaced human operators with simulated operators
7. T44 NASA-TLX requires humans → Replaced with automated proxy metrics (workload estimated from info density × ambiguity × conflict)
8. T1 AGE contradiction: acceptance requires AGE but plan says optional → Made conditional on T51 spike result
9. T21 Vectorize reference: Cloudflare leftover → Replaced with FAISS
10. psycopg2 vs psycopg3 contradiction → Fixed to psycopg[binary] (psycopg3)
11. Wave 4 intra-wave dependency: T22 must precede T18-T21 → Added header note
12. T11 AGE conditional: acceptance tests Cypher but AGE may be dropped → Made conditional on spike
