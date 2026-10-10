"""SensorSource protocol — contract for real-device telemetry ingestion.

Defines the seam between physical sensors (MQTT, serial, SensorThings API)
and the platform's observation pipeline. Any class implementing this
protocol can be fed to ``SensorIngestionService``, which publishes
telemetry through ``ProducerManager.send("observations.raw", payload)``.

REAL SENSOR DATA IS NOT SIMULATED. The ``provenance_chain`` produced by
implementations MUST NOT include ``{"simulated": True}`` — that key is
reserved for the ``SimulationEngine`` digital twin (see
``app.simulator.engine._publish_observation``).

The protocol is importable without any hardware-specific dependencies
(paho-mqtt, pyserial are guarded in their adapter modules).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SensorSource(Protocol):
    """Contract for a real-device telemetry source.

    Implementations read raw sensor data (MQTT messages, serial lines,
    HTTP pulls) and return a normalized observation payload dict matching
    the fields expected by ``ConsumerManager._build_observation`` in
    ``app/streaming/consumer.py``.

    Required payload fields (see the 23-field Observation model):
      observation_id, event_type, phenomenon, geometry, observed_at,
      source_id, source_type, org_id, incident_id.
    Optional payload fields (sensible defaults exist in the consumer):
      value, unit, geometry_uncertainty, valid_from, valid_until,
      received_at, collection_method, source_reliability, freshness,
      corroboration_state, model_uncertainty, quality_flags,
      access_policy, provenance_chain, raw_data_hash, model_version,
      supersedes, duplicate_group.

    The ``provenance_chain`` MUST NOT contain ``{"simulated": True}``.
    """

    @property
    def device_id(self) -> str:
        """Stable identifier for the physical device producing telemetry."""
        ...

    @property
    def org_id(self) -> str:
        """Tenant org_id this device's observations belong to."""
        ...

    @property
    def incident_id(self) -> str:
        """Incident this device's observations are scoped to."""
        ...

    def read_telemetry(self) -> dict[str, Any]:
        """Read one telemetry sample and return a normalized payload dict.

        Implementations may block until data is available (e.g. waiting
        for the next MQTT message or serial line). The returned dict
        must include the fields listed in the class docstring and its
        ``provenance_chain`` must NOT mark the data as simulated.
        """
        ...


def build_sensor_provenance(
    source_kind: str,
    device_id: str,
    **extra: Any,
) -> dict[str, Any]:
    """Build a provenance_chain for real sensor data.

    The returned dict marks the data as coming from a real device
    (``simulated`` is explicitly absent / False). Extra metadata
    (broker, port, topic, datastream_id, etc.) can be passed as kwargs.

    Args:
        source_kind: ``"mqtt"``, ``"serial"``, ``"sensorthings"``, etc.
        device_id: The physical device identifier.
        **extra: Additional provenance metadata.

    Returns:
        A dict suitable for the ``provenance_chain`` field. Never
        includes ``{"simulated": True}``.
    """
    chain: dict[str, Any] = {
        "source": source_kind,
        "device_id": device_id,
        "simulated": False,
    }
    chain.update(extra)
    return chain


__all__ = ["SensorSource", "build_sensor_provenance"]
