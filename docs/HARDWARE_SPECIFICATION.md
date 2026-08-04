# Hardware Specification: Rescue-Ball Device

> **SPECIFICATION DOCUMENT ONLY.**
> The physical device described in this document has **NOT** been built,
> procured, or manufactured. Physical build, procurement, and manufacturing
> are a **DEFERRED MILESTONE** that a software worker cannot perform.
>
> This document specifies the engineering requirements for a future hardware
> team to follow. It is the real-world counterpart to the digital twin in
> `backend/app/simulator/rescue_ball.py`. See disclaimers #1 and #2 in
> [`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md#1-rescue-ball-is-simulated-not-physical-hardware)
> (lines 231 and 241).

**Status:** SPEC ONLY (not built, deferred)
**Locked decision D1:** hardware = software-readiness + spec docs. Physical
build is deferred until a hardware team is funded and assigned.
**Related task:** Wave 4, Todo 12 (`resqnet-gap-closure` plan)
**Unblocks:** T13 (physical test-plan doc references this spec)

---

## Software Readiness Status (2026-07-29)

All software work in the `resqnet-gap-closure` plan (Waves 1 through 6) is
complete. The platform that would ingest telemetry from this device has
passed every software gate. This section records the software state so a
hardware team knows the receiving end is ready.

| Wave | Gate | Result |
|---|---|---|
| 1 | Test stabilization | 520+ backend tests, 21/21 Playwright e2e, 45/45 frontend unit tests |
| 2 to 3 | Real ML models | SAR flood mapping (94 MB, IoU 0.67), building damage (129 MB, F1 0.34), incident NLP (438 MB, binary classification). All 3 manifests `validated` and `signed`. `GET /api/capabilities` reports `onnx_models: available` |
| 4 | Ingestion performance | 100+ obs/sec sustained. 182.3 obs/sec full pipeline, 195.58 obs/sec reduced. DB pool raised to 50 connections, 6 Kafka partitions, 6 workers, batch consumer commits, async confidence scoring |
| 5 | Reliability | 1-hour soak at 99.26% success rate (162.79 obs/sec). Chaos suite 9/9 pass (redis, redpanda, minio kill, overlapping failures, container restarts, disk pressure, network loss). Measured failover: redis 9s, redpanda 10s, minio 14s |
| 6 | Frontend and auth | 0 ESLint warnings, 0 TypeScript errors, 45/45 frontend tests. Auth hardening: 15-min access tokens, 7-day refresh tokens, local revocation cache, hybrid fail-closed/fail-open policy with break-glass audit |

**What this does NOT change.** The physical hardware described in sections 1
through 8 below is still a DEFERRED MILESTONE. No device has been built,
procured, or manufactured. No physical testing has been done. The software
readiness above means the platform is ready to receive telemetry from a real
device. It does not mean a real device exists. See disclaimers #1 and #2 in
[`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md).

---

## Purpose and Scope

This specification defines the physical rescue ball: a spherical, buoyant,
sensor-equipped device airdropped or placed into flooded urban areas to
provide real-time situational awareness telemetry. The device emits
observations that flow into the ResQNet platform through the sensor
ingestion pipeline.

The digital twin (`RescueBallDevice` in
`backend/app/simulator/rescue_ball.py:62`) models this device in software.
That simulator uses `rng.gauss()` for all sensor readings and is 100%
synthetic. This document describes the real hardware that would replace the
simulator's synthetic outputs with measured data.

The spec covers eight subsystems:

1. Bill of Materials (BOM)
2. Mechanical enclosure
3. Communications
4. Power and battery
5. Deployment mechanism
6. Recovery
7. Mobility
8. Integration contract

Each subsystem maps to fields and behaviors in the simulator so a hardware
engineer can verify parity between the spec and the software contract.

---

## 1. Bill of Materials (BOM)

The BOM lists recommended parts for each functional block. Part numbers are
engineering recommendations, not procurement commitments. A hardware team
should validate availability, lead times, and export compliance before
ordering.

### 1.1 Compute and MCU

| Function | Recommended Part | Notes |
|---|---|---|
| Application processor | Raspberry Pi Zero 2 W | 1 GHz quad-core ARM, 512 MB RAM, runs Python telemetry agent. Handles MQTT, JSON encoding, sensor polling. |
| Microcontroller (low-power) | ESP32-S3 | Manages deep-sleep wake, battery monitoring, beacon mode when Pi is asleep. Reduces standby drain. |
| RTC | DS3231 | Battery-backed real-time clock for timestamp accuracy when GPS is unavailable. |

The dual-processor design lets the ESP32 keep the beacon alive while the Pi
sleeps. This matches the simulator's standby drain rate of 0.001 %/s
(`rescue_ball.py:27`), which is 5x lower than the deployed rate of 0.005 %/s
(`rescue_ball.py:27`).

### 1.2 Sensors

| Sensor | Recommended Part | Simulator Field | Notes |
|---|---|---|---|
| Thermal camera | Melexis MLX90640 IR array (32x24) | `device_temperature`, `thermal_sensor_status` | 55 deg horizontal FOV, 0.5-1 Hz refresh. Detects heat signatures near water surface. The simulator's `thermal_hotspot_c` fault injection (`rescue_ball.py:191`) models hotspot detection. |
| IMU | TDK InvenSense ICM-42688-P (6-axis accel + gyro) | `imu_reading` dict (`rescue_ball.py:96, 165-176`) | Outputs `accel_x`, `accel_y`, `accel_z` (m/s^2), `gyro_x`, `gyro_y`, `gyro_z` (rad/s). Matches the six IMU keys the simulator emits. |
| Acoustic microphone | SPH0645LM4H-B I2S MEMS mic | `acoustic_reading` dict (`rescue_ball.py:97, 178-185`) | Outputs `db_level` (dB SPL) and `frequency_peak` (Hz). Matches the two acoustic keys the simulator emits. |
| Vibration sensor | ADXL355 (3-axis, low-noise) | `imu_reading` (extended) | High-resolution vibration for structural damage detection. Adds `vibration_rms` to the IMU dict. |
| Seismic sensor | Raspberry Shake 1D geophone | `imu_reading` (extended) | Detects ground motion if the ball beaches on solid ground. Adds `seismic_velocity` to the IMU dict. |
| GPS | u-blox NEO-M9N | `lon`, `lat`, `altitude` (`rescue_ball.py:81-83`) | 1.5 m CEP accuracy. Provides position for the geometry field in observations. |
| Battery gauge | MAX17048 fuel gauge | `battery_pct` (`rescue_ball.py:87`) | Reports state of charge as 0-100 percent. Drives `estimated_remaining_runtime` (`rescue_ball.py:88`). |
| Temperature (internal) | DS18B20 | `device_temperature` (`rescue_ball.py:92`) | Monitors enclosure internal temp. The simulator relaxes this toward 38 C deployed, 25 C standby (`rescue_ball.py:34-39`). |

### 1.3 Communications

| Function | Recommended Part | Simulator Field | Notes |
|---|---|---|---|
| LTE modem | SIMCom SIM7600G-H | `link_type: "lte"` (`rescue_ball.py:89`) | Cat-4, global bands. Primary uplink. |
| Satellite module | Swarm Tile (or Iridium 9603N as alternative) | `link_type: "satellite"` (`rescue_ball.py:89`) | Fallback when LTE is unavailable. Low bandwidth, store-and-forward. |
| LoRa radio | Semtech SX1262 (via ESP32) | `link_type` fallback | Last-resort mesh relay to other balls or a shore base station. |
| GPS antenna | u-blox ANN-MB-00 | position accuracy | Multi-band, compact patch antenna. |

### 1.4 Power

| Function | Recommended Part | Notes |
|---|---|---|
| Battery | LiPo 3.7V 8000 mAh (29.6 Wh) | See section 4 for runtime analysis. |
| BMS | TI BQ25895 charge controller | USB-C charging, cell balancing, overcurrent protection. |
| DC-DC boost | TPS61023 (3.7V to 5V) | Powers the Pi Zero 2 W. |
| LDO | AP2112K-3.3 | Powers ESP32, sensors, and I2C bus. |

### 1.5 Enclosure

| Function | Recommended Part | Notes |
|---|---|---|
| Shell | Custom-molded ABS or polycarbonate hemisphere pair | See section 2 for IP rating and impact requirements. |
| O-ring seal | EPDM 70-duo O-ring, 2mm cross-section | Primary water ingress barrier at the equator seam. |
| Pressure vent | Gore-Tex Goretex PolyVent XS | Equalizes pressure without leaking. |

### 1.6 Cost Estimate (per unit, low volume)

| Block | Estimated Cost (USD) |
|---|---|
| Compute (Pi Zero 2 W + ESP32-S3 + RTC) | 45 |
| Sensors (thermal, IMU, acoustic, vibration, seismic, GPS, fuel gauge, temp) | 180 |
| Communications (LTE + satellite + LoRa + GPS antenna) | 220 |
| Power (battery + BMS + regulators) | 35 |
| Enclosure (shell + seals + vent) | 60 |
| PCB and assembly | 50 |
| **Total (per unit, qty 1-10)** | **~590** |

Costs drop significantly at volume. A production run of 100+ units could
bring per-unit cost below 400 USD. These figures are planning estimates, not
quotes.

---

## 2. Mechanical Enclosure

### 2.1 Form Factor

The device is a sphere. A sphere has no preferred orientation on impact or
in water, which simplifies deployment and buoyancy design.

| Parameter | Specification | Rationale |
|---|---|---|
| Diameter | 180 mm (7.1 in) | Large enough to house the BOM. Small enough for one-handed deployment and drone carry. |
| Mass | 1.2 kg target, 1.5 kg maximum | Must float (see buoyancy below). Keeps airdrop kinetic energy manageable. |
| Surface finish | Matte high-visibility orange (RAL 2008) | Visible in muddy floodwater and from the air. |

### 2.2 Ingress Protection

| Parameter | Specification | Rationale |
|---|---|---|
| IP rating | IP68 (1.5 m, 72 hours) | Floodwater submersion is the expected operating environment. IP68 is the minimum. IP69K (high-pressure jet) is preferred if the ball may be hosed down during recovery. |
| Seam design | Single equatorial O-ring seal | One seal is easier to inspect and replace than multiple penetrations. |
| Cable penetrations | None (all sensors internal, antennas internal or potted) | Eliminates the most common leak path. |
| Test pressure | 30 kPa internal (0.3 atm overpressure) | Slight positive pressure inside the enclosure. If the seal fails, the vent releases pressure outward, not inward. This makes a leak detectable before water enters. |

The simulator tracks `enclosure_status` with values `ok`, `damaged`, or
`breached` (`rescue_ball.py:93`). The hardware must report `breached` when
the internal humidity sensor detects moisture or the pressure differential
drops below threshold. The `enclosure_breached` health flag
(`rescue_ball.py:199`) must fire on the same condition.

### 2.3 Buoyancy

The ball must float in freshwater and seawater with partial submersion. The
antenna array and thermal camera lens should sit above the waterline.

| Parameter | Specification |
|---|---|
| Minimum freeboard | 30 mm (12% of diameter) above waterline in freshwater (1000 kg/m^3) |
| Waterline target | 40% submersion by volume in freshwater |
| Ballast | Removable ballast weights at the south pole to self-right the ball and keep antennas up |
| Floatation | Closed-cell foam core (EVA, density 30 kg/m^3) filling unused internal volume |

A 180 mm sphere displaces approximately 3.05 liters of freshwater. At 1.2 kg
mass, the ball displaces 1.2 liters to float, leaving 1.85 liters of foam
and air. This gives a 60% submersion depth, which is deeper than target. The
foam core reduces effective displaced volume. A hardware engineer should
verify the buoyancy calculation with the actual BOM mass and foam density
before tooling.

### 2.4 Impact Resistance

The ball must survive an airdrop landing at terminal velocity without
breaching the enclosure or damaging internal components.

| Parameter | Specification |
|---|---|
| Drop survival | 10 m/s vertical impact onto concrete (terminal velocity with a small drogue chute) |
| Impact absorption | 20 mm closed-cell EVA foam lining the inner shell |
| Component mounting | All PCBs potted in silicone (EGS-3HT) or mounted on isolation standoffs |
| Lens protection | Thermal camera and GPS antenna behind recessed, impact-resistant windows (Gorilla Glass or sapphire) |

The simulator does not model impact dynamics. The `enclosure_status` field
starts at `ok` and transitions to `damaged` or `breached` only through fault
injection. Real hardware must detect impact damage through the IMU (high-g
event logging) and report it as `enclosure_status: "damaged"` in the next
telemetry packet.

### 2.5 Thermal Operating Range

| Condition | Range |
|---|---|
| Operating temperature | -10 C to +55 C |
| Storage temperature | -20 C to +70 C |
| Internal temperature limit | 70 C (auto-shutdown to prevent battery thermal runaway) |

The simulator relaxes `device_temperature` toward 38 C in deployed state
(`rescue_ball.py:35, 159-163`). The real device should report internal
temperature through the DS18B20 sensor. The `high_temp` health flag fires at
50 C (`rescue_ball.py:44`), which gives a 20 C margin before the 70 C
auto-shutdown threshold.

---

## 3. Communications

### 3.1 Link Priority and Fallback Chain

The device uses three radio links in priority order. The simulator models
this through `link_type` with values `wifi`, `lte`, `satellite`, and `none`
(`rescue_ball.py:89`). The hardware spec replaces `wifi` with `lora` as the
lowest-priority link, since wifi is unrealistic in a flood zone.

| Priority | Link | Use Case | Bandwidth | Latency |
|---|---|---|---|---|
| 1 | LTE (SIM7600G-H) | Primary uplink when cell towers are alive | 1-10 Mbps | 100-500 ms |
| 2 | Satellite (Swarm/Iridium) | Fallback when LTE is down or out of range | 1-100 kbps | 1-60 s (store-and-forward) |
| 3 | LoRa (SX1262) | Mesh relay to other balls or a shore base station | 0.3-50 kbps | 1-10 s |
| 0 | None | No link available. Buffer locally, retry on next link acquisition. | 0 | N/A |

When `link_type` is `none`, the simulator sets `signal_quality` to 0 and
`packet_loss` to 100 (`rescue_ball.py:146-148`). The hardware must do the
same and buffer telemetry to internal flash (at least 24 hours of samples at
1 Hz) for later upload.

### 3.2 MQTT Broker Configuration

The device connects to an MQTT broker. The `MQTTSensorSource` adapter
(planned: `backend/app/sensing/adapters/mqtt_sensor.py`) subscribes to the
device's telemetry topics and feeds observations into the platform through
the `SensorSource` protocol (planned:
`backend/app/sensing/sensor_source.py`).

| Parameter | Value |
|---|---|
| Broker | Mosquitto or EMQX, TLS-enabled (port 8883) |
| Client ID | `resqnet-ball-{device_id}` |
| Authentication | Mutual TLS (client cert per device) or username/password per org |
| Keepalive | 60 seconds |
| QoS | 1 (at-least-once delivery) |
| Last Will and Testament | Topic: `resqnet/{org_id}/{incident_id}/devices/{device_id}/lwt`, payload: `{"online": false}` |
| Clean session | false (broker retains queued messages while device is offline) |

### 3.3 Topic Structure

```
resqnet/{org_id}/{incident_id}/devices/{device_id}/telemetry    # sensor data (publish, device -> broker)
resqnet/{org_id}/{incident_id}/devices/{device_id}/health       # health flags (publish, device -> broker)
resqnet/{org_id}/{incident_id}/devices/{device_id}/lwt          # last will (publish, broker retains)
resqnet/{org_id}/{incident_id}/devices/{device_id}/cmd          # commands (subscribe, platform -> device)
```

The `org_id` and `incident_id` in the topic path match the tenancy fields
required by the `SensorSource` protocol (planned:
`backend/app/sensing/sensor_source.py`) and the `Observation` model
(`backend/app/models/observation.py:103-104`). The `device_id` is a ULID
assigned at provisioning time.

### 3.4 Data Protocol

Telemetry is JSON over MQTT. Each message is a single JSON object, UTF-8
encoded, under 4 KB (fits in a single MQTT packet and a single LoRa frame
when compressed). The exact payload format is specified in section 8
(Integration Contract).

For satellite links where bandwidth is scarce, the device compresses the
JSON payload with gzip before transmission. The `MQTTSensorSource` adapter
detects gzip magic bytes (0x1f 0x8b) and decompresses before parsing.

---

## 4. Power and Battery

### 4.1 Battery Capacity

| Parameter | Value |
|---|---|
| Chemistry | Lithium polymer (LiPo) |
| Nominal voltage | 3.7 V |
| Capacity | 8000 mAh (29.6 Wh) |
| Cells | 1S (single cell) |
| Charge cycles | 500+ to 80% capacity |
| Charge time | 4 hours (USB-C PD, 5V 2A) |

### 4.2 Runtime Targets

The simulator computes `estimated_remaining_runtime` as
`battery_pct / drain_rate` (`rescue_ball.py:140`). The drain rates by
deployment state are defined at `rescue_ball.py:26-31`:

| State | Simulator Drain Rate | Full-battery Runtime | Hardware Power Budget |
|---|---|---|---|
| deployed (active sensing + comms) | 0.005 %/s | 20,000 s (5.6 h) | 5.3 W |
| standby (low-power idle) | 0.001 %/s | 100,000 s (27.8 h) | 1.1 W |
| lost (beacon only) | 0.002 %/s | 50,000 s (13.9 h) | 2.1 W |
| recovered (charging) | 0.0 %/s | N/A | 0 W (charging) |

The hardware must match these runtime targets. The `estimated_remaining_runtime`
field (`rescue_ball.py:88`) must be populated by the firmware using the same
formula: `int(battery_pct / drain_rate_for_current_state)`.

### 4.3 Power Budget Breakdown (Deployed State)

| Component | Power Draw |
|---|---|
| Raspberry Pi Zero 2 W (active) | 1.2 W |
| MLX90640 thermal camera (1 Hz) | 0.45 W |
| ICM-42688-P IMU | 0.01 W |
| SPH0645LM4H-B acoustic mic | 0.1 W |
| ADXL355 vibration sensor | 0.05 W |
| NEO-M9N GPS (1 Hz fix) | 0.1 W |
| SIM7600G-H LTE (avg transmit) | 2.5 W |
| MAX17048 fuel gauge + DS18B20 | 0.01 W |
| DC-DC conversion losses (85% eff) | 0.88 W (as overhead) |
| **Total** | **5.3 W** |

At 5.3 W draw from a 29.6 Wh battery: 29.6 / 5.3 = 5.58 hours. This matches
the simulator's 5.6 hour deployed runtime.

### 4.4 Low-Power Modes

| Mode | Trigger | Behavior | Drain Rate Target |
|---|---|---|---|
| Standby | No incident assigned, or recovery signal received | Pi sleeps, ESP32 polls sensors at 0.1 Hz, LTE off, LoRa beacon every 60 s | 1.1 W (0.001 %/s) |
| Lost (beacon) | No link for 10 minutes, or manual command | Pi off, ESP32 broadcasts LoRa beacon with GPS position every 30 s | 2.1 W (0.002 %/s) |
| Critical battery | `battery_pct <= 5.0` (`rescue_ball.py:43`) | All sensors off, ESP32 sends one LoRa beacon per 5 minutes with last known position | <0.5 W |
| Shutdown | `battery_pct == 0` or internal temp >= 70 C | All power cut. RTC and ESP32 deep-sleep retain state. | ~0 W |

### 4.5 Charging and Recovery Procedure

1. Recover the ball (see section 6).
2. Rinse the enclosure with fresh water if exposed to saltwater or sediment.
3. Inspect the O-ring seal for debris or damage. Replace if cracked.
4. Open the enclosure at the equator seam.
5. Connect USB-C PD charger (5V 2A minimum). The BQ25895 manages charge
   balancing and termination.
6. Charge to full (4 hours typical). The MAX17048 reports `battery_pct: 100`.
7. Verify telemetry by connecting to the device's WiFi provisioning AP
   before redeployment.

The simulator sets `deployment_state` to `recovered` with a drain rate of
0.0 %/s (`rescue_ball.py:29`), meaning the battery does not drain while
charging. The hardware must report `deployment_state: "recovered"` and
`battery_pct` rising toward 100 during charging.

---

## 5. Deployment Mechanism

### 5.1 Airdrop

The primary deployment method is airdrop from a drone or small aircraft.

| Parameter | Specification |
|---|---|
| Drop altitude | 30-100 m AGL |
| Descent device | Small drogue chute (30 cm diameter, 1.5 m bridle) or gliding wing |
| Terminal velocity | 8-12 m/s with drogue, 5-8 m/s with wing |
| Impact energy | 38-108 J at 1.2 kg (within enclosure impact spec, section 2.4) |
| Drogue release | Auto-release on impact detection (IMU high-g event) or 3-second ground contact timer |

The drogue chute is simpler and cheaper than a wing. A wing gives softer
landings and some steerability but adds complexity and mass. The choice is a
hardware team decision. Either way, the ball must survive the landing
without breaching.

### 5.2 Water Deployment

For water deployment (boat, bridge, or shore), the ball is placed directly
on the water surface. No drogue or wing is needed.

| Parameter | Specification |
|---|---|
| Drop height | 0-3 m above water surface |
| Impact | Minimal. The ball's buoyancy arrests descent within 0.5 m of submersion. |
| Self-righting | Ballast at the south pole orients the ball within 5 seconds of water contact. |

### 5.3 Trajectory and Landing Procedure

1. Pre-deployment: provision the device with `org_id`, `incident_id`, and
   `device_id` (ULID). Set `deployment_state` to `standby`.
2. Airdrop or water-deploy the ball.
3. On impact (IMU high-g event) or water contact (conductivity sensor), the
   firmware transitions `deployment_state` to `deployed`.
4. The ball begins active sensing: thermal, IMU, acoustic, vibration, GPS
   at 1 Hz. Telemetry publishes over LTE immediately.
5. If LTE is unavailable, the ball falls back to satellite, then LoRa
   (section 3.1).
6. Position advances by drift and current (section 7). The ball reports
   `lon`, `lat`, `altitude` every second.

The simulator's `step()` method (`rescue_ball.py:101`) advances state by
`delta_ms` milliseconds. The hardware equivalent is a 1 Hz main loop: read
sensors, update state, publish telemetry, sleep 1 second.

---

## 6. Recovery

### 6.1 Retrieval Method

After the incident concludes or the ball's battery is depleted, a recovery
team retrieves the device for reuse.

| Method | Range | Accuracy | Notes |
|---|---|---|---|
| GPS position (LTE/satellite) | Global | 1.5 m CEP | Primary. The ball reports its last known position every 30 s in beacon mode. |
| LoRa beacon (RSSI triangulation) | 2-15 km | 50-200 m | Fallback when no GPS fix or no LTE. Other balls or a shore receiver triangulate from RSSI. |
| Visual (high-visibility orange) | Line of sight | N/A | Final approach. The RAL 2008 orange shell is visible from 200 m in clear conditions. |
| Acoustic pinger | 100-500 m | 10-50 m | Underwater or sediment-buried balls. 40 kHz pinger, detected by a handheld hydrophone. |

### 6.2 Recovery Team Procedure

1. Query the platform for the device's last known position and
   `deployment_state`. If `lost`, the last beacon position is the search
   center.
2. Navigate to the search area.
3. If the ball is floating, retrieve by hand or net.
4. If submerged, use the acoustic pinger and a hydrophone to locate.
5. If buried in sediment, use the LoRa beacon RSSI to narrow the search,
   then probe with a rod.
6. On recovery, the firmware transitions `deployment_state` to `recovered`.
   This happens automatically when the recovery team sends a `recover`
   command on the `cmd` topic, or manually when the ball is powered off and
   on.
7. Transport the ball to the charging station (section 4.5).

### 6.3 Device Reuse

The ball is designed for multiple deployment cycles. After charging and
seal inspection, the same device can be redeployed with a new `incident_id`.
The `device_id` and `org_id` persist across incidents. The platform tracks
deployment history through the audit log and the `source_id` field in
observations (`backend/app/models/observation.py:63`).

Expected lifecycle: 50-100 deployments before battery degradation or seal
wear requires refurbishment. The O-ring seal should be replaced every 10
deployments or after any `enclosure_status: "breached"` event.

---

## 7. Mobility

### 7.1 Propulsion: None (Drift Model)

The rescue ball has no propulsion system. It drifts with floodwater
currents. This is a deliberate design choice: propulsion adds mass, power
draw, and failure modes. A passive drifter is cheaper, simpler, and survives
longer in the field.

### 7.2 Simulator Kinematic Model

The simulator advances position using a velocity-compass model in
`_advance_position()` (`rescue_ball.py:122-133`):

```python
heading_noise = rng.gauss(0.0, 2.0)  # +/-2 deg Gaussian
h_rad = math.radians(self.heading + heading_noise)
dx_m = self.velocity * math.sin(h_rad) * dt_s
dy_m = self.velocity * math.cos(h_rad) * dt_s
```

The model takes `velocity` (m/s) and `heading` (degrees, 0 = north,
clockwise) and advances `lon`/`lat` by the displacement, plus a 2-degree
Gaussian heading perturbation. Altitude random-walks by +/-0.1 m per step
(`rescue_ball.py:133`).

### 7.3 Hardware Parity

The real ball has no `velocity` or `heading` control. Instead, the firmware
derives these from GPS displacement:

| Simulator Field | Hardware Source | Derivation |
|---|---|---|
| `velocity` (`rescue_ball.py:85`) | GPS position delta | `distance(prev_fix, curr_fix) / dt_s` |
| `heading` (`rescue_ball.py:86`) | GPS bearing | `bearing(prev_fix, curr_fix)` in degrees clockwise from north |
| `lon`, `lat` (`rescue_ball.py:81-82`) | GPS NEO-M9N | Direct fix, 1 Hz |
| `altitude` (`rescue_ball.py:83`) | GPS altitude | Direct fix, +/-5 m typical accuracy |

The firmware computes `velocity` and `heading` from consecutive GPS fixes
and reports them in the telemetry payload. The platform receives these as
part of the observation and can compare them against the simulator's
kinematic model for validation.

When GPS is unavailable (underwater, under bridge, indoor flooding), the
firmware falls back to IMU dead reckoning: integrate `accel_x/y/z` over time
to estimate displacement. Dead reckoning drifts, so the `geometry_uncertainty`
field (`backend/app/models/observation.py:52`) must increase proportionally
to time since last GPS fix. A reasonable model: 5 m uncertainty per minute
of dead reckoning.

### 7.4 Drift vs. Propulsion Trade-off

| Factor | Passive Drift (chosen) | Propelled (rejected) |
|---|---|---|
| Cost | Low (no motors) | High (motors, drivers, propellers) |
| Power | 0 W for mobility | 2-10 W for motors |
| Runtime | 5.6 h (all power to sensing) | 2-3 h (motors drain battery) |
| Failure modes | None (no moving parts) | Motor seizure, propeller fouling, debris entanglement |
| Coverage | Follows currents (limited control) | Can hold position or navigate |
| Complexity | Low | High (control loop, motor driver, feedback) |

The drift model is appropriate for situational awareness: the ball goes
where the flood goes, which is where the data is needed. A propelled variant
could be a future hardware revision if station-keeping becomes a
requirement.

---

## 8. Integration Contract

This section defines the software contract the hardware must satisfy. The
device must emit telemetry that the platform can ingest through the
`SensorSource` protocol and persist as a 23-field `Observation` row.

### 8.1 SensorSource Protocol

The `SensorSource` protocol is defined in
`backend/app/sensing/sensor_source.py` (planned, T10 in progress). The
protocol specifies:

| Member | Type | Description |
|---|---|---|
| `device_id` | `str` | ULID identifying the physical device |
| `org_id` | `str` | Tenancy scope (matches `Observation.org_id`, `observation.py:103`) |
| `incident_id` | `str` | Incident scope (matches `Observation.incident_id`, `observation.py:104`) |
| `read_telemetry()` | `-> dict` | Returns a telemetry dict conforming to the payload schema below |
| `provenance_chain` | `dict` | Provenance metadata. Must NOT contain `{"simulated": True}`. Real hardware provenance includes firmware version, sensor models, and calibration dates. |

The `MQTTSensorSource` adapter (planned:
`backend/app/sensing/adapters/mqtt_sensor.py`) implements `SensorSource` by
subscribing to the MQTT topics defined in section 3.3 and parsing the JSON
payload into the telemetry dict.

### 8.2 Observation Model (23 Fields)

The telemetry dict must contain values that map to the 23 fields of the
`Observation` model (`backend/app/models/observation.py:16-104`):

| # | Field | Source Line | Hardware Source | Payload Key |
|---|---|---|---|---|
| 1 | `observation_id` | `observation.py:38` | Generated by backend (ULID) | N/A (backend assigns) |
| 2 | `event_type` | `observation.py:41` | Fixed by sensor type | `event_type` |
| 3 | `phenomenon` | `observation.py:42` | Fixed by sensor type | `phenomenon` |
| 4 | `value` | `observation.py:45` | Sensor reading | `value` |
| 5 | `unit` | `observation.py:46` | Sensor unit | `unit` |
| 6 | `geometry` | `observation.py:49` | GPS lon/lat | `geometry: {lon, lat}` |
| 7 | `geometry_uncertainty` | `observation.py:52` | GPS accuracy or dead-reckoning drift | `geometry_uncertainty` |
| 8 | `observed_at` | `observation.py:55` | RTC timestamp (epoch ms) | `observed_at` |
| 9 | `valid_from` | `observation.py:56` | Same as `observed_at` | `valid_from` |
| 10 | `valid_until` | `observation.py:57` | `observed_at + sample_interval_ms` | `valid_until` |
| 11 | `received_at` | `observation.py:60` | Set by backend on ingestion | N/A (backend assigns) |
| 12 | `source_id` | `observation.py:63` | `device_id` | `source_id` |
| 13 | `source_type` | `observation.py:64` | `SourceType.SENSOR` enum | `source_type: "sensor"` |
| 14 | `collection_method` | `observation.py:67` | `"mqtt"` or `"lora"` or `"satellite"` | `collection_method` |
| 15 | `source_reliability` | `observation.py:68` | 0.0-1.0, calibrated per sensor | `source_reliability` |
| 16 | `freshness` | `observation.py:71` | 1.0 at emission, decays in backend | `freshness: 1.0` |
| 17 | `corroboration_state` | `observation.py:72` | `"unconfirmed"` from single device | `corroboration_state: "unconfirmed"` |
| 18 | `model_uncertainty` | `observation.py:77` | Sensor spec uncertainty, or null | `model_uncertainty` |
| 19 | `quality_flags` | `observation.py:80` | Health flags dict | `quality_flags` |
| 20 | `access_policy` | `observation.py:83` | `"internal"` default | `access_policy: "internal"` |
| 21 | `provenance_chain` | `observation.py:88` | Device metadata (see 8.3) | `provenance_chain` |
| 22 | `raw_data_hash` | `observation.py:89` | SHA-256 of raw sensor bytes | `raw_data_hash` |
| 23 | `model_version` | `observation.py:90` | Firmware version, or null | `model_version` |

### 8.3 Provenance Chain

The `provenance_chain` field (`observation.py:88`) must contain device
metadata that distinguishes real hardware from the simulator. The simulator
sets `{"simulated": True}` in its provenance chain. Real hardware must NOT
include that key.

Required keys in the hardware provenance chain:

```json
{
  "device_id": "01HXY...",
  "firmware_version": "1.0.0",
  "hardware_revision": "A1",
  "sensor_models": {
    "thermal": "MLX90640",
    "imu": "ICM-42688-P",
    "acoustic": "SPH0645LM4H-B",
    "vibration": "ADXL355",
    "gps": "NEO-M9N"
  },
  "calibration_date": "2026-07-15T00:00:00Z",
  "deployment_method": "airdrop"
}
```

### 8.4 Telemetry JSON Payload

The device publishes one JSON object per sensor reading on the telemetry
topic. Each message maps to one `Observation` row. The payload format:

```json
{
  "device_id": "01HXY7GK3P9QZ8R4M2N6V5T0W1",
  "org_id": "org_demo",
  "incident_id": "01HXZ8FK4M0QZ9R5N3O7V6T1W2",
  "source_id": "01HXY7GK3P9QZ8R4M2N6V5T0W1",
  "source_type": "sensor",
  "collection_method": "mqtt",
  "event_type": "environmental",
  "phenomenon": "temperature",
  "value": 38.2,
  "unit": "celsius",
  "geometry": {
    "type": "Point",
    "coordinates": [85.3240, 27.7172]
  },
  "geometry_uncertainty": 1.5,
  "observed_at": 1753696000000,
  "valid_from": 1753696000000,
  "valid_until": 1753696001000,
  "source_reliability": 0.92,
  "freshness": 1.0,
  "corroboration_state": "unconfirmed",
  "model_uncertainty": 0.5,
  "quality_flags": {
    "low_battery": false,
    "critical_battery": false,
    "high_temp": false,
    "signal_loss": false,
    "enclosure_breached": false,
    "camera_offline": false,
    "thermal_sensor_offline": false
  },
  "access_policy": "internal",
  "provenance_chain": {
    "device_id": "01HXY7GK3P9QZ8R4M2N6V5T0W1",
    "firmware_version": "1.0.0",
    "hardware_revision": "A1",
    "sensor_models": {
      "thermal": "MLX90640",
      "imu": "ICM-42688-P",
      "acoustic": "SPH0645LM4H-B",
      "vibration": "ADXL355",
      "gps": "NEO-M9N"
    },
    "calibration_date": "2026-07-15T00:00:00Z",
    "deployment_method": "airdrop"
  },
  "raw_data_hash": "sha256:a1b2c3d4e5f6...",
  "model_version": "1.0.0",
  "device_state": {
    "deployment_state": "deployed",
    "battery_pct": 87.5,
    "estimated_remaining_runtime": 17500,
    "link_type": "lte",
    "signal_quality": 78.3,
    "packet_loss": 12.1,
    "device_temperature": 36.8,
    "enclosure_status": "ok",
    "velocity": 0.42,
    "heading": 145.0,
    "altitude": 0.3,
    "imu_reading": {
      "accel_x": 0.02,
      "accel_y": -0.01,
      "accel_z": 9.79,
      "gyro_x": 0.003,
      "gyro_y": -0.002,
      "gyro_z": 0.001
    },
    "acoustic_reading": {
      "db_level": 61.3,
      "frequency_peak": 985.0
    },
    "camera_status": "active",
    "thermal_sensor_status": "active"
  }
}
```

The `device_state` block carries the full `RescueBallDevice` state
(`rescue_ball.py:62-99`) so the platform can update its digital twin in real
time. The `quality_flags` dict matches the seven health flags the simulator
computes (`rescue_ball.py:193-203`).

### 8.5 Sensor Reading to Observation Mapping

Each sensor produces one observation per sample. The `event_type` and
`phenomenon` fields distinguish them:

| Sensor | `event_type` | `phenomenon` | `value` | `unit` |
|---|---|---|---|---|
| Thermal (internal) | `environmental` | `temperature` | `device_temperature` | `celsius` |
| Thermal (IR array) | `thermal` | `surface_temperature` | pixel array max | `celsius` |
| IMU accel | `motion` | `acceleration` | `sqrt(ax^2+ay^2+az^2)` | `m/s^2` |
| IMU gyro | `motion` | `angular_velocity` | `sqrt(gx^2+gy^2+gz^2)` | `rad/s` |
| Acoustic | `acoustic` | `sound_pressure` | `db_level` | `dB` |
| Acoustic (freq) | `acoustic` | `frequency_peak` | `frequency_peak` | `Hz` |
| Vibration | `motion` | `vibration_rms` | `vibration_rms` | `m/s^2` |
| Seismic | `motion` | `seismic_velocity` | `seismic_velocity` | `m/s` |
| GPS | `position` | `location` | N/A (geometry only) | N/A |
| Battery | `system` | `battery_level` | `battery_pct` | `percent` |
| Signal | `system` | `signal_quality` | `signal_quality` | `percent` |

The device publishes one message per sensor per sample interval. At 1 Hz
across 11 sensor channels, that is 11 messages per second. To reduce MQTT
overhead on constrained links, the firmware may batch all sensors into a
single `event_type: "telemetry_bundle"` message with a `values` array. The
`MQTTSensorSource` adapter splits the bundle into individual observations on
ingestion.

### 8.6 Idempotency

Each telemetry message must include an idempotency key in the MQTT message
properties (`User-Property: idempotency-key={observed_at}-{device_id}-{seq}`).
The platform deduplicates on this key. If the device retransmits (QoS 1
at-least-once), the backend drops the duplicate. This follows the platform
convention of idempotency keys on all external and queue paths.

---

## References

| Reference | Path | Description |
|---|---|---|
| Digital twin | `backend/app/simulator/rescue_ball.py:62` | `RescueBallDevice` dataclass (notional device model) |
| Runtime field | `backend/app/simulator/rescue_ball.py:88` | `estimated_remaining_runtime: int` (seconds) |
| Battery drain rates | `backend/app/simulator/rescue_ball.py:26-31` | `_BATTERY_DRAIN_PER_S` dict by deployment state |
| Kinematic model | `backend/app/simulator/rescue_ball.py:122-133` | `_advance_position()` velocity-compass model |
| Health flags | `backend/app/simulator/rescue_ball.py:187-203` | `_recompute_health_flags()` thresholds |
| Observation model | `backend/app/models/observation.py:16-104` | 23-field `Observation` SQLAlchemy model |
| SensorSource protocol | `backend/app/sensing/sensor_source.py` (planned, T10) | `read_telemetry() -> dict`, `device_id`, `org_id`, `incident_id`, `provenance_chain` |
| MQTT adapter | `backend/app/sensing/adapters/mqtt_sensor.py` (planned) | `MQTTSensorSource` subscribes to device topics |
| Disclaimer #1 | `docs/KNOWN_LIMITATIONS.md:231` | Rescue ball is simulated, not physical hardware |
| Disclaimer #2 | `docs/KNOWN_LIMITATIONS.md:241` | Physical deployment and landing not validated |
| Offline prep hardware | `docs/offline-prep.md:36-52` | Server-side minimum hardware requirements (not device) |

---

## Change Log

| Date | Task | Change |
|---|---|---|
| 2026-07-28 | Wave 4, Todo 12 | Initial specification document created. Physical build deferred. |
| 2026-07-29 | T40 | Added Software Readiness Status section. All software gates (Waves 1 to 6) green. Physical hardware spec unchanged and still deferred. |

## Software Integration Harness (Task 25)

The repository includes a read-only contract harness for signed telemetry:
`scripts/run_sensor_harness.py`. It verifies provisioning and organization
binding, Ed25519 signatures over canonical telemetry bytes, strict sequence
ordering, loss/duplicate/replay quarantine, calibration provenance, key
rotation/revocation, declared clock source and skew, replay windows, and
sequence-wrap rejection using NDJSON fixtures. The happy fixture's protocol
gate is machine evidence only; it does not establish a physical device.

Run the machine gate with:

```text
backend/.venv/bin/python scripts/run_sensor_harness.py --fixture tests/fixtures/sensor-valid.ndjson --verify-signature --verify-sequence --report evidence/sota/task-25-machine.json
```

Secure boot, physical calibration, environmental limits, and production key
custody are separate prerequisites. Missing evidence returns
`DEFERRED_EXTERNAL` and never promotes sensing, human-detection, rescue-ball,
field, agency, or operational readiness claims.
