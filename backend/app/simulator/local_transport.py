"""Explicit development transport for simulated observations, without Kafka."""

from __future__ import annotations

from app.db import SessionLocal
from app.lib.audit import write_audit
from app.lib.idempotency import check_and_record, next_raw_sequence, record_raw_event
from app.lib.time import now_ms
from app.lib.ulid import generate_ulid
from app.streaming.consumer import ConsumerManager


def persist_simulation(payload: dict, run_id: str) -> None:
    """Persist draft, simulated data using the canonical ingestion contracts."""
    codec = ConsumerManager()
    stamp = now_ms()
    normalized = {**payload,
        "observation_id": generate_ulid(),
        "external_id": f"{run_id}:{payload['observation_id']}",
        "observed_at": stamp, "received_at": stamp,
        "source_time_ms": stamp, "receipt_time_ms": stamp,
        "collection_method": "digital_twin",
        "visibility": "internal", "review_status": "draft",
        "provenance_chain": {"simulated": True, "run_id": run_id,
            "simulation_time_ms": payload["observed_at"],
            "simulation_observation_id": payload["observation_id"]},
    }
    with SessionLocal() as db:
        normalized["sequence"] = next_raw_sequence(db, normalized["org_id"], normalized["source_id"])
        if not check_and_record(db, normalized["source_id"], normalized["external_id"],
            org_id=normalized["org_id"], incident_id=normalized["incident_id"],
            payload=normalized, commit=False):
            return
        raw = codec._build_raw_event(normalized)
        if not record_raw_event(db, raw):
            return
        db.add(codec._build_observation(normalized, raw))
        write_audit(db, org_id=normalized["org_id"], incident_id=normalized["incident_id"],
            actor="digital_twin", action="simulator.observation", entity=normalized["observation_id"],
            after={"phenomenon": normalized["phenomenon"], "simulated": True, "run_id": run_id},
            review_status="draft")


def build_simulation_payload(engine, device, phenomenon: str, value: float, unit: str, obs_id: str) -> dict:
    """Preserve the Kafka payload and deterministic identifiers."""
    import hashlib
    import json

    payload = {"observation_id": obs_id, "event_type": "sensor_observation",
        "phenomenon": phenomenon,
        "geometry": {"type": "Point", "coordinates": [device.lon, device.lat]},
        "observed_at": engine._sim_time_ms, "source_id": f"simulator:{device.device_id}",
        "source_type": "sensor", "org_id": engine._org_id, "incident_id": engine._incident_id,
        "value": float(value), "unit": unit, "provenance_chain": {"simulated": True}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["raw_data_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return payload
