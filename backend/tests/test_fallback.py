"""Tests for low-bandwidth fallback channels — SMS, cell broadcast, LoRa, DTN, text-first.

Pure unit tests — no database or network required. All channel sends are stubbed.
"""

import json

import pytest

from app.comms.fallback import LowBandwidthFallback


@pytest.fixture
def fb():
    return LowBandwidthFallback()


def test_compress_payload_under_2kb(fb):
    """compress_payload strips maps/images and produces <2KB JSON."""
    data = {
        "incident_id": "inc_001",
        "severity": "severe",
        "area": "Rivertown downtown",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        },
        "map_url": "https://maps.example.org/inc/001",
        "image_url": "https://cdn.example.org/inc/001.png",
        "shelters": [
            {"name": "Main Shelter", "capacity": 200, "occupancy": 80},
            {"name": "North Shelter", "capacity": 150, "occupancy": 60},
        ],
        "description": "x" * 5000,  # long text that must be truncated
    }
    compressed = fb.compress_payload(data)
    encoded = json.dumps(compressed, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    assert len(encoded.encode("utf-8")) <= 2048
    # Heavy keys stripped.
    assert "geometry" not in compressed
    assert "map_url" not in compressed
    assert "image_url" not in compressed
    # Light fields preserved.
    assert compressed["incident_id"] == "inc_001"
    assert compressed["severity"] == "severe"


def test_compress_payload_rejects_unsupported_mode(fb):
    """compress_payload raises on unsupported mode."""
    with pytest.raises(ValueError):
        fb.compress_payload({"a": 1}, mode="binary")


def test_sms_adapter_sends_formatted_alert(fb):
    """send_sms returns a record with formatted alert text."""
    result = fb.send_sms("+15551234567", "Flood warning: River Street overflowing")
    assert result["status"] == "stubbed_ok"
    assert result["channel"] == "sms"
    assert result["phone"] == "+15551234567"
    assert "[ALERT]" in result["text"]
    assert "Flood warning" in result["text"]
    assert result["message_id"]  # ULID assigned


def test_sms_adapter_rejects_empty(fb):
    """send_sms raises on missing phone or message."""
    with pytest.raises(ValueError):
        fb.send_sms("", "msg")
    with pytest.raises(ValueError):
        fb.send_sms("+15551234567", "")


def test_sms_truncates_long_message(fb):
    """send_sms truncates message body longer than 154 chars."""
    long_msg = "A" * 300
    result = fb.send_sms("+15551234567", long_msg)
    body = result["text"].split(": ", 1)[1]
    assert len(body) <= 154
    assert body.endswith("...")
    assert "A" * 300 not in result["text"]


def test_cell_broadcast_returns_government_gated_note(fb):
    """send_cell_broadcast returns a note — government-gated, not directly sent."""
    result = fb.send_cell_broadcast("Rivertown downtown", "Evacuate immediately")
    assert result["status"] == "government_gated"
    assert result["channel"] == "cell_broadcast"
    assert "government" in result["note"].lower()
    assert result["area"] == "Rivertown downtown"
    assert result["text"] == "Evacuate immediately"


def test_cell_broadcast_rejects_empty(fb):
    """send_cell_broadcast raises on missing area or message."""
    with pytest.raises(ValueError):
        fb.send_cell_broadcast("", "msg")
    with pytest.raises(ValueError):
        fb.send_cell_broadcast("area", "")


def test_lora_accepts_sensor_reading(fb):
    """send_lora accepts a sensor reading and returns success."""
    result = fb.send_lora("node-42", {
        "temperature": 27.5,
        "humidity": 78.0,
        "water_level": 1.2,
        "battery": 3.7,
    })
    assert result["status"] == "stubbed_ok"
    assert result["channel"] == "lora"
    assert result["device_id"] == "node-42"
    assert result["sensor_readings"]["temperature"] == 27.5
    assert result["sensor_readings"]["water_level"] == 1.2


def test_lora_rejects_non_sensor_payload(fb):
    """send_lora raises if payload has no recognized sensor fields."""
    with pytest.raises(ValueError):
        fb.send_lora("node-42", {"note": "no sensor data"})
    with pytest.raises(ValueError):
        fb.send_lora("", {"temperature": 25.0})


def test_dtn_queues_payload(fb):
    """send_dtn queues the payload for later delivery."""
    payload = {"incident_id": "inc_001", "status": "shelter_open", "capacity": 100}
    result = fb.send_dtn("edge-node-7", payload)
    assert result["status"] == "queued"
    assert result["channel"] == "dtn"
    assert result["node_id"] == "edge-node-7"
    assert result["payload"] == payload
    # Pending queue reflects the new entry.
    pending = fb.dtn_pending()
    assert len(pending) == 1
    assert pending[0]["message_id"] == result["message_id"]
    # Flush clears the queue.
    assert fb.dtn_flush() == 1
    assert fb.dtn_pending() == []


def test_dtn_rejects_empty(fb):
    """send_dtn raises on missing node_id or empty payload."""
    with pytest.raises(ValueError):
        fb.send_dtn("", {"a": 1})
    with pytest.raises(ValueError):
        fb.send_dtn("node-1", {})


def test_fallback_mode_flag(fb):
    """set_fallback_mode toggles is_low_bandwidth_mode."""
    assert fb.is_low_bandwidth_mode() is False
    fb.set_fallback_mode(True)
    assert fb.is_low_bandwidth_mode() is True
    fb.set_fallback_mode(False)
    assert fb.is_low_bandwidth_mode() is False
