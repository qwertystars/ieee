"""MQTT sensor source — subscribes to a broker topic and yields telemetry.

Uses ``paho-mqtt`` with a GUARDED import so the module loads cleanly
when the library is not installed (e.g. in test environments without
MQTT hardware). Instantiation fails with a clear error if paho-mqtt
is missing or the broker is unreachable.

The ``read_telemetry()`` method blocks until the next MQTT message
arrives on the subscribed topic, then returns a normalized observation
payload dict matching ``ConsumerManager._build_observation``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import queue
from typing import Any

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType
from app.sensing.sensor_source import build_sensor_provenance

# Guarded import — paho-mqtt is an optional dependency.
try:
    import paho.mqtt.client as mqtt  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — exercised only without paho-mqtt
    mqtt = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_DEFAULT_QUEUE_TIMEOUT_S = 30.0


class MQTTSensorSource:
    """SensorSource backed by an MQTT subscription.

    Implements the ``SensorSource`` protocol (duck-typed — no explicit
    inheritance needed for ``runtime_checkable`` Protocol).

    The client connects on construction and subscribes to ``topic``.
    Each call to ``read_telemetry()`` blocks until a message arrives
    (or ``queue_timeout`` elapses, raising ``TimeoutError``).
    """

    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        topic: str,
        device_id: str,
        org_id: str,
        incident_id: str,
        *,
        username: str | None = None,
        password: str | None = None,
        queue_timeout_s: float = _DEFAULT_QUEUE_TIMEOUT_S,
    ) -> None:
        if mqtt is None:
            raise ImportError(
                "paho-mqtt is not installed. Install it with "
                "`pip install paho-mqtt` to use MQTTSensorSource."
            )
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._topic = topic
        self._device_id = device_id
        self._org_id = org_id
        self._incident_id = incident_id
        self._queue_timeout_s = queue_timeout_s
        self._msg_queue: queue.Queue[dict[str, Any]] = queue.Queue()

        self._client = mqtt.Client(client_id=f"resqnet-{device_id}")
        if username:
            self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(broker_host, broker_port)
        self._client.loop_start()

    def _on_connect(self, client: object, userdata: object, flags: dict, rc: int) -> None:
        if rc == 0:
            logger.info("MQTT connected to %s:%d, subscribing to %s",
                        self._broker_host, self._broker_port, self._topic)
            self._client.subscribe(self._topic)
        else:
            logger.error("MQTT connect failed, rc=%d", rc)

    def _on_message(self, client: object, userdata: object, msg: object) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))  # type: ignore[attr-defined]
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("MQTT malformed message on %s: %s", self._topic, exc)
            return
        self._msg_queue.put(payload)

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
        """Block until the next MQTT message, return a normalized payload.

        Raises ``TimeoutError`` if no message arrives within
        ``queue_timeout_s`` seconds.
        """
        raw = self._msg_queue.get(timeout=self._queue_timeout_s)
        return self._normalize(raw)

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Map a raw MQTT JSON payload to the observation payload format."""
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
            "source_id": f"mqtt:{self._device_id}",
            "source_type": SourceType.sensor.value,
            "collection_method": "mqtt_subscription",
            "source_reliability": 0.8,
            "freshness": 1.0,
            "corroboration_state": CorroborationState.uncorroborated.value,
            "model_uncertainty": None,
            "quality_flags": {"mqtt_topic": self._topic},
            "access_policy": AccessPolicy.internal.value,
            "provenance_chain": build_sensor_provenance(
                "mqtt",
                self._device_id,
                broker=f"{self._broker_host}:{self._broker_port}",
                topic=self._topic,
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
        """Disconnect from the broker and stop the network loop."""
        self._client.loop_stop()
        self._client.disconnect()


__all__ = ["MQTTSensorSource"]
