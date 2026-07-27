"""Low-bandwidth fallback channels — SMS, cell broadcast, LoRa, DTN, text-first payloads.

When connectivity degrades, critical alerts must still reach responders. This module
provides offline-capable fallback channels and a text-first payload compressor that
strips GeoJSON/images to fit <2KB payloads suitable for SMS/LoRa/DTN transport.

Must NOT depend on internet for critical alerts — SMS and cell broadcast are
carrier/government-gated and work without IP connectivity to the platform.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from app.lib.time import now_ms
from app.lib.ulid import generate_ulid

logger = logging.getLogger(__name__)

# Hard ceiling for text-first payloads (SMS/LoRa/DTN budget).
_MAX_PAYLOAD_BYTES = 2048

# Fields stripped during text-first compression (maps, images, heavy nested objects).
_STRIP_KEYS = frozenset({
    "geometry", "geojson", "geometry_wkt", "bbox", "map", "map_url",
    "image", "image_url", "thumbnail", "photo", "photos", "imagery",
    "raster", "tile_url", "tiles",
})

# Sensor reading fields accepted by the LoRa adapter.
_LORA_SENSOR_FIELDS = frozenset({
    "temperature", "humidity", "water_level", "battery", "pressure",
})


class LowBandwidthFallback:
    """Low-bandwidth fallback channels + text-first payload compressor.

    All channel sends are stubbed in dev — no real SMS/LoRa/DTN hardware is touched.
    Critical alerts MUST be deliverable without internet: SMS and cell broadcast
    are carrier/government-gated and do not require IP connectivity to this platform.
    """

    def __init__(self) -> None:
        self._fallback_mode: bool = False
        self._dtn_queue: list[dict[str, Any]] = []
        self._dtn_lock = threading.Lock()
        self._sms_outbox: list[dict[str, Any]] = []
        self._lora_outbox: list[dict[str, Any]] = []
        self._cell_broadcast_log: list[dict[str, Any]] = []

    # --- Fallback mode flag ---

    def set_fallback_mode(self, enabled: bool) -> None:
        """Toggle low-bandwidth mode. When True, API returns minimal JSON."""
        self._fallback_mode = bool(enabled)

    def is_low_bandwidth_mode(self) -> bool:
        """Return True if low-bandwidth fallback mode is active."""
        return self._fallback_mode

    # --- Text-first payload compression ---

    def compress_payload(self, data: dict[str, Any], mode: str = "text_first") -> dict[str, Any]:
        """Compress payload to text-first form: strip maps/images, list-only, <2KB.

        - Strips GeoJSON, geometry, bbox, image, imagery, tile fields.
        - Converts nested dicts to flat "k=v; k=v" text lists where possible.
        - Truncates long string values to fit within _MAX_PAYLOAD_BYTES (2KB).
        """
        if mode != "text_first":
            raise ValueError(f"unsupported compression mode: {mode}")

        stripped = _strip_heavy_keys(data)
        flattened = _to_text_list(stripped)
        encoded = json.dumps(flattened, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) <= _MAX_PAYLOAD_BYTES:
            return flattened
        return _truncate_to_fit(flattened, _MAX_PAYLOAD_BYTES)

    # --- SMS adapter (stubbed, carrier network — no internet needed) ---

    def send_sms(self, phone: str, message: str) -> dict[str, Any]:
        """Send SMS via gateway adapter (Twilio/MSG91 in prod, stubbed in dev).

        Does NOT depend on internet to the platform — SMS goes via carrier network.
        Returns success descriptor; the formatted text is recorded in the outbox.
        """
        if not phone or not message:
            raise ValueError("phone and message are required")
        formatted = _format_sms(phone, message)
        record = {
            "message_id": generate_ulid(),
            "channel": "sms",
            "phone": phone,
            "text": formatted,
            "sent_at": now_ms(),
            "status": "stubbed_ok",
        }
        self._sms_outbox.append(record)
        logger.info("sms.send_stubbed", extra={"phone": phone, "message_id": record["message_id"]})
        return record

    # --- Cell broadcast (government-gated, integration note only) ---

    def send_cell_broadcast(self, area: str, message: str) -> dict[str, Any]:
        """Cell broadcast integration note — government-gated, not directly sendable.

        Cell broadcast requires government/carrier authorization. This method
        returns an integration note describing what would be sent; it does NOT
        send anything. Use send_sms() as the carrier-independent fallback.
        """
        if not area or not message:
            raise ValueError("area and message are required")
        note = {
            "message_id": generate_ulid(),
            "channel": "cell_broadcast",
            "area": area,
            "text": message,
            "prepared_at": now_ms(),
            "status": "government_gated",
            "note": (
                "Cell broadcast requires government/carrier authorization. "
                "This is an integration note only — no broadcast was sent. "
                "Use send_sms() as the carrier-independent fallback."
            ),
        }
        self._cell_broadcast_log.append(note)
        logger.info(
            "cell_broadcast.government_gated",
            extra={"area": area, "message_id": note["message_id"]},
        )
        return note

    # --- LoRa adapter (sensor data via LoRaWAN, offline mesh radio) ---

    def send_lora(self, device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send sensor reading via LoRaWAN adapter (stubbed in dev).

        Accepts sensor readings: temperature, humidity, water_level, battery, pressure.
        LoRa is offline-capable (mesh radio, no IP connectivity needed).
        """
        if not device_id:
            raise ValueError("device_id is required")
        if not isinstance(payload, dict) or not payload:
            raise ValueError("payload must be a non-empty dict")

        sensor_fields = {k: v for k, v in payload.items() if k in _LORA_SENSOR_FIELDS}
        if not sensor_fields:
            raise ValueError(
                f"payload must contain at least one sensor reading: {sorted(_LORA_SENSOR_FIELDS)}"
            )

        record = {
            "message_id": generate_ulid(),
            "channel": "lora",
            "device_id": device_id,
            "sensor_readings": sensor_fields,
            "sent_at": now_ms(),
            "status": "stubbed_ok",
        }
        self._lora_outbox.append(record)
        logger.info(
            "lora.send_stubbed",
            extra={"device_id": device_id, "message_id": record["message_id"]},
        )
        return record

    # --- DTN store-carry-forward (no internet at send time) ---

    def send_dtn(self, node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Queue payload for DTN store-carry-forward delivery.

        Stores the payload in-memory; a carrier node will deliver it when
        connectivity is available. Does NOT require internet at send time.
        """
        if not node_id:
            raise ValueError("node_id is required")
        if not isinstance(payload, dict) or not payload:
            raise ValueError("payload must be a non-empty dict")
        record = {
            "message_id": generate_ulid(),
            "channel": "dtn",
            "node_id": node_id,
            "payload": payload,
            "queued_at": now_ms(),
            "status": "queued",
        }
        with self._dtn_lock:
            self._dtn_queue.append(record)
        logger.info(
            "dtn.queued",
            extra={"node_id": node_id, "message_id": record["message_id"]},
        )
        return record

    def dtn_pending(self) -> list[dict[str, Any]]:
        """Return a snapshot of the pending DTN queue (for inspection/flush)."""
        with self._dtn_lock:
            return list(self._dtn_queue)

    def dtn_flush(self) -> int:
        """Mark all pending DTN messages as delivered; return count flushed."""
        with self._dtn_lock:
            count = len(self._dtn_queue)
            self._dtn_queue.clear()
        return count


# --- Helpers (module-level, pure functions) ---


def _strip_heavy_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip map/image/geometry keys from a dict."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k in _STRIP_KEYS:
            continue
        if isinstance(v, dict):
            nested = _strip_heavy_keys(v)
            if nested:
                out[k] = nested
        elif isinstance(v, list):
            out[k] = [
                _strip_heavy_keys(item) if isinstance(item, dict) else item for item in v
            ]
        else:
            out[k] = v
    return out


def _to_text_list(data: dict[str, Any]) -> dict[str, Any]:
    """Convert nested dicts to flat text-list form where reasonable.

    Nested dicts become "k=v; k=v" strings. Lists of dicts become lists of such strings.
    Scalars and lists of scalars are preserved as-is.
    """
    out: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = "; ".join(
                f"{dk}={dv}" for dk, dv in v.items()
                if not isinstance(dv, (dict, list))
            )
        elif isinstance(v, list) and v and all(isinstance(i, dict) for i in v):
            out[k] = [
                "; ".join(
                    f"{dk}={dv}" for dk, dv in i.items()
                    if not isinstance(dv, (dict, list))
                )
                for i in v
            ]
        else:
            out[k] = v
    return out


def _truncate_to_fit(data: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    """Truncate long string values to fit the payload under max_bytes (compact JSON)."""
    out = dict(data)
    while True:
        encoded = json.dumps(out, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) <= max_bytes:
            return out
        # Find the longest string value.
        longest_key, longest_val = "", ""
        for k, v in out.items():
            if isinstance(v, str) and len(v) > len(longest_val):
                longest_key, longest_val = k, v
        if len(longest_val) > 16:
            new_len = max(8, len(longest_val) // 2)
            out[longest_key] = longest_val[:new_len] + "..."
        elif out:
            out.pop(next(reversed(out)))
        else:
            return out


def _format_sms(phone: str, message: str) -> str:
    """Format an alert as a single SMS text line (no map, no images)."""
    text = message.strip()
    if len(text) > 154:
        text = text[:151] + "..."
    return f"[ALERT] to={phone}: {text}"


__all__ = ["LowBandwidthFallback"]
