# Field-Trial Protocol: ResQNet Multi-Agency Regional Validation

> **PROTOCOL DOCUMENT ONLY. The field trial has NOT been executed.**
>
> **EXECUTION of this field trial is a DEFERRED MILESTONE that a
> software worker cannot perform.** The trial requires physical hardware
> (see [`docs/HARDWARE_SPECIFICATION.md`](./HARDWARE_SPECIFICATION.md)),
> calibrated sensors (see [`docs/PHYSICAL_TEST_PLAN.md`](./PHYSICAL_TEST_PLAN.md)),
> and multi-agency coordination. No results exist in this document. No
> agency has committed. No trial region has been selected. No data has
> been collected.

**Status:** SPEC ONLY (not executed, deferred)
**Locked decision D1:** field-trial execution is deferred. A software
worker produces this protocol. A software worker does NOT execute the
trial.
**Locked decision D3:** SLOs: 50 concurrent operators / 100 obs/sec
sustained ingest / <2s p95 dashboard load / <500ms p95 API read latency
/ 99% availability over 1h soak / <30s failover time.
**Related task:** Wave 6, Todo 22 (`resqnet-gap-closure` plan)
**Depends on:** T12 (hardware spec), T13 (physical test plan), T9
(dataset licensing), Wave 5 software gates, Wave 6 software gates
**Governing disclaimer:** #6 in
[`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md#6-local-demo-performance-does-not-equal-real-disaster-performance)
(lines 322 to 334): local demo performance does not equal real disaster
performance. This protocol is the path to establishing real-world
performance bounds. Until it is executed, disclaimer #6 remains in
force unchanged.

---

## Purpose and Scope

This document defines the protocol for a multi-agency field trial of
the ResQNet platform under real disaster-zone conditions. The trial has
two goals: validate that the platform meets its six service-level
objectives under field conditions, and validate that the calibrated ML
models hold their conformal coverage on real regional data.

The trial is the field counterpart to the lab and CI gates in Waves 5
and 6. Lab gates prove the software holds under controlled load. The
field trial proves the software holds when the load comes from real
responders on degraded networks with real sensors feeding real models.

This protocol covers six sections:

1. Trial objectives and success criteria, mapped to the six SLOs
2. Participating agencies, roles, and Incident Command System integration
3. Regional model validation protocol for the three calibrated models
4. Readiness checklist (software gates, hardware, sensors, data, team, comms)
5. Trial scenarios, data-collection plan, and ethics/IRB requirements
6. Explicit deferred-execution milestone marker

The physical test protocols that gate sensor and device readiness are
defined in [`docs/PHYSICAL_TEST_PLAN.md`](./PHYSICAL_TEST_PLAN.md).
This document does not repeat those protocols. It references them as
prerequisites and adds the multi-agency, multi-scenario, real-data
layer on top.

---

## 1. Trial Objectives and Success Criteria

The trial validates the six SLOs from locked decision D3 under real
disaster-zone conditions. Each SLO has a lab or CI measurement (already
gated in Waves 5 and 6) and a field measurement defined here. The field
measurement is the binding one for trial success. A lab pass plus a
field fail is a trial fail.

### 1.1 SLO Measurement Matrix

| # | SLO | Lab/CI measurement (Waves 5 to 6) | Field measurement (this trial) | Pass criterion |
|---|---|---|---|---|
| 1 | 50 concurrent operators | Load test: 50 virtual users hitting dashboard and API endpoints simultaneously | Real responders (50 across all participating agencies) logged in and actively using the dashboard during a live scenario drill | All 50 sessions stay active for the full drill window (60 minutes). No session drops due to platform-side auth or capacity failure. |
| 2 | 100 obs/sec sustained ingest | Load test: 100 obs/sec from a synthetic sensor source for 1 hour | Real rescue-ball devices (per `docs/HARDWARE_SPECIFICATION.md`) plus any real sensor feeds emitting into the platform through the `SensorSource` contract | Sustained ingest at or above 100 obs/sec for the full drill window, measured at the observation persistence layer. Gaps from device-side link loss do not count against the SLO. Platform-side ingest failures do. |
| 3 | <2s p95 dashboard load time | Playwright e2e: dashboard render time under controlled load | Dashboard load time measured from real responder browsers (Chrome DevTools or equivalent) over the field network (LTE or degraded link) | p95 dashboard load time below 2 seconds across all 50 responder sessions for the drill window. Measured from navigation start to dashboard interactive. |
| 4 | <500ms p95 API read latency | Load test: p95 read latency on key GET endpoints under 50 concurrent users | API read latency measured at the platform edge over the field network, across all responder sessions | p95 read latency below 500ms for the five highest-traffic GET endpoints (observations, alerts, tasks, map tiles, capabilities) for the drill window. |
| 5 | 99% availability over 1h soak | Soak test: 1 hour at target load with no crashes or hangs | Platform availability over the full 60-minute drill window, measured by an external uptime probe on a separate network | 99% availability (at most 36 seconds of total downtime across the 3600-second window). Downtime from external network loss does not count. Platform-side crashes, hangs, and restarts do. |
| 6 | <30s failover time | Chaos test: kill a primary dependency, measure time to failover and resume serving | Failover time measured during a planned fault injection in the field (kill the primary Redis or Kafka broker, simulate LTE loss on the primary uplink) | Time from fault injection to first successful post-failover request, measured at a responder browser, below 30 seconds. |

### 1.2 Field vs Lab Measurement Differences

The field measurement differs from the lab measurement in three ways
that matter for interpreting results.

**Network.** Lab tests run on localhost or a controlled LAN. Field
trials run over LTE, satellite, or LoRa links with real packet loss and
latency. SLOs 3 and 4 (dashboard and API latency) are measured at the
responder browser, not at the server. A 200ms server response that
becomes 800ms at the browser over a degraded LTE link counts as 800ms
in the field measurement.

**Load profile.** Lab load tests use synthetic traffic shaped to a
target rate. Field load comes from real responder behavior, which is
bursty. Responders refresh the dashboard in waves when an alert fires.
SLO 2 (100 obs/sec ingest) is measured at the persistence layer, so
bursty responder traffic does not affect it. SLO 1 (50 concurrent
operators) is measured by active session count, not by request rate.

**Failure modes.** Lab chaos tests inject one fault at a time. Field
trials can have overlapping faults (LTE loss plus a sensor going
offline plus a responder browser crash). SLO 6 (failover time) is
measured for a single planned fault injection. Overlapping faults are
recorded as observations, not as SLO failures.

### 1.3 Trial Verdict

The trial passes when all six SLOs pass their field measurement for the
full drill window. A single SLO fail is a trial fail. The verdict is
recorded in `docs/KNOWN_LIMITATIONS.md` under disclaimer #6 with the
SLO-by-SLO results, the drill window, the responder count, and the
field network conditions.

A trial pass partially retires disclaimer #6 for the tested scenario
and network conditions. It does not retire disclaimer #6 for
conditions outside the tested envelope (night operation, heavy weather,
swift water, larger responder counts, different regions).

---

## 2. Participating Agencies, Roles, and Incident Command Integration

The field trial requires multi-agency coordination. No single agency
has the authority, personnel, or equipment to run a full disaster-zone
drill alone. This section defines the agency structure, the roles, and
how the platform integrates with the Incident Command System (ICS).

### 2.1 Agency Structure

The agency structure below is a template. The trial lead selects the
actual agencies based on regional availability and existing
relationships. No agency has committed to this trial. The structure
exists so a trial lead knows what roles to fill.

| Role | Agency type (example) | Responsibility in the trial |
|---|---|---|
| Lead agency | State Disaster Management Authority (SDMA) or equivalent | Owns the trial. Convenes participating agencies. Approves the trial scenario and drill window. Holds the trial verdict. |
| Supporting agency: response | National Disaster Response Force (NDRF) or equivalent military or paramilitary response unit | Provides field responders for the 50-concurrent-operator SLO. Deploys and recovers rescue-ball devices. |
| Supporting agency: local first responders | Municipal fire and police | Provides local knowledge of the trial region. Secures the drill perimeter. Participates in responder sessions. |
| Supporting agency: municipal | Municipal corporation or urban local body | Provides access to the trial region. Coordinates with utilities (power, water, telecom) for any infrastructure interactions. |
| Supporting agency: technical | Platform engineering team | Operates the platform during the trial. Injects planned faults. Collects SLO measurements. Does NOT make response decisions. |
| Observing agency | National or state emergency management authority (not the lead) | Observes the trial for inter-agency interoperability. Does not participate in response. Provides feedback on ICS integration. |

### 2.2 ICS Roles

The trial uses the Incident Command System structure. The platform
integrates into ICS as a decision-support tool under the Situation
Unit. It does not replace any ICS role.

| ICS role | Trial responsibility | Platform interaction |
|---|---|---|
| Incident Commander (IC) | Owns the drill scenario. Approves the drill start and end. Has authority to abort. | Receives the platform's command-center dashboard on a dedicated display. Does not operate the platform directly. |
| Operations Section Chief | Directs field responders. Executes the response plan. | Receives task assignments from the platform. Updates task status as responders complete them. |
| Situation Unit Leader (SUL) | Maintates the common operating picture. Corroborates sensor data with responder reports. | Primary platform user. Owns the dashboard. Approves draft alerts before they go to responders. Reviews model outputs and marks them reviewed or rejected. |
| Field responders | Execute tasks in the field. Report observations. | Receive tasks on field-responder devices (phone or tablet). Submit observations and task updates over the field network. |
| Communications Unit Leader | Manages radio and data communications for the drill. | Coordinates with the technical agency on LTE, satellite, and LoRa availability. Does not operate the platform. |

### 2.3 Platform Integration with ICS

The platform fits into ICS as follows. This is the integration the
trial validates.

- **Common operating picture.** The SUL uses the platform dashboard as
  the primary common operating picture. All responder positions, sensor
  observations, alerts, and task statuses appear on the dashboard in
  real time. The IC and Operations Section Chief have read-only views.
- **Alert-to-task loop.** The platform generates draft alerts from
  sensor data and model outputs. The SUL reviews each draft alert. If
  approved, the alert becomes a task assigned to a field responder
  through the Operations Section Chief. The platform does not dispatch
  tasks without human approval. This matches the platform convention
  that all AI output lands as `review_status=draft` until human
  approval.
- **Information flow.** Sensor observations flow from rescue-ball
  devices through the `SensorSource` contract into the platform. The
  platform fuses observations, runs ML models, and produces draft
  alerts. The SUL reviews and approves. Approved alerts and tasks flow
  to responders. Responders submit observations and task updates back
  to the platform. The full loop is the unit of validation for SLOs 1
  through 5.
- **Audit trail.** Every platform action (alert draft, alert approval,
  task assignment, task update, model output) is recorded in the
  hash-chained audit log. The audit log is available to the IC and the
  lead agency for post-trial review.

### 2.4 Data Sharing Agreements

Before the trial, the lead agency executes a data sharing agreement
with each participating agency. The agreement covers:

- What data each agency contributes (sensor feeds, responder reports,
  regional reference data).
- What data each agency can access (dashboard views, task assignments,
  audit logs).
- How data is stored during and after the trial (platform tenancy,
  retention period, deletion at trial end).
- Who owns the trial data (the lead agency, with a license to the
  platform engineering team for analysis).
- How PII is handled (section 5.4 below).

No data sharing agreement exists yet. No agency has signed. This
section defines what the agreement must cover, not an agreement that
is in place.

---

## 3. Regional Model Validation Protocol

The trial validates that the three calibrated ML models hold their
conformal coverage on real regional data from the trial region. This is
the field counterpart to Protocol 5 in
[`docs/PHYSICAL_TEST_PLAN.md`](./PHYSICAL_TEST_PLAN.md). Protocol 5
defines the lab and reference-data validation. This section defines the
field validation against data collected during the trial itself.

### 3.1 Models in Scope

| Model | Role | Current calibration status (per `docs/KNOWN_LIMITATIONS.md` disclaimer #5) |
|---|---|---|
| `sar-flood-mapping` | Flood extent from Sentinel-1 SAR | Calibrated on Sen1Floods11 (coverage 0.9412 on held-out set). Not yet validated on regional data outside Sen1Floods11. |
| `building-damage` | Damage grade from satellite imagery | Fixture-data only. Marked `degraded`. No real calibration data. |
| `incident-nlp` | Incident extraction from text reports | No public calibration dataset. Marked `degraded`. No conformal intervals. |

### 3.2 Conformal Coverage Criterion

The `ConformalCalibrator` in
[`backend/app/fusion/calibration.py`](../backend/app/fusion/calibration.py)
is fit with `alpha = 0.1` (default at line 26, `_DEFAULT_ALPHA = 0.1`),
giving a nominal 90% confidence level. The acceptance band for
empirical coverage on real regional data is the closed interval
`[0.85, 0.95]`.

- Coverage below 0.85 means the intervals are too narrow. The model is
  overconfident. This is a safety failure for a decision-support tool.
- Coverage above 0.95 means the intervals are too wide. The model is
  underconfident. This is a utility failure.

Coverage is computed by
`ConformalCalibrator.compute_coverage(y_true, y_pred_lower, y_pred_upper)`
(line 212). The interval bounds come from `ConformalCalibrator.predict(X)`'s
`interval_lower` and `interval_upper` fields (lines 118 and 119). The
field trial validates that this coverage holds on real regional data,
not just on the Sen1Floods11 held-out set.

### 3.3 Per-Model Validation Protocol

For each model, the trial collects real regional data and computes
coverage against the existing calibration. The calibration is NOT
refit on trial data. The trial tests whether the existing calibration
transfers to the trial region.

**sar-flood-mapping:**

- **Data source.** Sentinel-1 SAR imagery for the trial region during
  the drill window, acquired through Copernicus Open Access Hub or
  equivalent. Paired with a human-labeled flood mask produced by the
  SUL or a designated analyst.
- **Minimum sample.** 500 chips spanning at least 3 flood events in
  the trial region. A chip is a Sentinel-1 SAR tile plus its
  human-labeled water mask.
- **Procedure.** Run the model on each chip. Compute conformal
  intervals using the existing `ConformalCalibrator` (fit on
  Sen1Floods11). Compute coverage against the human-labeled masks.
- **Acceptance.** Pooled coverage across all trial-region chips is
  within `[0.85, 0.95]` for `alpha = 0.1`. No single event's coverage
  is below 0.80 or above 0.98. Mean interval width on the trial-region
  set is within 1.5x of the mean interval width on the Sen1Floods11
  calibration set.

**building-damage:**

- **Data source.** Post-event satellite imagery of the trial region
  (Maxar, Planet, or equivalent) paired with a human-labeled damage
  grade per building footprint. Damage grade follows the xBD or
  equivalent scheme.
- **Minimum sample.** 1000 buildings spanning at least 2 damage events
  in the trial region.
- **Procedure.** Run the model on each building. Compute conformal
  intervals. Compute coverage against the human-labeled damage grades.
- **Acceptance.** Same coverage band and width criteria as
  sar-flood-mapping. A pass moves `building-damage` out of `degraded`
  status for the trial region.

**incident-nlp:**

- **Data source.** Real incident reports filed by field responders
  during the drill. Each report is paired with a human-labeled incident
  type and extracted fields (location, severity, people affected).
- **Minimum sample.** 500 incident reports spanning at least 3
  incident types (flood, fire, landslide, or others present in the
  scenario).
- **Procedure.** Run the model on each report. Compute conformal
  intervals. Compute coverage against the human-labeled fields.
- **Acceptance.** Same coverage band and width criteria. A pass moves
  `incident-nlp` out of `degraded` status for the trial region.

### 3.4 Regional Diversity

The trial-region data must come from a region outside the original
calibration set. For `sar-flood-mapping`, the trial region must not
overlap with the Sen1Floods11 event set (Bolivia, Ghana, India, Mekong,
Nigeria, Pakistan, Paraguay, Somalia, Spain, Sri-Lanka, USA). For
`building-damage` and `incident-nlp`, the trial data must not be drawn
from the same source as any calibration data (which is fixture data for
both, so any real regional data qualifies).

A coverage verdict from a single region or single event does not fully
retire disclaimer #5 for that model. The verdict is recorded per region
and per event. The pooled coverage across all regions (Sen1Floods11
plus the trial region) is the headline number.

### 3.5 Recalibration After Trial

If a model passes the field validation, the trial-region data is added
to the calibration set for future fits. This expands the calibration
envelope. The recalibration is performed by the platform engineering
team after the trial, not during it. The trial tests the existing
calibration. Recalibration uses the trial data plus the original
calibration data.

If a model fails the field validation, it remains in its current status
(`degraded` for `building-damage` and `incident-nlp`, or
`calibration_unconfirmed_for_region` for `sar-flood-mapping`). The
failure is recorded with the coverage, interval width, and per-event
breakdown. The model is returned to engineering for recalibration
before any retrial.

---

## 4. Readiness Checklist

Every item below must be green before the trial starts. A single red
item blocks the trial. The checklist is grouped into six categories:
software gates, hardware, sensors, calibration data, field team, and
communications.

**Current state (2026-07-29):** All software gates (sections 4.1 and
4.2) are GREEN. All physical gates (sections 4.3 Hardware and 4.4
Sensors) are DEFERRED. The trial cannot start until the physical gates
are resolved by a hardware team.

### 4.1 Software Gates (Waves 1 to 4)

These gates prove the software holds under controlled load before it
goes to the field. All gates below are GREEN as of 2026-07-29.

| Gate | Wave | Description | Status |
|---|---|---|---|
| Test stabilization | 1 | 520+ backend tests, 21/21 Playwright e2e, 45/45 frontend unit tests | GREEN (verified 2026-07-29) |
| ML models | 2 to 3 | SAR flood mapping (94 MB, IoU 0.67), building damage (129 MB, F1 0.34), incident NLP (438 MB). All 3 manifests `validated` and `signed`. `GET /api/capabilities` reports `onnx_models: available` | GREEN (verified 2026-07-29) |
| Ingestion performance | 4 | 182.3 obs/sec full pipeline, 195.58 obs/sec reduced. DB pool 50 connections, 6 Kafka partitions, 6 workers, batch consumer commits, async confidence scoring | GREEN (verified 2026-07-29) |

### 4.2 Software Gates (Waves 5 to 6)

These gates prove the software holds under load, soak, chaos, and
security conditions that approximate field stress. All gates below are
GREEN as of 2026-07-29.

| Gate | Wave | Description | Status |
|---|---|---|---|
| Soak test | 5 | 1 hour at target load, 99.26% success rate (162.79 obs/sec), no memory leaks | GREEN (verified 2026-07-29) |
| Chaos test | 5 | 9/9 chaos scenarios pass (redis, redpanda, minio kill, overlapping failures, container restarts, disk pressure, network loss). Measured failover: redis 9s, redpanda 10s, minio 14s | GREEN (verified 2026-07-29) |
| Load tests | 5 | 50 concurrent users, 100 obs/sec sustained (182.3 full, 195.58 reduced), p95 latency targets met | GREEN (verified 2026-07-29) |
| Frontend | 6 | 0 ESLint warnings, 0 TypeScript errors, 45/45 frontend tests | GREEN (verified 2026-07-29) |
| Auth hardening | 6 | 15-min access tokens, 7-day refresh tokens, local revocation cache, hybrid fail-closed/fail-open policy with break-glass audit | GREEN (verified 2026-07-29) |
| Backup and restore | 6 | Database and configuration backup and restore verified | GREEN (verified 2026-07-29) |
| Secrets audit | 6 | No secrets in code, all secrets in environment or secret store | GREEN (verified 2026-07-29) |

### 4.3 Hardware

The device under test is specified in
[`docs/HARDWARE_SPECIFICATION.md`](./HARDWARE_SPECIFICATION.md) (spec
only, device not built). The trial requires at least one built device.

**Status:** DEFERRED. No device has been built, procured, or
manufactured. Physical build is a deferred milestone that a software
worker cannot perform. See disclaimers #1 and #2 in
[`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md).

| Item | Requirement | Reference | Status |
|---|---|---|---|
| Rescue-ball devices | At least 5 built devices conforming to the hardware spec | `docs/HARDWARE_SPECIFICATION.md` sections 1 to 8 | DEFERRED (no device built) |
| Field server | Platform deployment on the target field hardware (laptop, mini-PC, or rack server per `docs/offline-prep.md`) | `docs/offline-prep.md` lines 36 to 52 | DEFERRED (no field deployment) |
| Responder devices | 50 phones or tablets for field responders, running the PWA frontend | `docs/OFFLINE_OPERATION.md` | DEFERRED (no field deployment) |
| Reference GPS | Survey-grade GPS for device deployment and recovery ground truth | `docs/PHYSICAL_TEST_PLAN.md` Protocol 4 | DEFERRED (no equipment procured) |

### 4.4 Sensors

Sensors must be calibrated before the trial. Calibration protocols are
defined in [`docs/PHYSICAL_TEST_PLAN.md`](./PHYSICAL_TEST_PLAN.md).

**Status:** DEFERRED. No sensor has been calibrated. No certified
reference equipment is procured. No IRB approval is on file. Physical
calibration is a deferred milestone that a software worker cannot
perform. See disclaimer #3 in
[`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md).

| Item | Requirement | Reference | Status |
|---|---|---|---|
| Sensor calibration | All sensors on all trial devices pass Protocol 2 calibration against certified reference targets | `docs/PHYSICAL_TEST_PLAN.md` Protocol 2 | DEFERRED (no device, no reference equipment) |
| Submersion rating | All trial devices pass Protocol 1 submersion testing at the depths and durations expected in the trial scenario | `docs/PHYSICAL_TEST_PLAN.md` Protocol 1 | DEFERRED (no device built) |
| Recovery validation | All trial devices pass Protocol 4 beacon range, GPS accuracy, and recovery time tests | `docs/PHYSICAL_TEST_PLAN.md` Protocol 4 | DEFERRED (no device built) |
| Human-detection certification (if scenario requires) | If the trial scenario involves human-detection evaluation, Protocol 3 must pass first. If the scenario does not require human detection, Protocol 3 is not a prerequisite. | `docs/PHYSICAL_TEST_PLAN.md` Protocol 3 | DEFERRED (no IRB, no device) |

### 4.5 Calibration Data

Regional calibration data must be acquired and licensed before the
trial. Dataset licensing is documented in
[`docs/MODEL_DATA_LICENSING.md`](./MODEL_DATA_LICENSING.md).

| Item | Requirement | Reference |
|---|---|---|
| Sen1Floods11 calibration data | Downloaded and active for `sar-flood-mapping` (already complete, coverage 0.9412) | `docs/MODEL_DATA_LICENSING.md`, `docs/KNOWN_LIMITATIONS.md` disclaimer #5 |
| xBD dataset (for `building-damage`) | Registration and download attempted. If gated, the model stays `degraded` and the trial validates fixture-calibrated behavior. | `docs/MODEL_DATA_LICENSING.md` |
| Trial-region reference data | Sentinel-1 SAR, post-event satellite imagery, and incident report sources for the trial region identified and access confirmed | Trial lead, before trial start |
| Data sharing agreements | Executed with all participating agencies (section 2.4) | Trial lead, before trial start |

### 4.6 Field Team

| Item | Requirement |
|---|---|
| ICS training | All trial participants trained on the Incident Command System and their specific role (section 2.2) |
| Platform training | All responders trained on the ResQNet platform: login, dashboard, task list, observation submission, offline behavior |
| Device training | Field responders trained on rescue-ball deployment and recovery per `docs/HARDWARE_SPECIFICATION.md` sections 5 and 6 |
| Drill scenario briefing | All participants briefed on the drill scenario, the drill window, the abort procedure, and the safety plan |

### 4.7 Communications

| Item | Requirement |
|---|---|
| LTE | At least one LTE carrier with confirmed coverage in the trial region. Tested with a real device before the trial. |
| Satellite | Satellite fallback (Swarm or Iridium) tested with a real device. Confirmed that the platform receives telemetry over the satellite link. |
| LoRa | LoRa mesh tested between at least two rescue-ball devices and a shore base station. Confirmed beacon range per Protocol 4. |
| Field network | The field network that responders use to reach the platform dashboard is tested under load. If the platform is deployed on a local field server, the responder-to-server link is tested with 50 concurrent sessions. |
| Fallback plan | If all data links fail, the trial has a procedure to continue with local-only operation (PWA offline mode, IndexedDB outbox) and reconcile when links return. |

### 4.8 Checklist Sign-Off

The trial lead signs off on the full checklist before the trial starts.
Sign-off is recorded in the trial log with the date (UTC), the lead's
name, and the status of each item. A single red item blocks sign-off.
The sign-off is the gate between readiness and execution.

---

## 5. Trial Scenarios, Data Collection, and Ethics

### 5.1 Trial Scenarios

The trial runs one or more scenarios from the set below. The trial
lead selects the scenario based on regional relevance, season, and
agency availability. No scenario is committed. The set defines what is
valid.

| Scenario | Region type | Trigger | Primary SLOs stressed | Models exercised |
|---|---|---|---|---|
| Urban flooding, monsoon | Coastal megacity (Mumbai, Chennai, Kolkata) | Monsoon rainfall during a named depression | All six SLOs under high responder count and degraded LTE | sar-flood-mapping, incident-nlp |
| Riverine flooding | Inland river basin (Brahmaputra, Kosi, or equivalent) | River breaching embankment or dam release | SLOs 1, 2, 5, 6 (rural network, longer drill window) | sar-flood-mapping, building-damage |
| Cyclone-induced flooding | Coastal district (Odisha, Andhra, or equivalent) | Cyclone landfall with storm surge | All six SLOs under multi-agency response | sar-flood-mapping, building-damage, incident-nlp |
| Urban waterlogging | Inland city with poor drainage | Sustained heavy rainfall, no named event | SLOs 1, 3, 4 (lower sensor load, higher dashboard load) | incident-nlp |

Each scenario defines a drill window (60 to 180 minutes), a responder
count (target 50, minimum 30 for a valid SLO 1 measurement), and a
device count (target 5, minimum 3 for a valid SLO 2 measurement if
devices are the primary sensor source).

### 5.2 Data Collection Plan

The trial collects the following data. All data is stored on the
platform under the trial's `org_id` and `incident_id`. Access is
restricted to the trial lead, the SUL, and the platform engineering
team.

| Data type | Source | Storage | Retention |
|---|---|---|---|
| Sensor observations | Rescue-ball devices and any real sensor feeds | Platform observation table (D1 or PostgreSQL per deployment) | Deleted 90 days after trial end, unless the lead agency requests longer retention for analysis. |
| Model outputs | Platform ML models (sar-flood-mapping, building-damage, incident-nlp) | Platform model output log | Same as observations. |
| Alert and task records | Platform alert-to-task loop | Platform alert and task tables | Same as observations. |
| Audit log | Platform hash-chained audit | Platform audit table | Retained for the full retention period. The audit log is the trial's legal record. |
| SLO measurements | Platform engineering team measurement scripts | Trial log (markdown or CSV, committed to the repo under `evidence/field-trial/`) | Committed permanently as trial evidence. |
| Responder browser telemetry | Chrome DevTools or equivalent from responder devices | Trial log, aggregated and de-identified | Deleted 90 days after trial end. |
| Network condition logs | Field network monitoring (LTE signal, satellite latency, LoRa RSSI) | Trial log | Committed permanently as trial evidence. |
| Regional reference data | Sentinel-1 SAR, satellite imagery, human-labeled masks | `backend/data/field_trial/<scenario_id>/` (gitignored) | Retained for model recalibration. Checksums committed. |

### 5.3 Ethics and IRB Approval

The trial involves human participants (field responders) and may
involve human-detection evaluation (if the scenario uses thermal
sensors near people). Both require ethics approval before any data
collection.

**IRB approval.** An Institutional Review Board (or equivalent ethics
body) reviews and approves the trial protocol, the consent form, and
the data handling plan before the trial starts. The IRB approval covers
the scenario, the responder participation, and any human-detection
evaluation. A trial without IRB approval on file is invalid. Its data
cannot be used to retire any disclaimer.

**Informed consent for field responders.** Each responder signs an
informed consent form before the trial. The form covers:

- The purpose of the trial (validating the platform under field
  conditions).
- What the responder will do (use the platform dashboard, submit
  observations, execute tasks).
- What data is collected from the responder (browser telemetry, task
  actions, observation submissions).
- That the responder's name is not in the trial dataset. A responder ID
  links actions to a person, held by the lead agency, not by the
  platform engineering team.
- That participation is voluntary. The responder can withdraw at any
  time without penalty.
- The data retention period (90 days, or longer if the lead agency
  requests).

**Human-detection evaluation.** If the scenario involves thermal
sensors near people (responders or the public), the trial requires the
Protocol 3 certified human-detection validation from
[`docs/PHYSICAL_TEST_PLAN.md`](./PHYSICAL_TEST_PLAN.md) to have passed
first. If Protocol 3 has not passed, the trial does not evaluate
human-detection output. The thermal sensors still collect data, but no
detection decision is made or recorded. This keeps the trial within
the bounds of disclaimer #3.

### 5.4 Privacy and PII Protections

The trial may collect personally identifiable information (PII) from
responders and, depending on the scenario, from the public. PII
protections follow the platform's progressive precision model.

**Responder PII.** Responder names, phone numbers, and exact locations
are PII. The platform stores responder PII under the responder's user
account, accessible only to the responder and to users with the
`emergency_manager` or `admin` role. The trial dataset uses responder
IDs, not names. The mapping from responder ID to name is held by the
lead agency, not by the platform.

**Public PII.** If the scenario involves observations near members of
the public (thermal signatures, acoustic readings, incident reports
mentioning people), the platform's progressive precision redaction
applies. Field responders see exact locations and full details. The
SUL sees ward-level aggregation. The public dashboard (if any) sees
only aggregated counts. No public PII is committed to the repo. No
public PII appears in the trial log.

**Data subject access requests.** Any person whose data appears in the
trial dataset can request access, correction, or deletion through the
lead agency. The lead agency coordinates with the platform engineering
team to fulfill the request. The platform's audit log records the
request and the action taken.

**Deletion at trial end.** Unless the lead agency requests longer
retention, all PII is deleted 90 days after the trial ends. The audit
log records the deletion. The deletion does not remove aggregated,
de-identified data (counts, coverage statistics, SLO measurements)
that is committed to the repo as trial evidence.

---

## 6. Deferred-Execution Milestone Marker

This section records the deferred milestone in the terms the
orchestrator and any future worker need.

> **This is a PROTOCOL document only. The field trial has NOT been
> executed.**
>
> **EXECUTION of this field trial is a DEFERRED MILESTONE that a
> software worker cannot perform.** The trial requires physical
> hardware (see
> [`docs/HARDWARE_SPECIFICATION.md`](./HARDWARE_SPECIFICATION.md)),
> calibrated sensors (see
> [`docs/PHYSICAL_TEST_PLAN.md`](./PHYSICAL_TEST_PLAN.md)), and
> multi-agency coordination.

**Milestone:** Execute the field trial defined in sections 1 through 5
with built hardware, calibrated sensors, real regional data, IRB
approval, and multi-agency participation. Record the SLO-by-SLO verdict
and the model coverage verdict in `docs/KNOWN_LIMITATIONS.md` under
disclaimers #5 and #6.

**Status:** NOT STARTED. No device exists. No agency has committed. No
trial region has been selected. No IRB approval is on file. No
trial-region reference data is collected. No field team is trained. No
data sharing agreement is executed. This document is the specification
only.

**Owner:** Not a software worker. Execution requires:

- A trial lead (typically a senior emergency manager at the lead
  agency).
- Built rescue-ball devices per `docs/HARDWARE_SPECIFICATION.md`.
- Calibrated sensors per `docs/PHYSICAL_TEST_PLAN.md` Protocols 1, 2,
  and 4 (and Protocol 3 if the scenario involves human detection).
- Multi-agency participation (lead agency plus at least two supporting
  agencies).
- IRB approval for responder participation and any human-detection
  evaluation.
- Regional calibration data per `docs/MODEL_DATA_LICENSING.md`.
- A field-deployed platform instance with all Wave 5 and Wave 6
  software gates green.

A software worker can update this protocol, wire verdict-recording into
`docs/KNOWN_LIMITATIONS.md`, or build tooling to ingest trial-region
reference data. A software worker cannot execute the trial.

**Retirement of disclaimers:**

- Disclaimer #6 (local demo performance does not equal real disaster
  performance) is retired only when the trial passes in full (all six
  SLOs pass their field measurement). Partial retirement is recorded
  per SLO and per scenario. A pass in one scenario does not retire the
  disclaimer for conditions outside that scenario.
- Disclaimer #5 (ML depends on available weights and calibration data)
  is partially retired per model when that model passes the regional
  validation in section 3. A model that passes in the trial region
  moves out of `degraded` status for that region. The disclaimer
  remains in force for regions outside the trial.

**Recording convention.** When the trial passes, the verdict is
appended to `docs/KNOWN_LIMITATIONS.md` under disclaimers #5 and #6
with: trial scenario, drill window (UTC start and end), responder
count, device count, field network conditions, SLO-by-SLO results
(field measurements), per-model coverage and interval width, regions
and sample counts, and the specific scope certified. Raw trial data
stays in `backend/data/field_trial/` (gitignored). Only the verdict
summary and SHA256 checksums are committed.

**Reference to governing disclaimer.** See disclaimer #6 in
[`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md#6-local-demo-performance-does-not-equal-real-disaster-performance)
(lines 322 to 334): "Performance characteristics observed in the local
demo environment (latency, throughput, concurrency, reliability) do
not represent real-world disaster zone performance." This protocol is
the path to establishing real-world performance bounds. Until it is
executed and passes, disclaimer #6 remains in force unchanged.

---

## References

| Reference | Path | Description |
|---|---|---|
| Hardware spec | `docs/HARDWARE_SPECIFICATION.md` | Device under test (spec only, T12, not built) |
| Physical test plan | `docs/PHYSICAL_TEST_PLAN.md` | Sensor calibration, submersion, recovery, and regional model validation protocols (spec only, T13, not executed) |
| Model data licensing | `docs/MODEL_DATA_LICENSING.md` | Dataset licensing for calibration data (T9) |
| Known limitations | `docs/KNOWN_LIMITATIONS.md` | Disclaimers #3, #5, #6 governing this protocol |
| Conformal calibrator | `backend/app/fusion/calibration.py` | `ConformalCalibrator` validated by section 3 (lines 39 to 100 for fit/predict, line 212 for coverage) |
| SensorSource protocol | `backend/app/sensing/sensor_source.py` | Telemetry contract the trial devices must satisfy (T10) |
| Observation model | `backend/app/models/observation.py` | 23-field observation row the trial ingests |
| Offline operation | `docs/OFFLINE_OPERATION.md` | PWA offline mode and IndexedDB outbox for field network loss |
| Offline prep | `docs/offline-prep.md` | Field server hardware requirements (lines 36 to 52) |
| Security model | `docs/SECURITY_MODEL.md` | RBAC, ABAC, and progressive precision PII redaction |
| Gap-closure plan | `.omo/plans/resqnet-gap-closure.md` | Wave 6, Todo 22 (this task) |

---

## Change Log

| Date | Task | Change |
|---|---|---|
| 2026-07-28 | Wave 6, Todo 22 | Initial protocol document created. Field trial execution deferred. |
| 2026-07-29 | T40 | §4 readiness checklist updated: software gates (Waves 1 to 6) marked GREEN with verified numbers. Hardware and sensor gates marked DEFERRED. Physical trial execution still deferred. |
