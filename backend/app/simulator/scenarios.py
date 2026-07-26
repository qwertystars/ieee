"""Predefined rescue-ball scenarios and fault injection.

DIGITAL SIMULATION — physical rescue ball, mobility, communications, thermal
accuracy, and landing mechanism have NOT been validated. Scenarios are
notional trajectories through the Rivertown demo region (lon ≈ 72.85,
lat ≈ 19.06). Fault injection functions are deterministic: they modify the
device in place and return ``None``.

Coordinates use the platform convention: ``(lon, lat, altitude_m)`` tuples.
Altitude is relative to mean sea level; negative values indicate below-sea
flooded zones.
"""

from __future__ import annotations

from app.simulator.rescue_ball import RescueBallDevice

# Rivertown flood path: a notional rescue-ball trajectory through the flooded
# Rivulet basin. Waypoints are (lon, lat, altitude_m) tuples tracing the
# device from deployment at the riverside, through the flooded wards, into the
# basin center, and out to the recovery zone.
RIVERTOWN_FLOOD_PATH: list[tuple[float, float, float]] = [
    (72.8500, 19.0720, 5.0),  # deployment point (riverside)
    (72.8520, 19.0700, 4.0),  # entering flood zone
    (72.8550, 19.0680, 2.0),  # ward 1 — shallow flood
    (72.8580, 19.0650, 0.5),  # ward 2 — moderate flood
    (72.8620, 19.0630, -1.0),  # ward 3 — deep flood
    (72.8650, 19.0620, -1.5),  # basin center
    (72.8680, 19.0630, -1.0),  # exiting basin
    (72.8700, 19.0650, 0.0),  # recovery zone
]


def inject_battery_drain(device: RescueBallDevice, rate: float) -> None:
    """Increase battery drain by subtracting ``rate`` % from ``battery_pct``.

    ``rate`` is the additional drain in percentage points to apply immediately.
    The result is clamped to [0, 100]. Deterministic.
    """
    device.battery_pct = max(0.0, min(100.0, device.battery_pct - rate))


def inject_sensor_degradation(device: RescueBallDevice, sensor: str) -> None:
    """Degrade a specific sensor to ``'degraded'`` status.

    ``sensor`` must be one of ``'camera'`` or ``'thermal'``. Deterministic.
    """
    if sensor == "camera":
        device.camera_status = "degraded"
    elif sensor == "thermal":
        device.thermal_sensor_status = "degraded"
    else:
        raise ValueError(f"unknown sensor: {sensor!r}")


def inject_connectivity_loss(device: RescueBallDevice, duration: int) -> None:
    """Simulate connectivity loss for ``duration`` seconds.

    Sets ``signal_quality`` to 0, ``packet_loss`` to 100, and ``link_type`` to
    ``'none'``. The ``duration`` is recorded in ``health_flags`` for downstream
    consumers. Deterministic.
    """
    device.signal_quality = 0.0
    device.packet_loss = 100.0
    device.link_type = "none"
    device.health_flags["connectivity_loss_duration_s"] = duration


def inject_blocked_route(
    device: RescueBallDevice, alternative_heading: float
) -> None:
    """Change heading to ``alternative_heading`` (degrees) to bypass a block.

    Deterministic: sets ``device.heading`` to the given value.
    """
    device.heading = float(alternative_heading)


def inject_thermal_hotspot(
    device: RescueBallDevice, temperature: float
) -> None:
    """Set thermal sensor to detect a hotspot at ``temperature`` °C.

    Marks the thermal sensor as active and records the hotspot temperature in
    ``health_flags['thermal_hotspot_c']``. Deterministic.
    """
    device.thermal_sensor_status = "active"
    device.health_flags["thermal_hotspot_c"] = float(temperature)


def inject_human_heat_signature(
    device: RescueBallDevice, location: str
) -> None:
    """Set thermal sensor to detect a human heat signature at ``location``.

    Marks the thermal sensor as active and records the location in
    ``health_flags['human_heat_at']``. Deterministic.
    """
    device.thermal_sensor_status = "active"
    device.health_flags["human_heat_at"] = location


def inject_water_depth(device: RescueBallDevice, depth: float) -> None:
    """Set acoustic reading for water depth (meters).

    Records the depth in ``acoustic_reading['water_depth_m']``. Deterministic.
    """
    device.acoustic_reading["water_depth_m"] = float(depth)


def inject_motion(device: RescueBallDevice, direction: float) -> None:
    """Set IMU reading for motion detection in ``direction`` (degrees).

    Records the heading in ``imu_reading['motion_heading_deg']``. Deterministic.
    """
    device.imu_reading["motion_heading_deg"] = float(direction)


def inject_vibration(device: RescueBallDevice, intensity: float) -> None:
    """Set IMU reading for vibration intensity (m/s²).

    Records the intensity in ``imu_reading['vibration_intensity']``.
    Deterministic.
    """
    device.imu_reading["vibration_intensity"] = float(intensity)


def inject_environmental_temp(device: RescueBallDevice, temp: float) -> None:
    """Set device temperature to ``temp`` °C.

    Deterministic: sets ``device.device_temperature`` to the given value.
    """
    device.device_temperature = float(temp)


__all__ = [
    "RIVERTOWN_FLOOD_PATH",
    "inject_battery_drain",
    "inject_sensor_degradation",
    "inject_connectivity_loss",
    "inject_blocked_route",
    "inject_thermal_hotspot",
    "inject_human_heat_signature",
    "inject_water_depth",
    "inject_motion",
    "inject_vibration",
    "inject_environmental_temp",
]
