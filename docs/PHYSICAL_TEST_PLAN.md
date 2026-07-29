# Physical Test Plan: Rescue-Ball Device and Regional Models

> **SPECIFICATION DOCUMENT ONLY. Physical testing has NOT been executed.**
>
> **EXECUTION of this test plan is a DEFERRED MILESTONE that a software
> worker cannot perform.** The protocols below define what must happen
> before any deployed rescue-ball device or regional model can be called
> certified. No results in this document. No data has been collected.
> No device has been built, submerged, calibrated, recovered, or
> validated against certified targets.

## Software Readiness Status (2026-07-29)

All software gates that gate this test plan are green. The platform,
the ML models, the ingestion pipeline, the reliability layer, and the
auth layer have all passed their Wave 1 through Wave 6 verification.
What remains deferred is the physical execution of the five protocols
below.

| Gate | Wave | Result |
|---|---|---|
| Test stabilization | 1 | 520+ backend tests, 21/21 Playwright e2e, 45/45 frontend unit tests |
| ML models | 2 to 3 | SAR flood mapping (94 MB, IoU 0.67), building damage (129 MB, F1 0.34), incident NLP (438 MB). All 3 manifests `validated` and `signed`. Capabilities endpoint reports `onnx_models: available` |
| Ingestion performance | 4 | 182.3 obs/sec full pipeline, 195.58 obs/sec reduced. DB pool 50, 6 Kafka partitions, 6 workers, batch consumer commits |
| Reliability | 5 | 1-hour soak at 99.26% success rate (162.79 obs/sec). Chaos suite 9/9 pass. Failover: redis 9s, redpanda 10s, minio 14s |
| Frontend and auth | 6 | 0 ESLint warnings, 0 TypeScript errors, 45/45 tests. 15-min access tokens, 7-day refresh tokens, local revocation cache, hybrid fail-closed/fail-open |

**What this does NOT change.** The five protocols below (floodwater
submersion, sensor calibration, certified human-detection validation,
field-recovery testing, regional model validation) are still a DEFERRED
MILESTONE. No device exists. No reference equipment is procured. No IRB
approval is on file. No regional evaluation data is collected. The
software readiness above means the platform is ready to receive and
process data from calibrated sensors. It does not mean any sensor has
been calibrated. See disclaimers #3 and #6 in
[`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md).

## Device under test

The device under test is specified in
[`docs/HARDWARE_SPECIFICATION.md`](./HARDWARE_SPECIFICATION.md)
(spec only, device not built). That document defines the physical
rescue-ball enclosure, sensor stack, power budget, beacon, and
environmental ratings. This test plan references it by planned path.
Where a protocol depends on a hardware parameter (depth rating, beacon
output, IP rating), the value comes from the hardware spec, not from
this document.

The telemetry contract the device must satisfy while under test is
defined by the `SensorSource` protocol in
`backend/app/sensing/sensor_source.py` (planned path, T10). Every
protocol below that requires live telemetry checks the device continues
emitting `read_telemetry()` frames conforming to that contract.

The conformal calibration layer that Protocol 5 validates is
`ConformalCalibrator` in [`backend/app/fusion/calibration.py`](../backend/app/fusion/calibration.py).
The default miscoverage rate is `alpha = 0.1` (90% confidence level)
with an internal 70/30 train/calibration split. Acceptance criteria in
Protocol 5 are stated against that default.

## Governing disclaimers

This plan exists because of two disclaimers in
[`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md) that currently
block certification. Execution of these protocols is the only path to
retiring them.

- **Disclaimer #3** (Simulated Thermal Imaging Not Certified for Human
  Detection): the thermal sensor simulation produces synthetic heat
  signatures. No real thermal sensor has been calibrated or tested.
  The simulated thermal data must not be used to confirm or deny the
  presence of a person in a real disaster zone. Protocols 2 and 3 are
  the required work to change this status.
- **Disclaimer #6** (Local Demo Performance Does Not Equal Real Disaster
  Performance): demo latency, throughput, and reliability numbers do
  not represent real disaster zone performance. Protocols 1, 4, and 5
  are the required work to establish real-world performance bounds.

Until the protocols below are executed by qualified personnel with
certified reference equipment and ethics approval, disclaimers #3 and
#6 remain in force unchanged.

## Scope and prerequisites

This plan covers five protocols:

1. Floodwater submersion testing
2. Sensor calibration against certified reference targets
3. Certified human-detection validation
4. Field-recovery testing
5. Regional model validation on real regional data

Prerequisites that apply across all protocols:

- A built device conforming to `docs/HARDWARE_SPECIFICATION.md`.
- Certified reference equipment with current calibration certificates
  traceable to national standards (NIST or equivalent).
- Test personnel trained on the reference equipment.
- IRB approval for any protocol involving human subjects (Protocols 2
  and 3). No human-subjects testing begins before approval is on file.
- A test log capturing, per run: device serial, firmware revision,
  reference equipment serial and calibration certificate number,
  environmental conditions, operator, timestamp (UTC epoch ms), raw
  readings, and pass/fail verdict.
- All raw test data preserved under
  `backend/data/physical_test/<protocol>/<run_id>/` with SHA256
  checksums. The directory is gitignored. Only the verdict summary and
  checksums are referenced in committed documents.

## Protocol 1: Floodwater Submersion Testing

### Purpose

Establish that the device survives and continues emitting valid
telemetry under the `SensorSource` contract when submerged in the
water conditions representative of a flood deployment. This is the
physical counterpart to Disclaimer #6: demo reliability numbers are
not flood-zone reliability numbers.

### Test matrix

The matrix is the cross of depth, duration, and water condition. Every
cell is a separate run with a fresh or refurbished device per the
reuse policy in Protocol 4.

| Depth | Durations | Water conditions |
|---|---|---|
| 1 m | 24 h, 72 h, 7 days | clear, turbid, brackish, saltwater |
| 3 m | 24 h, 72 h, 7 days | clear, turbid, brackish, saltwater |
| 10 m | 24 h, 72 h, 7 days | clear, turbid, brackish, saltwater |

The 10 m depth is the design depth from the hardware spec. If the
hardware spec rates the device for a different maximum depth, the
deepest cell is set to that rated depth and the table is regenerated
before execution. Depths are measured at the device, not the surface.

Water condition definitions:

- **Clear**: potable water, turbidity below 5 NTU, salinity below
  0.5 ppt, temperature 15 to 25 C.
- **Turbid**: turbidity 50 to 200 NTU (stirred silt load
  representative of post-flood runoff), salinity below 0.5 ppt.
- **Brackish**: salinity 5 to 18 ppt (estuarine range), turbidity
  below 30 NTU.
- **Saltwater**: salinity 30 to 38 ppt (coastal seawater range),
  turbidity below 30 NTU.

Each condition is held within range for the full duration. Salinity
and turbidity are logged at least hourly. Temperature is logged
continuously.

### Telemetry continuity criterion

The device must continue emitting `read_telemetry()` frames conforming
to the `SensorSource` contract in
`backend/app/sensing/sensor_source.py` for the full submerged duration.
A frame is conforming if:

- It is emitted within the contract's declared cadence window.
- All sensor fields declared by the device's `SensorSource` are
  present and within the contract's declared valid ranges.
- The frame's timestamp is UTC epoch milliseconds and monotonically
  non-decreasing within clock skew tolerance.

A run is a telemetry failure if any of these hold:

- A gap between consecutive frames exceeds 2x the declared cadence.
- More than 0.1% of frames in the run are non-conforming.
- The device stops emitting frames before the duration completes.

### Post-submersion inspection

After each run the device is recovered, rinsed per the hardware spec's
recovery procedure, and inspected for:

- Water ingress (visual + internal humidity sensor if equipped).
- Seal deformation or corrosion at enclosure joints.
- Sensor face fouling on optical, acoustic, and thermal ports.
- Battery voltage under load versus pre-submersion baseline.
- Beacon range check per Protocol 4 to confirm the recovery beacon
  still functions.

### Pass/fail criteria

A cell passes when all of these are true:

- Telemetry continuity criterion met for the full duration.
- No water ingress detected.
- Post-submersion beacon range is within 10% of the pre-submersion
  baseline measured in Protocol 4.
- Battery voltage under load is within 10% of pre-submersion baseline.

A cell fails on any breach above. A failure at any depth for a given
water condition and duration fails that condition at all greater
depths for the same duration (no credit for surviving deeper if a
shallower cell leaked).

### Acceptance

The device is rated for floodwater deployment at a given depth and
duration only when all four water conditions pass at that depth and
duration. The rated deployment envelope is the union of passing cells.
The rated envelope is recorded in the hardware spec's environmental
ratings section and in `docs/KNOWN_LIMITATIONS.md` as a partial
retirement of Disclaimer #6.

## Protocol 2: Sensor Calibration Against Certified Reference Targets

### Purpose

Establish that each sensor in the device stack reads within stated
accuracy against certified reference targets traceable to national
standards. This is the prerequisite for Protocol 3: a human-detection
claim is only credible if the underlying sensors are calibrated.

### Reference targets

| Sensor | Reference equipment | Required accuracy | Traceability |
|---|---|---|---|
| Thermal | Blackbody calibration source | temperature accuracy plus or minus 0.1 C over the 0 to 50 C range, emissivity 0.97 to 0.99 | NIST-traceable |
| IMU | Rate table | angular rate accuracy plus or minus 0.01 deg/s over plus or minus 500 deg/s, angle accuracy plus or minus 0.05 deg | NIST-traceable |
| Acoustic | Reference microphone + calibrator | SPL accuracy plus or minus 0.5 dB over 20 Hz to 20 kHz, class 1 per IEC 61672 | NIST-traceable |
| Vibration | Reference accelerometer + shaker | acceleration accuracy plus or minus 0.01 m/s^2 over 0.5 to 200 Hz | NIST-traceable |

Each reference instrument must have a current calibration certificate
on file. Certificates expire per their issuing lab's interval. An
expired certificate disqualifies the run.

### Calibration procedure

For each sensor, the procedure is:

1. **Warm-up.** Stabilize the device and reference equipment at the
   test environment for the warm-up time stated in the hardware spec,
   minimum 15 minutes.
2. **Baseline.** Record the reference and device readings at zero
   stimulus (or ambient for thermal). Compute the zero offset.
3. **Sweep.** Apply the reference stimulus across the sensor's full
   declared range in at least 10 evenly spaced steps. At each step,
   hold the stimulus stable for at least 30 seconds and record the
   mean of at least 100 device samples alongside the reference value.
4. **Repeatability.** Repeat the full sweep 3 times without
   repositioning. Compute the per-step standard deviation across
   repeats.
5. **Hysteresis.** Sweep up then immediately down through the same
   steps. Compute the per-step up/down difference.
6. **Record.** Store raw samples, reference values, computed offsets,
   sweep residuals, repeatability std, and hysteresis deltas under
   `backend/data/physical_test/protocol2/<run_id>/`.

### Acceptance criteria per sensor

A sensor passes calibration when all of these hold across all steps
and repeats:

- **Accuracy.** The mean device reading at each step is within the
  sensor's declared accuracy band of the reference value. Declared
  accuracy bands come from the hardware spec. If the hardware spec
  does not state a band, the reference equipment accuracy above is the
  band.
- **Repeatability.** Per-step standard deviation across the 3 repeats
  is below one third of the declared accuracy band.
- **Hysteresis.** Per-step up/down difference is below one quarter of
  the declared accuracy band.
- **Zero offset.** The baseline zero offset is within the declared
  accuracy band and is recorded for use in field recalibration.

A sensor that fails any criterion is marked `calibration_failed` and
is not eligible to participate in Protocol 3.

### Certified human-detection test scenarios (IRB-required)

A subset of Protocol 2 establishes that the thermal and acoustic
sensors produce usable human-signature readings under controlled
conditions. This subset requires IRB approval before any data
collection. The scenarios below are the calibration-grade scenarios:
controlled environment, informed consent, no deception, no distress.

The certified human-detection validation itself is Protocol 3. The
scenarios here only confirm the sensors can resolve a human signature
at all against a known target.

| Scenario | Setup | What is measured |
|---|---|---|
| Single stationary person, frontal | 1 subject at 5 m, 10 m, 20 m, ambient to 30 C | thermal contrast vs background, SPL of breathing and voice |
| Single stationary person, lateral | same distances, subject turned 90 deg | thermal contrast change, acoustic directivity |
| Seated vs standing | 1 subject at 10 m, both postures | thermal silhouette area, acoustic signature |
| Group of 3, mixed postures | 3 subjects at 10 m | thermal cluster separation, acoustic sum |

Each scenario is run with the calibrated thermal and acoustic sensors
from the previous section. The reference ground truth is the known
subject count, distance (laser-measured), and posture, recorded by the
test operator. No detection decision is made by the device in Protocol
2. The output is raw sensor data plus the reference ground truth, both
archived under `backend/data/physical_test/protocol2/human_scenarios/`.

### IRB and consent

Before any human-subjects data collection:

- An Institutional Review Board (or equivalent ethics body) reviews and
  approves the protocol, consent form, and data handling plan.
- Each subject signs an informed consent form covering: purpose,
  procedures, risks (minimal, thermal and acoustic only), data
  retention, and right to withdraw at any time without penalty.
- Data is stored de-identified. Subject names are not in the test log.
  A separate consent roster keyed by subject ID is held by the IRB
  office, not by the engineering team.
- Minors are excluded. Vulnerable populations are excluded unless the
  IRB grants a specific waiver with additional safeguards.

A run without IRB approval on file is invalid and its data cannot be
used to retire Disclaimer #3.

## Protocol 3: Certified Human-Detection Validation

### Purpose

Establish, with statistical confidence, the false-positive and
false-negative rates of the device's human-detection output against
human-labeled ground truth. This is the only protocol that can retire
Disclaimer #3. Until this protocol is executed and passes, the
thermal-based human-detection output remains NOT certified.

> **Explicit status.** As of this document's writing, Protocol 3 has
> NOT been executed. The device's human-detection output is NOT
> certified. This is true regardless of any demo, simulation, or
> synthetic-data result elsewhere in the repository. Certification
> requires this protocol to pass in full.

### Gold standard

The gold standard is human-labeled ground truth. For each test frame
or window, a human annotator labels whether a person is present, how
many, and where in the sensor field of view. The device's
human-detection output is compared against this label.

Annotator requirements:

- At least 3 independent annotators per frame.
- Annotators trained on a written labeling guide with worked examples.
- Inter-annotator agreement measured by Fleiss' kappa. Frames with
  kappa below 0.6 are reviewed and relabeled or excluded with the
  reason recorded.
- Annotators do not see the device's output while labeling. The
  labeling interface presents only the raw sensor data.

### Statistical targets

| Metric | Target | Minimum sample |
|---|---|---|
| False-positive rate | below 5% | 1000 negative windows |
| False-negative rate | below 5% | 1000 positive windows |
| Confidence interval | 95% CI upper bound below 5% for both rates | as above |
| Total detections sampled | at least 1000 positive plus 1000 negative | 2000 windows minimum |

A window is a fixed-duration slice of the sensor stream (the duration
is set by the device's declared detection cadence, recorded in the
hardware spec). Positive windows contain at least one person per the
gold standard. Negative windows contain zero persons.

The 95% confidence interval is computed by the Wilson score method on
each rate. The target is that the upper bound of the interval is
below 5%, not merely that the point estimate is below 5%. A point
estimate below 5% with an upper bound above 5% is a fail.

### Test scenarios

The scenario set must cover the conditions in which the device would
be deployed. Each scenario is run with the calibrated sensors from
Protocol 2 and the IRB-approved subject pool.

| Scenario | Subjects | Condition | Windows target |
|---|---|---|---|
| Single person, open field | 1 | clear line of sight, 5 to 30 m | 200 positive, 200 negative |
| Single person, partial occlusion | 1 | 30 to 70% of body occluded by vegetation or debris | 200 positive, 200 negative |
| Group of 3 to 5, open field | 3 to 5 | clear line of sight, 5 to 30 m | 200 positive, 200 negative |
| Group of 3 to 5, partial occlusion | 3 to 5 | mixed occlusion per subject | 200 positive, 200 negative |
| Thermal contrast, cold background | 1 to 3 | background 0 to 10 C, subjects 30 to 37 C | 200 positive, 200 negative |
| Thermal contrast, warm background | 1 to 3 | background 25 to 35 C, subjects 30 to 37 C (low contrast) | 200 positive, 200 negative |
| No person, distractor heat sources | 0 | warm animals, vehicles, sun-heated rocks | 0 positive, 1000 negative |

The distractor scenario is required. A device that detects humans
reliably but fires on warm animals or sun-heated surfaces fails in the
field. The 1000 negative windows in the distractor scenario count
toward the false-positive sample.

### Pass/fail criteria

Protocol 3 passes when all of these are true:

- The 95% CI upper bound on the false-positive rate is below 5% across
  all negative windows (all scenarios combined).
- The 95% CI upper bound on the false-negative rate is below 5% across
  all positive windows (all scenarios combined).
- No single scenario has a point-estimate false-positive or
  false-negative rate above 8%. A scenario above 8% is a fail even if
  the pooled rate passes.
- Inter-annotator Fleiss' kappa is at least 0.6 on the final labeled
  set.
- IRB approval was on file before any data collection.

A fail on any criterion means the device's human-detection output
remains NOT certified. Disclaimer #3 stays unchanged. The failure is
recorded with the failing scenario, rate, and CI, and the device is
returned to engineering for revision before retest.

### What this protocol does NOT certify

Passing Protocol 3 certifies the device's human-detection output
under the tested conditions only. It does not certify:

- Detection in conditions outside the tested scenario set (e.g.,
    night operation, heavy rain, sub-freezing backgrounds).
- Detection through opaque cover (walls, dense rubble, deep water).
- Any medical or life-safety determination (see Disclaimer #4).
- Detection of non-human subjects or animals.
- Performance on populations not represented in the IRB-approved
    subject pool.

Each extension of the certification envelope requires a new protocol
execution with the added conditions and a new IRB amendment if new
subject populations are involved.

## Protocol 4: Field-Recovery Testing

### Purpose

Establish that a deployed device can be retrieved within a target time
window, that its recovery beacon and GPS are accurate enough to locate
it, and that a recovered device can be returned to service. This is
the physical counterpart to Disclaimer #6's note that demo performance
is not disaster performance: recovery is a field operation, not a
simulator output.

### Retrieval procedure

The retrieval procedure is defined in the hardware spec and exercised
end to end in this protocol. The minimum steps:

1. Deploy the device at a known GPS coordinate (survey-grade reference,
   accuracy better than 1 m).
2. Start the recovery clock at the moment deployment is complete.
3. Operator navigates to the device using the device's beacon and GPS
   output only. No prior knowledge of the exact landing spot is used.
4. Operator confirms visual contact and retrieves the device.
5. Stop the recovery clock. Record the elapsed time, the operator's
   final GPS fix, and the device's final GPS fix.

### Beacon range test

The recovery beacon must be locatable at a minimum of 100 m
line-of-sight. The test:

- Place the device at a fixed point with the beacon active.
- Measure the received signal strength at 25 m, 50 m, 75 m, 100 m,
  125 m, and 150 m along a clear line-of-sight path.
- Record the beacon's declared effective range (the distance at which
  the signal is at least 3 dB above the noise floor).
- Repeat the test with one intervening obstruction representative of
  post-flood debris (a wood pile or equivalent) at the midpoint.

Pass criterion: the line-of-sight effective range is at least 100 m.
The obstructed range is recorded but is not a pass/fail gate for the
100 m rating. The obstructed range informs the field operations
manual.

### GPS accuracy test

The device's GPS fix must be within plus or minus 5 m of the
survey-grade reference coordinate. The test:

- Power the device outdoors with a clear sky view.
- Record 100 consecutive GPS fixes at 1 Hz.
- Compute the 95th-percentile circular error probable (CEP) against
  the reference coordinate.
- Repeat with partial sky view (representative of urban canyon or
  tree canopy, 40 to 60% sky obstruction).

Pass criterion: the 95th-percentile CEP under clear sky is at or below
5 m. The partial-sky CEP is recorded and informs the field operations
manual but is not a pass/fail gate for the 5 m rating.

### Recovery time target

The target is recovery in under 30 minutes from deployment completion
to device in hand. The test:

- Run 10 independent retrieval trials at 10 different deployment
  sites spanning the deployment envelope from Protocol 1 (depths,
  water conditions, and durations within the rated envelope).
- Record the elapsed time for each trial.
- Compute the 90th-percentile recovery time across the 10 trials.

Pass criterion: the 90th-percentile recovery time is below 30 minutes.
A single trial above 30 minutes is allowed as long as the 90th
percentile passes. Two or more trials above 30 minutes is a fail.

### Device reuse validation

A recovered device must be returnable to service. After each retrieval
trial:

1. Rinse and inspect per the hardware spec's recovery procedure.
2. Run the Protocol 2 calibration sweep on each sensor.
3. Run the Protocol 4 beacon range and GPS accuracy tests again.

Pass criterion: the device passes Protocol 2 calibration and the
beacon and GPS tests after recovery. A device that survives recovery
but drifts out of calibration is returned to engineering. The reuse
count (how many deploy-recover cycles a device survives before
calibration drift) is recorded as a durability metric.

### Acceptance

The device is rated field-recoverable when the beacon, GPS, recovery
time, and reuse criteria all pass. The rating is recorded in the
hardware spec and partially retires Disclaimer #6 for the recovery
operation. Recovery in conditions outside the tested envelope (night,
heavy weather, swift water) is not certified by this protocol.

## Protocol 5: Regional Model Validation

### Purpose

Establish that the deployed ML models produce conformal prediction
intervals whose empirical coverage on real regional data matches the
theoretical guarantee. This is the validation that the
`ConformalCalibrator` in `backend/app/fusion/calibration.py` actually
delivers its stated coverage when the data distribution shifts from
the calibration set to a real region.

### Models in scope

| Model | Role | Current calibration status |
|---|---|---|
| `sar-flood-mapping` | flood extent from Sentinel-1 SAR | calibrated on Sen1Floods11 (see Disclaimer #5) |
| `building-damage` | damage grade from satellite imagery | fixture-data only, marked `degraded` |
| `incident-nlp` | incident extraction from text reports | no public calibration dataset, marked `degraded` |

The `degraded` status for `building-damage` and `incident-nlp` is
recorded in `docs/KNOWN_LIMITATIONS.md` under Disclaimer #5. Protocol
5 is the path to move those models out of `degraded` status, and to
confirm the `sar-flood-mapping` calibration holds on regions beyond
Sen1Floods11.

### Conformal coverage criterion

The `ConformalCalibrator` is fit with `alpha = 0.1`, giving a nominal
90% confidence level. The acceptance band for empirical coverage on
real regional data is the closed interval `[0.85, 0.95]`.

- Coverage below 0.85 means the intervals are too narrow: the model
  is overconfident and the intervals do not contain the true value
  often enough. This is a safety failure for a decision-support tool.
- Coverage above 0.95 means the intervals are too wide: the model is
  underconfident and the intervals are not informative. This is a
  utility failure.

The coverage is computed by `ConformalCalibrator.compute_coverage(y_true,
y_pred_lower, y_pred_upper)` on the held-out regional evaluation set.
The interval bounds come from `ConformalCalibrator.predict(X)`'s
`interval_lower` and `interval_upper` fields.

### Minimum sample sizes

| Model | Minimum regional evaluation samples | Rationale |
|---|---|---|
| `sar-flood-mapping` | 500 chips spanning at least 3 flood events | per-event variance requires multiple events |
| `building-damage` | 1000 buildings spanning at least 2 damage events | damage grade is per-building, needs building-level labels |
| `incident-nlp` | 500 incident reports spanning at least 3 incident types | type diversity drives NLP coverage |

A chip is a Sentinel-1 SAR tile plus its human-labeled water mask. A
building is a single building footprint plus its damage grade label
(per xBD or equivalent scheme). An incident report is a single text
report plus its human-labeled incident type and extracted fields.

Samples below the minimum cannot produce a coverage verdict. A model
with fewer than the minimum samples is marked
`regional_validation_insufficient_samples` and remains in its current
status.

### Regional diversity requirements

The regional evaluation data must come from regions outside the
original calibration set. Specifically:

- For `sar-flood-mapping`: the evaluation regions must not overlap
  with the Sen1Floods11 event set. At least 3 distinct flood events
  from at least 2 distinct geographic regions (different continents
  preferred) are required.
- For `building-damage`: the evaluation events must not overlap with
  the xBD training events (if xBD is used for calibration). At least 2
  distinct damage events from at least 2 distinct regions.
- For `incident-nlp`: the evaluation reports must not be drawn from
  the same source as any calibration data. At least 3 distinct
  incident types (e.g., flood, fire, landslide) from at least 2
  distinct reporting agencies or regions.

Regional diversity is a gate. A coverage verdict from a single region
or single event does not retire Disclaimer #5 for that model. The
verdict is recorded per region and per event, and the pooled coverage
across all regions is the headline number.

### Acceptance criteria per model

A model passes regional validation when all of these hold:

- The minimum sample size is met.
- The regional diversity requirements are met.
- The pooled empirical coverage across all evaluation regions is
  within `[0.85, 0.95]` for `alpha = 0.1`.
- No single region's coverage is below 0.80 or above 0.98. A region
  outside this wider band is a per-region fail even if the pooled
  coverage passes. The per-region failure is recorded and the model
  is marked `regional_coverage_drift` for that region.
- The mean interval width on the regional set is within 1.5x of the
  mean interval width on the calibration set. A width blow-up
  indicates the model is hedging against distribution shift rather
  than producing useful intervals.

A model that passes is moved out of `degraded` status (for
`building-damage` and `incident-nlp`) or has its calibration
confirmed for the tested regions (for `sar-flood-mapping`). The
verdict is recorded in `docs/KNOWN_LIMITATIONS.md` under Disclaimer
#5 with the regions, sample counts, coverage, and interval width.

### Recalibration cadence

Conformal coverage drifts over time as the data distribution shifts.
Protocol 5 is not a one-time gate. The cadence:

- Re-run Protocol 5 for each model at least once per calendar quarter
  on fresh regional data.
- Trigger an out-of-cycle re-run when a deployed model's online
  coverage estimate (computed on a rolling window of field
  predictions with delayed ground truth) drops below 0.85 or exceeds
  0.95 for two consecutive weeks.
- Record each re-run's verdict in the same location as the initial
  validation.

A model that fails a re-run is returned to `degraded` status until a
passing re-run is recorded.

## Deferred execution milestone

This section records the deferred milestone in the terms the
orchestrator and any future worker need.

**Milestone:** Execute Protocols 1 through 5 with certified reference
equipment, IRB approval, and real regional data. Record verdicts in
`docs/KNOWN_LIMITATIONS.md` and the hardware spec.

**Status:** NOT STARTED. No device exists. No reference equipment is
procured. No IRB approval is on file. No regional evaluation data is
collected. This document is the specification only.

**Owner:** Not a software worker. Execution requires hardware
engineering, test engineering, an IRB-approved human-subjects protocol,
certified reference equipment, and regional data partners. A software
worker can update this spec, wire verdict-recording into
`docs/KNOWN_LIMITATIONS.md`, or build tooling to ingest regional
evaluation data. A software worker cannot execute the protocols.

**Retirement of disclaimers:**

- Disclaimer #3 is retired only when Protocol 3 passes in full.
  Partial retirement (e.g., sensors calibrated but human-detection
  not yet validated) is recorded as a partial retirement with the
  specific scope that remains uncertified.
- Disclaimer #6 is retired only when Protocols 1, 4, and 5 pass in
  full for the rated deployment envelope. Partial retirement is
  recorded per protocol and per condition.

**Recording convention.** When a protocol passes, the verdict is
appended to `docs/KNOWN_LIMITATIONS.md` under the relevant disclaimer
with: protocol number, run ID, date (UTC), regions and sample counts
where applicable, coverage and interval width where applicable, and
the specific scope certified. The raw data stays in
`backend/data/physical_test/` (gitignored). Only the verdict summary
and SHA256 checksums are committed.

## References

- [`docs/HARDWARE_SPECIFICATION.md`](./HARDWARE_SPECIFICATION.md):
  device under test (spec only, T12).
- `backend/app/sensing/sensor_source.py`: `SensorSource` telemetry
  contract (planned, T10).
- [`backend/app/fusion/calibration.py`](../backend/app/fusion/calibration.py):
  `ConformalCalibrator` validated by Protocol 5.
- [`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md): Disclaimer
  #3 (thermal not certified for human detection), Disclaimer #5 (ML
  depends on weights and calibration data), Disclaimer #6 (demo
  performance is not disaster performance).

---

## Change Log

| Date | Task | Change |
|---|---|---|
| 2026-07-28 | Wave 6, Todo 13 | Initial test plan document created. Physical test execution deferred. |
| 2026-07-29 | T40 | Added Software Readiness Status section. All software gates (Waves 1 to 6) green. Physical test plan unchanged and still deferred. |
