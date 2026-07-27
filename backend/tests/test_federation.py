"""Tests for federated data fabric — source management and delayed sync.

Uses the real PostgreSQL database via SessionLocal. The sources and
federation_outbox tables are created by Alembic migrations. All test rows
are cleaned up.
"""

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.ingestion.federation import (
    OutboxEntry,
    OutboxManager,
    SourceManager,
)
from app.lib.ulid import generate_ulid
from app.models.enums import AccessPolicy
from app.models.observation import Observation
from app.models.source import Ownership, Source, SourceKind, SourceStatus

ORG_ID = "org_test_federation"


@pytest.fixture
def db():
    """Yield a session and clean up test rows after each test."""
    session = SessionLocal()
    for model in (OutboxEntry, Observation, Source):
        session.execute(delete(model).where(model.org_id == ORG_ID))
    session.commit()
    try:
        yield session
    finally:
        for model in (OutboxEntry, Observation, Source):
            session.execute(delete(model).where(model.org_id == ORG_ID))
        session.commit()
        session.close()


def _make_payload(source_id: str, observation_id: str | None = None) -> dict:
    """Build a valid observation payload for the outbox."""
    return {
        "observation_id": observation_id or generate_ulid(),
        "event_type": "flood", "phenomenon": "water_level",
        "value": 1.5, "unit": "m",
        "geometry_wkt": "POINT(-73.9857 40.7484)",
        "geometry_uncertainty": 5.0,
        "observed_at": 1721300000000, "valid_from": 1721300000000,
        "received_at": 1721300001000,
        "source_id": source_id, "source_type": "sensor",
        "collection_method": "stream_gauge", "source_reliability": 0.9,
        "freshness": 0.95, "corroboration_state": "uncorroborated",
        "quality_flags": {"outlier": False}, "access_policy": "internal",
        "provenance_chain": {"steps": ["ingest", "normalize"]},
        "raw_data_hash": "abc123def456",
        "org_id": ORG_ID, "incident_id": "inc_test_001",
    }


def test_register_source(db):
    """Register a source and verify all fields are persisted."""
    sm = SourceManager(db)
    source_id = sm.register_source(
        org_id=ORG_ID, name="USGS CAP Feed", type=SourceKind.cap_feed,
        provider="usgs.gov", config={"url": "https://example.com/feed"},
        ownership=Ownership.owned, access_policy=AccessPolicy.public,
        refresh_interval_s=300,
    )
    assert len(source_id) == 26

    source = db.get(Source, source_id)
    assert source is not None
    assert source.name == "USGS CAP Feed"
    assert source.type == SourceKind.cap_feed
    assert source.provider == "usgs.gov"
    assert source.ownership == Ownership.owned
    assert source.access_policy == AccessPolicy.public
    assert source.status == SourceStatus.active
    assert source.refresh_interval_s == 300
    assert source.last_success_at is None
    assert source.last_error is None
    assert source.config == {"url": "https://example.com/feed"}


def test_update_source_status(db):
    """Update source status after success and failure."""
    sm = SourceManager(db)
    source_id = sm.register_source(
        org_id=ORG_ID, name="SensorThings API", type=SourceKind.sensorthings,
        provider="sensors.local", config={}, ownership=Ownership.federated,
        access_policy=AccessPolicy.internal,
    )

    # Simulate a successful sync
    sm.update_source_status(source_id, success=True)
    source = db.get(Source, source_id)
    assert source.status == SourceStatus.active
    assert source.last_success_at is not None
    assert source.last_error is None

    # Simulate a failure
    sm.update_source_status(source_id, success=False, error="connection timeout")
    source = db.get(Source, source_id)
    assert source.status == SourceStatus.error
    assert source.last_error == "connection timeout"


def test_outbox_delayed_sync(db):
    """Add observation to outbox, sync, verify it's inserted into observations."""
    sm = SourceManager(db)
    source_id = sm.register_source(
        org_id=ORG_ID, name="Field Sensor", type=SourceKind.internal,
        provider="field_device_01", config={}, ownership=Ownership.owned,
        access_policy=AccessPolicy.internal,
    )

    obs_id = generate_ulid()
    payload = _make_payload(source_id, obs_id)

    om = OutboxManager(db)
    outbox_id = om.add_to_outbox(obs_id, source_id, payload, sync_priority=1)
    assert len(outbox_id) == 26

    # Verify pending
    pending = om.get_pending_outbox()
    assert len(pending) == 1
    assert pending[0].status == "pending"

    # Sync
    synced = om.sync_outbox()
    assert synced == 1

    # Verify observation was inserted
    obs = db.get(Observation, obs_id)
    assert obs is not None
    assert obs.event_type == "flood"
    assert obs.value == 1.5
    assert obs.source_id == source_id

    # Verify outbox entry is marked as synced
    entry = db.get(OutboxEntry, outbox_id)
    assert entry.status == "synced"
    assert entry.synced_at is not None

    # Verify no more pending
    assert len(om.get_pending_outbox()) == 0


def test_source_ownership_filter(db):
    """Create owned + federated sources, filter by ownership."""
    sm = SourceManager(db)
    owned_id = sm.register_source(
        org_id=ORG_ID, name="Owned Feed", type=SourceKind.cap_feed,
        provider="local", config={}, ownership=Ownership.owned,
        access_policy=AccessPolicy.public,
    )
    fed_id = sm.register_source(
        org_id=ORG_ID, name="Federated Feed", type=SourceKind.ogc_features,
        provider="remote.org", config={}, ownership=Ownership.federated,
        access_policy=AccessPolicy.internal,
    )
    agg_id = sm.register_source(
        org_id=ORG_ID, name="Aggregated Feed", type=SourceKind.hdx,
        provider="hdx.org", config={}, ownership=Ownership.aggregated,
        access_policy=AccessPolicy.sensitive,
    )

    # All sources
    all_sources = sm.list_sources(ORG_ID)
    assert len(all_sources) == 3

    # Filter: owned only
    owned = sm.list_sources(ORG_ID, ownership_filter=Ownership.owned)
    assert len(owned) == 1
    assert owned[0].id == owned_id

    # Filter: federated only
    federated = sm.list_sources(ORG_ID, ownership_filter=Ownership.federated)
    assert len(federated) == 1
    assert federated[0].id == fed_id

    # Filter: aggregated only
    aggregated = sm.list_sources(ORG_ID, ownership_filter=Ownership.aggregated)
    assert len(aggregated) == 1
    assert aggregated[0].id == agg_id


def test_federated_source_not_centralized(db):
    """Federated sources must NOT have their observations centralized."""
    sm = SourceManager(db)
    source_id = sm.register_source(
        org_id=ORG_ID, name="Remote OGC Features", type=SourceKind.ogc_features,
        provider="remote.org", config={}, ownership=Ownership.federated,
        access_policy=AccessPolicy.internal,
    )

    obs_id = generate_ulid()
    payload = _make_payload(source_id, obs_id)

    om = OutboxManager(db)
    outbox_id = om.add_to_outbox(obs_id, source_id, payload)

    synced = om.sync_outbox()
    assert synced == 0  # federated sources are not centralized

    # Observation was NOT inserted
    obs = db.get(Observation, obs_id)
    assert obs is None

    # Outbox entry is marked as skipped
    entry = db.get(OutboxEntry, outbox_id)
    assert entry.status == "skipped"
    assert "federated" in (entry.error or "")
