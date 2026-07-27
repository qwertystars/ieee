"""Rescue-ball device simulator — deterministic digital twin.

DIGITAL SIMULATION — physical rescue ball, mobility, communications, thermal
accuracy, and landing mechanism have NOT been validated. This module models a
notional spherical rescue device deployed into flooded urban areas for
situational awareness. All randomness is sourced from a caller-provided
``random.Random`` so that the same seed reproduces the same trajectory.

Conventions follow the platform standard:
- ULIDs for identifiers (see ``app.lib.ulid``).
- UTC epoch milliseconds for timestamps (see ``app.lib.time``).
- ``org_id`` tenancy on every device.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

# Meters per degree of latitude (constant; Earth is approximately spherical).
_M_PER_DEG_LAT = 111_320.0

# Battery drain rate in %/second by deployment state.
_BATTERY_DRAIN_PER_S: dict[str, float] = {
    "deployed": 0.005,  # active sensing + comms
    "standby": 0.001,  # low-power idle
    "recovered": 0.0,  # charging
    "lost": 0.002,  # beacon only
}

# Thermal equilibrium temperature (°C) by deployment state.
_EQUILIBRIUM_TEMP_C: dict[str, float] = {
    "deployed": 38.0,
    "standby": 25.0,
    "recovered": 22.0,
    "lost": 30.0,
}

# Health-flag thresholds.
_LOW_BATTERY_PCT = 20.0
_CRIT_BATTERY_PCT = 5.0
_HIGH_TEMP_C = 50.0
_SIGNAL_LOSS_PCT = 10.0

# Thermal relaxation time constant (seconds) — ~5 minutes.
_THERMAL_TAU_S = 300.0


def _meters_to_deg(
    lon: float, lat: float, dx_m: float, dy_m: float
) -> tuple[float, float]:
    """Convert a delta in meters to (d_lon, d_lat) at the given position."""
    d_lat = dy_m / _M_PER_DEG_LAT
    cos_lat = math.cos(math.radians(lat))
    d_lon = dx_m / (_M_PER_DEG_LAT * cos_lat) if cos_lat > 0.0 else 0.0
    return d_lon, d_lat


@dataclass(slots=True)
class RescueBallDevice:
    """Digital twin of a single rescue ball.

    DIGITAL SIMULATION — physical rescue ball, mobility, communications,
    thermal accuracy, and landing mechanism have NOT been validated.

    All state mutations happen through ``step()``, which is deterministic given
    the same ``random.Random`` seed. The device is mutable by design (it is a
    stateful simulator, not a value object).

    ``health_flags`` holds boolean recomputed flags plus optional non-boolean
    metadata set by fault-injection functions (see ``app.simulator.scenarios``).
    ``imu_reading`` and ``acoustic_reading`` hold the latest sensor samples;
    fault-injection functions may add extra keys that ``step()`` preserves.
    """

    device_id: str
    org_id: str
    incident_id: str
    lon: float
    lat: float
    altitude: float
    deployment_state: str  # deployed | standby | recovered | lost
    velocity: float  # m/s
    heading: float  # degrees, 0 = north, clockwise
    battery_pct: float  # 0-100
    estimated_remaining_runtime: int  # seconds
    link_type: str  # wifi | lte | satellite | none
    signal_quality: float  # 0-100
    packet_loss: float  # 0-100
    device_temperature: float  # Celsius
    enclosure_status: str  # ok | damaged | breached
    camera_status: str  # active | offline | degraded
    thermal_sensor_status: str  # active | offline | degraded
    imu_reading: dict[str, float]
    acoustic_reading: dict[str, float]
    last_seen_ts: int  # epoch ms
    health_flags: dict[str, Any]

    def step(self, delta_ms: int, rng: random.Random) -> None:
        """Advance device state by ``delta_ms`` milliseconds.

        All randomness is drawn from ``rng`` so the same seed reproduces the
        same trajectory. Position advances by velocity*heading with a small
        Gaussian perturbation; battery drains by deployment-state rate;
        signal quality random-walks within [0, 100]; temperature relaxes
        toward the deployment-state equilibrium; health flags recompute from
        thresholds. Non-boolean keys in ``health_flags`` and extra keys in
        ``imu_reading`` / ``acoustic_reading`` are preserved.
        """
        dt_s = delta_ms / 1000.0
        self._advance_position(dt_s, rng)
        self._drain_battery(dt_s)
        self._fluctuate_signal(rng)
        self._relax_temperature(dt_s)
        self._update_imu(rng)
        self._update_acoustic(rng)
        self.last_seen_ts += delta_ms
        self._recompute_health_flags()

    def _advance_position(self, dt_s: float, rng: random.Random) -> None:
        """Move by velocity*heading plus a small Gaussian perturbation."""
        if self.deployment_state != "deployed" or self.velocity <= 0.0:
            return
        heading_noise = rng.gauss(0.0, 2.0)  # ±2° Gaussian
        h_rad = math.radians(self.heading + heading_noise)
        dx_m = self.velocity * math.sin(h_rad) * dt_s
        dy_m = self.velocity * math.cos(h_rad) * dt_s
        d_lon, d_lat = _meters_to_deg(self.lon, self.lat, dx_m, dy_m)
        self.lon += d_lon
        self.lat += d_lat
        self.altitude += rng.gauss(0.0, 0.1)  # ±0.1 m random walk

    def _drain_battery(self, dt_s: float) -> None:
        """Decrease battery_pct based on deployment-state drain rate."""
        rate = _BATTERY_DRAIN_PER_S.get(self.deployment_state, 0.0)
        self.battery_pct = max(0.0, self.battery_pct - rate * dt_s)
        if rate > 0.0:
            self.estimated_remaining_runtime = int(self.battery_pct / rate)
        else:
            self.estimated_remaining_runtime = 0

    def _fluctuate_signal(self, rng: random.Random) -> None:
        """Random-walk signal_quality and packet_loss within [0, 100]."""
        if self.link_type == "none":
            self.signal_quality = 0.0
            self.packet_loss = 100.0
            return
        self.signal_quality = max(
            0.0, min(100.0, self.signal_quality + rng.gauss(0.0, 2.0))
        )
        target_loss = max(0.0, 100.0 - self.signal_quality)
        self.packet_loss = max(
            0.0,
            min(100.0, self.packet_loss + (target_loss - self.packet_loss) * 0.1),
        )

    def _relax_temperature(self, dt_s: float) -> None:
        """Relax device_temperature toward deployment-state equilibrium."""
        target = _EQUILIBRIUM_TEMP_C.get(self.deployment_state, 25.0)
        alpha = 1.0 - math.exp(-dt_s / _THERMAL_TAU_S)
        self.device_temperature += (target - self.device_temperature) * alpha

    def _update_imu(self, rng: random.Random) -> None:
        """Update IMU reading with small Gaussian noise around rest."""
        self.imu_reading.update(
            {
                "accel_x": rng.gauss(0.0, 0.05),
                "accel_y": rng.gauss(0.0, 0.05),
                "accel_z": 9.81 + rng.gauss(0.0, 0.02),
                "gyro_x": rng.gauss(0.0, 0.01),
                "gyro_y": rng.gauss(0.0, 0.01),
                "gyro_z": rng.gauss(0.0, 0.01),
            }
        )

    def _update_acoustic(self, rng: random.Random) -> None:
        """Update acoustic reading with small Gaussian noise."""
        self.acoustic_reading.update(
            {
                "db_level": 60.0 + rng.gauss(0.0, 2.0),
                "frequency_peak": 1000.0 + rng.gauss(0.0, 50.0),
            }
        )

    def _recompute_health_flags(self) -> None:
        """Recompute boolean health flags from current thresholds.

        Uses ``update()`` so non-boolean keys set by fault-injection functions
        (e.g. ``thermal_hotspot_c``) are preserved across ``step()`` calls.
        """
        self.health_flags.update(
            {
                "low_battery": self.battery_pct <= _LOW_BATTERY_PCT,
                "critical_battery": self.battery_pct <= _CRIT_BATTERY_PCT,
                "high_temp": self.device_temperature >= _HIGH_TEMP_C,
                "signal_loss": self.signal_quality <= _SIGNAL_LOSS_PCT,
                "enclosure_breached": self.enclosure_status == "breached",
                "camera_offline": self.camera_status == "offline",
                "thermal_sensor_offline": self.thermal_sensor_status == "offline",
            }
        )


__all__ = ["RescueBallDevice"]
