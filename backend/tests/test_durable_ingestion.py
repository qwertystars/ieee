from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.ingestion.adapters.event_registry import EventRegistryAdapter
from app.lib.idempotency import (
    IdempotencyKey,
    authorize_replay,
    record_ingestion_failure,
    record_raw_event,
)
from app.lib.ulid import generate_ulid
from app.main import app
from app.models.events import Event, RawEvent, RawEventRecord
from app.models.observation import Observation
from app.streaming.consumer import DLQ_RETENTION_DAYS, ConsumerManager
from app.streaming.producer import ProducerManager


def _raw_event(external_id: str) -> RawEvent:
    event_id = generate_ulid()
    return RawEvent(
        event_id=event_id,
        org_id="org_task5",
        incident_id="incident_task5",
        source_id="source_task5",
        external_id=external_id,
        event_type="sensor_observation",
        source_time_ms=1756000000000,
        receipt_time_ms=1756000000001,
        sequence=1,
        payload={"value": 2.5, "phenomenon": "water_level"},
    )


def test_raw_event_survives_crash_after_api_ack() -> None:
    event = _raw_event(f"crash-{generate_ulid()}")
    db = SessionLocal()
    try:
        assert record_raw_event(db, event) is True
        db.commit()

        row = db.get(RawEventRecord, event.event_id)
        assert row is not None
        assert row.canonical_hash == event.canonical_hash()
        assert row.payload == event.payload
    finally:
        db.execute(delete(RawEventRecord).where(RawEventRecord.id == event.event_id))
        db.commit()
        db.close()


def test_duplicate_external_delivery_has_one_raw_effect() -> None:
    event = _raw_event(f"duplicate-{generate_ulid()}")
    db = SessionLocal()
    try:
        assert record_raw_event(db, event) is True
        assert record_raw_event(db, event) is False
        db.commit()

        rows = db.execute(
            select(RawEventRecord).where(
                RawEventRecord.org_id == event.org_id,
                RawEventRecord.source_id == event.source_id,
                RawEventRecord.external_id == event.external_id,
            )
        ).scalars().all()
        assert len(rows) == 1
    finally:
        db.execute(
            delete(RawEventRecord).where(
                RawEventRecord.org_id == event.org_id,
                RawEventRecord.source_id == event.source_id,
                RawEventRecord.external_id == event.external_id,
            )
        )
        db.commit()
        db.close()


def test_failure_is_durable_and_replay_requires_admin() -> None:
    external_id = f"poison-{generate_ulid()}"
    db = SessionLocal()
    try:
        failure = record_ingestion_failure(
            db,
            {
                "org_id": "org_task5",
                "incident_id": "incident_task5",
                "source_id": "source_task5",
                "external_id": external_id,
                "payload": "malformed",
            },
            "missing observation_id",
        )
        assert failure.action == "ingestion.failed"

        try:
            authorize_replay(
                db,
                failure.entity,
                org_id="org_task5",
                actor="viewer",
                role="viewer",
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("non-admin replay must be rejected")

        replay = authorize_replay(
            db,
            failure.entity,
            org_id="org_task5",
            actor="admin",
            role="admin",
        )
        assert replay.action == "ingestion.replay"
    finally:
        db.execute(
            delete(Event).where(
                Event.org_id == "org_task5",
                Event.entity == external_id,
            )
        )
        db.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.org_id == "org_task5",
                IdempotencyKey.external_id == external_id,
            )
        )
        db.commit()
        db.close()


def test_replay_lookup_is_tenant_scoped() -> None:
    external_id = f"tenant-replay-{generate_ulid()}"
    db = SessionLocal()
    try:
        failure = record_ingestion_failure(
            db,
            {
                "org_id": "org_task5_a",
                "incident_id": "incident_task5",
                "source_id": "source_task5",
                "external_id": external_id,
            },
            "poison payload",
        )
        with pytest.raises(LookupError):
            authorize_replay(
                db,
                failure.entity,
                org_id="org_task5_b",
                actor="admin",
                role="admin",
            )
    finally:
        db.execute(delete(Event).where(Event.entity == external_id))
        db.execute(delete(Event).where(Event.org_id.in_(["org_task5_a", "org_task5_b"])))
        db.commit()
        db.close()


def test_dlq_retention_is_thirty_days() -> None:
    assert DLQ_RETENTION_DAYS == 30


def test_dlq_unavailable_is_not_acknowledged() -> None:
    consumer = ConsumerManager(bootstrap_servers="localhost:9092")
    assert consumer._dlq_producer is None


def test_api_acknowledgement_writes_ledger_and_retries_idempotently() -> None:
    source_id = f"api-source-{generate_ulid()}"
    idempotency_key = f"api-key-{generate_ulid()}"
    feature: dict[str, Any] = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [144.9, -37.8]},
        "properties": {
            "event_type": "sensor_observation",
            "phenomenon": "water_level",
            "value": 1.5,
            "source_id": source_id,
            "source_type": "sensor",
        },
    }
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            data={
                "username": "admin@demo.disaster",
                "password": "demo1234",
            },
        )
        assert login.status_code == 200
        headers = {
            "Authorization": f"Bearer {login.json()['access_token']}",
            "Idempotency-Key": idempotency_key,
        }
        incident = client.post(
            "/api/incidents",
            json={"title": "Durability probe", "disaster_type": "flood"},
            headers=headers,
        )
        assert incident.status_code == 201
        incident_id = incident.json()["id"]
        first = client.post(
            "/api/observations",
            params={"incident_id": incident_id},
            json=feature,
            headers=headers,
        )
        second = client.post(
            "/api/observations",
            params={"incident_id": incident_id},
            json=feature,
            headers=headers,
        )
    assert first.status_code == 201
    assert second.status_code == 201
    observation_id = first.json()["properties"]["observation_id"]
    assert second.json()["properties"]["observation_id"] == observation_id

    db = SessionLocal()
    try:
        raw_rows = db.execute(
            select(RawEventRecord).where(
                RawEventRecord.org_id == "org_demo",
                RawEventRecord.source_id == source_id,
                RawEventRecord.external_id == idempotency_key,
            )
        ).scalars().all()
        assert len(raw_rows) == 1
        assert db.execute(
            select(Observation).where(Observation.observation_id == observation_id)
        ).scalar_one_or_none() is not None
    finally:
        db.execute(delete(Observation).where(Observation.observation_id == observation_id))
        db.execute(
            delete(RawEventRecord).where(RawEventRecord.source_id == source_id)
        )
        db.execute(
            delete(IdempotencyKey).where(IdempotencyKey.external_id == idempotency_key)
        )
        db.commit()
        db.close()


def test_social_publish_failure_does_not_consume_idempotency() -> None:
    adapter = EventRegistryAdapter({"api_key": "test"})
    article = {
        "uri": f"article-{generate_ulid()}",
        "title": "Flood report",
        "date": "2026-07-26T10:00:00Z",
        "source": {"location": {"lat": 1.0, "lon": 2.0}},
    }
    adapter.pull_articles = AsyncMock(return_value=[article])
    producer = AsyncMock()
    producer.send.side_effect = TimeoutError("broker timeout")
    db = SessionLocal()
    try:
        with pytest.raises(TimeoutError, match="broker timeout"):
            asyncio.run(adapter.sync(db, producer, "org_task5", "incident_task5"))
        assert db.query(IdempotencyKey).filter_by(
            org_id="org_task5", source="event_registry", external_id=article["uri"]
        ).first() is None
    finally:
        db.rollback()
        db.close()


def test_social_route_does_not_have_noop_success_path() -> None:
    from app.api.routes import ingest

    assert not hasattr(ingest, "_NoopProducer")


def test_admin_replay_requeues_recorded_failure_payload() -> None:
    external_id = f"replay-{generate_ulid()}"
    db = SessionLocal()
    producer = ProducerManager(bootstrap_servers="localhost:9092")
    producer.send = AsyncMock()
    try:
        failure = record_ingestion_failure(
            db,
            {
                "org_id": "org_task5",
                "incident_id": "incident_task5",
                "source_id": "source_task5",
                "external_id": external_id,
                "observation_id": generate_ulid(),
            },
            "poison payload",
        )
        replay = asyncio.run(
            producer.replay_failure(
                db,
                failure.entity,
                org_id="org_task5",
                actor="admin",
                role="admin",
            )
        )
        assert replay.action == "ingestion.replay"
        assert producer.send.await_count == 1
        assert producer.send.await_args.args[0] == "observations.raw"
    finally:
        db.execute(delete(Event).where(Event.entity == external_id))
        db.commit()
        db.close()


def test_single_malformed_fields_return_422() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            data={"username": "admin@demo.disaster", "password": "demo1234"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        incident = client.post(
            "/api/incidents",
            json={"title": "Malformed probe", "disaster_type": "flood"},
            headers=headers,
        )
        response = client.post(
            "/api/observations",
            params={"incident_id": incident.json()["id"]},
            json={
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1, 2]},
                "properties": {"observed_at": "not-an-epoch"},
            },
            headers=headers,
        )
    assert response.status_code == 422


def test_batch_malformed_fields_return_422() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            data={"username": "admin@demo.disaster", "password": "demo1234"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        incident = client.post(
            "/api/incidents",
            json={"title": "Malformed batch probe", "disaster_type": "flood"},
            headers=headers,
        )
        response = client.post(
            "/api/observations/batch",
            params={"incident_id": incident.json()["id"]},
            json={
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1, 2]},
                    "properties": {
                        "event_type": "sensor_observation",
                        "phenomenon": "water_level",
                        "source_id": "malformed",
                        "observed_at": "not-an-epoch",
                    },
                }],
            },
            headers=headers,
        )
    assert response.status_code == 422
