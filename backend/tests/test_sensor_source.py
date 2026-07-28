"""Integration test — SensorSource protocol and real-device ingestion seam.

Verifies that mock sensor telemetry flows through the full pipeline:
  MockSensorSource → SensorIngestionService → (fake producer captures payload)
  → ConsumerManager._process() → PostgreSQL

Asserts the stored observation:
  - Has ``provenance_chain`` WITHOUT ``simulated: true``
  - Matches the 23-field observation model
  - Has ``source_type=sensor`` (real device, not simulator)

Kafka/Redpanda is NOT available in the test environment, so the
producer is replaced with a fake that captures the payload. The
consumer's ``_process()`` method is called directly to insert into
PostgreSQL. No mocking of the SUT beyond the producer.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models.observation import Observation
from app.sensing.sensor_source import SensorSource, build_sensor_provenance
from app.sensing.ingestion_service import SensorIngestionService
from app.streaming.consumer import ConsumerManager
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy, CorroborationState, SourceType

ORG_ID = "org_test_sensor"
INCIDENT_ID = "inc_test_sensor"
DEVICE_ID = "mock-sensor-001"


class MockSensorSource:
    """Deterministic SensorSource for testing — produces real-format telemetry.

    Implements the ``SensorSource`` protocol. Each ``read_telemetry()``
    call returns the next sample from a fixed list, raising
    ``StopIteration`` when exhausted.
    """

    def __init__(self, samples: list[dict] | None = None) -> None:
        self._device_id = DEVICE_ID
        self._org_id = ORG_ID
        self._incident_id = INCIDENT_ID
        self._samples = samples if samples is not None else self._default_samples()
        self._index = 0

    @staticmethod
    def _default_samples() -> list[dict]:
        return [
            {
                "phenomenon": "water_level",
                "value": 2.35,
                "unit": "m",
                "lon": -73.9857,
                "lat": 40.7484,
            },
            {
                "phenomenon": "temperature",
                "value": 24.8,
                "unit": "celsius",
                "lon": -73.9857,
                "lat": 40.7484,
            },
        ]

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def org_id(self) -> str:
        return self._org_id

    @property
    def incident_id(self) -> str:
        return self._incident_id

    def read_telemetry(self) -> dict:
        if self._index >= len(self._samples):
            raise StopIteration("No more telemetry samples")
        raw = self._samples[self._index]
        self._index += 1
        return self._normalize(raw)

    def _normalize(self, raw: dict) -> dict:
        observed_at = now_ms()
        geometry = {
            "type": "Point",
            "coordinates": [raw["lon"], raw["lat"]],
        }
        raw_for_hash = json.dumps(raw, sort_keys=True, default=str)
        return {
            "observation_id": generate_ulid(),
            "event_type": "sensor_reading",
            "phenomenon": raw["phenomenon"],
            "value": float(raw["value"]),
            "unit": raw["unit"],
            "geometry": geometry,
            "geometry_uncertainty": 0.0,
            "observed_at": observed_at,
            "valid_from": observed_at,
            "valid_until": None,
            "received_at": now_ms(),
            "source_id": f"mock:{self._device_id}",
            "source_type": SourceType.sensor.value,
            "collection_method": "mock_sensor",
            "source_reliability": 0.9,
            "freshness": 1.0,
            "corroboration_state": CorroborationState.uncorroborated.value,
            "model_uncertainty": None,
            "quality_flags": {"test": True},
            "access_policy": AccessPolicy.internal.value,
            "provenance_chain": build_sensor_provenance(
                "mock",
                self._device_id,
                sample_index=self._index - 1,
            ),
            "raw_data_hash": "sha256:" + hashlib.sha256(
                raw_for_hash.encode("utf-8")
            ).hexdigest(),
            "model_version": None,
            "supersedes": None,
            "duplicate_group": None,
            "org_id": self._org_id,
            "incident_id": self._incident_id,
        }


class FakeProducer:
    """Captures payloads instead of sending to Kafka."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []
        self._started = True

    @property
    def is_started(self) -> bool:
        return self._started

    async def start(self) -> None:
        self._started = True

    async def send(self, topic: str, message: dict, key: str | None = None) -> None:
        self.sent.append((topic, message))

    async def stop(self) -> None:
        self._started = False


def test_sensor_source_protocol_is_runtime_checkable():
    """MockSensorSource satisfies the SensorSource protocol."""
    source = MockSensorSource()
    assert isinstance(source, SensorSource)


def test_build_sensor_provenance_does_not_mark_simulated():
    """build_sensor_provenance never includes simulated: True."""
    chain = build_sensor_provenance("mqtt", "dev-001", broker="localhost:1883")
    assert chain.get("simulated") is False
    assert chain["source"] == "mqtt"
    assert chain["device_id"] == "dev-001"
    assert chain["broker"] == "localhost:1883"


async def test_full_pipeline_mock_to_postgres():
    """Mock telemetry flows through the full pipeline to PostgreSQL.

    Steps:
      1. MockSensorSource.read_telemetry() → payload dict
      2. SensorIngestionService.ingest_once() → FakeProducer captures payload
      3. ConsumerManager._process(payload) → INSERT into PostgreSQL
      4. Query PostgreSQL to verify the observation
    """
    source = MockSensorSource()
    producer = FakeProducer()
    service = SensorIngestionService(source, producer)

    # Step 1+2: ingest one sample through the service
    payload = await service.ingest_once()
    assert payload is not None, "ingest_once should return the payload"
    assert len(producer.sent) == 1
    assert producer.sent[0][0] == "observations.raw"

    captured_payload = producer.sent[0][1]

    # Verify the payload has the right structure before DB insert
    assert captured_payload["source_type"] == "sensor"
    assert captured_payload["org_id"] == ORG_ID
    assert captured_payload["incident_id"] == INCIDENT_ID
    assert "simulated" not in captured_payload["provenance_chain"] or \
        captured_payload["provenance_chain"]["simulated"] is False

    # Step 3: feed the payload to the consumer's _process() method
    cm = ConsumerManager(bootstrap_servers="localhost:9092")
    await cm._process(captured_payload)

    # Step 4: query PostgreSQL to verify the observation was stored
    db = SessionLocal()
    try:
        result = db.execute(
            select(Observation).where(
                Observation.observation_id == captured_payload["observation_id"]
            )
        )
        obs = result.scalar_one_or_none()
        assert obs is not None, "Observation was not inserted into PostgreSQL"

        # Verify the 23-field observation model fields
        assert obs.observation_id == captured_payload["observation_id"]
        assert obs.event_type == "sensor_reading"
        assert obs.phenomenon == "water_level"
        assert obs.value == 2.35
        assert obs.unit == "m"
        assert obs.geometry_uncertainty == 0.0
        assert obs.observed_at == captured_payload["observed_at"]
        assert obs.source_id == f"mock:{DEVICE_ID}"
        assert obs.source_type == SourceType.sensor
        assert obs.collection_method == "mock_sensor"
        assert obs.source_reliability == 0.9
        assert obs.freshness == 1.0
        assert obs.corroboration_state == CorroborationState.uncorroborated
        assert obs.access_policy == AccessPolicy.internal
        assert obs.org_id == ORG_ID
        assert obs.incident_id == INCIDENT_ID

        # CRITICAL: provenance_chain must NOT mark data as simulated
        chain = obs.provenance_chain
        assert chain.get("simulated") is not True, (
            f"Real sensor data must not be marked simulated: {chain}"
        )
        assert chain.get("source") == "mock"
        assert chain.get("device_id") == DEVICE_ID
    finally:
        db.close()


async def test_ingest_once_returns_none_on_read_error():
    """If read_telemetry raises, ingest_once returns None (no crash)."""
    source = MockSensorSource(samples=[])  # empty → StopIteration
    producer = FakeProducer()
    service = SensorIngestionService(source, producer)

    result = await service.ingest_once()
    assert result is None
    assert len(producer.sent) == 0


async def test_ingest_once_returns_none_when_producer_not_started():
    """If producer is not started, ingest_once returns None."""
    source = MockSensorSource()
    producer = FakeProducer()
    producer._started = False
    service = SensorIngestionService(source, producer)

    result = await service.ingest_once()
    assert result is None


async def test_multiple_samples_ingest_correctly():
    """Multiple telemetry samples flow through the pipeline sequentially."""
    source = MockSensorSource()
    producer = FakeProducer()
    service = SensorIngestionService(source, producer)

    payloads = []
    for _ in range(2):
        p = await service.ingest_once()
        if p is not None:
            payloads.append(p)

    assert len(payloads) == 2
    assert payloads[0]["phenomenon"] == "water_level"
    assert payloads[1]["phenomenon"] == "temperature"
    assert payloads[0]["observation_id"] != payloads[1]["observation_id"]

    # Both payloads must have non-simulated provenance
    for p in payloads:
        assert p["provenance_chain"].get("simulated") is not True
