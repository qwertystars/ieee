"""Serial sensor source — reads telemetry lines from a serial port.

Uses ``pyserial`` with a GUARDED import so the module loads cleanly
when the library is not installed (e.g. in test environments without
serial hardware). Instantiation fails with a clear error if pyserial
is missing or the serial port is unavailable.

The ``read_telemetry()`` method blocks until a complete line is
received from the serial device, parses it as JSON, and returns a
normalized observation payload dict matching
``ConsumerManager._build_observation``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.sensing.sensor_source import build_sensor_provenance

# Guarded import — pyserial is an optional dependency.
try:
    import serial  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — exercised only without pyserial
    serial = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_DEFAULT_READ_TIMEOUT_S = 30.0
_DEFAULT_BAUDRATE = 9600


class SerialSensorSource:
    """SensorSource backed by a serial port.

    Implements the ``SensorSource`` protocol (duck-typed). Opens the
    serial port on construction. Each call to ``read_telemetry()``
    blocks until a complete JSON line is received.
    """

    def __init__(
        self,
        port: str,
        device_id: str,
        org_id: str,
        incident_id: str,
        *,
        baudrate: int = _DEFAULT_BAUDRATE,
        read_timeout_s: float = _DEFAULT_READ_TIMEOUT_S,
    ) -> None:
        if serial is None:
            raise ImportError(
                "pyserial is not installed. Install it with "
                "`pip install pyserial` to use SerialSensorSource."
            )
        self._port = port
        self._device_id = device_id
        self._org_id = org_id
        self._incident_id = incident_id
        self._read_timeout_s = read_timeout_s

        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=read_timeout_s,
            )
        except serial.SerialException as exc:  # type: ignore[union-attr]
            raise ConnectionError(
                f"Cannot open serial port {port}: {exc}. Ensure the "
                f"device is connected and the port is not in use."
            ) from exc
        logger.info("SerialSensorSource connected to %s @ %d baud", port, baudrate)

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def org_id(self) -> str:
        return self._org_id

    @property
    def incident_id(self) -> str:
        return self._incident_id

    def read_telemetry(self) -> dict[str, Any]:
        """Block until a JSON line arrives, return a normalized payload.

        Raises ``TimeoutError`` if no line arrives within
        ``read_timeout_s`` seconds. Raises ``ValueError`` if the line
        is not valid JSON.
        """
        line = self._serial.readline()
        if not line:
            raise TimeoutError(
                f"No data from serial port {self._port} within "
                f"{self._read_timeout_s}s"
            )
        try:
            raw = json.loads(line.decode("utf-8").strip())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(
                f"Invalid JSON from serial port {self._port}: {exc}"
            ) from exc
        return self._normalize(raw)

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Map a raw serial JSON payload to the observation payload format."""
        observed_at = int(raw.get("timestamp", now_ms()))
        geometry = raw.get("geometry") or {
            "type": "Point",
            "coordinates": [
                float(raw.get("lon", 0.0)),
                float(raw.get("lat", 0.0)),
            ],
        }
        return {
            "observation_id": generate_ulid(),
            "event_type": "sensor_reading",
            "phenomenon": raw.get("phenomenon", "unknown"),
            "value": float(raw["value"]) if raw.get("value") is not None else None,
            "unit": raw.get("unit"),
            "geometry": geometry,
            "geometry_uncertainty": float(raw.get("geometry_uncertainty", 0.0)),
            "observed_at": observed_at,
            "valid_from": observed_at,
            "valid_until": None,
            "received_at": now_ms(),
            "source_id": f"serial:{self._device_id}",
            "source_type": SourceType.sensor.value,
            "collection_method": "serial_port",
            "source_reliability": 0.8,
            "freshness": 1.0,
            "corroboration_state": CorroborationState.uncorroborated.value,
            "model_uncertainty": None,
            "quality_flags": {"serial_port": self._port},
            "access_policy": AccessPolicy.internal.value,
            "provenance_chain": build_sensor_provenance(
                "serial",
                self._device_id,
                port=self._port,
            ),
            "raw_data_hash": "sha256:" + hashlib.sha256(
                json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
            "model_version": None,
            "supersedes": None,
            "duplicate_group": None,
            "org_id": self._org_id,
            "incident_id": self._incident_id,
        }

    def close(self) -> None:
        """Close the serial port."""
        if hasattr(self, "_serial") and self._serial.is_open:
            self._serial.close()


__all__ = ["SerialSensorSource"]
