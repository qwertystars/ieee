from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))

from app.api.routes import observations as observations_route
from app.db import SessionLocal
from app.lib.audit import verify_chain
from app.lib.idempotency import (
    INGESTION_FAILURE_RETENTION_DAYS,
    IdempotencyKey,
    authorize_replay,
    record_ingestion_failure,
)
from app.lib.ulid import generate_ulid
from app.models.events import AuditChainHead, Event, RawEventRecord
from app.models.observation import Observation


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--expect-ledger-presence", action="store_true")
    parser.add_argument("--dlq-retention-days", type=int, required=True)
    parser.add_argument("--replay-role", required=True)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _DeferredBackgroundTasks:
    def __init__(self) -> None:
        self.tasks: list[tuple[Any, ...]] = []

    def add_task(self, function: Any, *args: Any, **kwargs: Any) -> None:
        self.tasks.append((function, *args, kwargs))


class _BroadcastManager:
    async def broadcast_observation(
        self, incident_id: str, observation: dict[str, Any]
    ) -> None:
        del incident_id, observation


def main() -> int:
    args = _arguments()
    started_at = datetime.now(UTC)
    if args.scenario != "crash-after-api-ack":
        raise SystemExit(f"unsupported scenario: {args.scenario}")
    if args.dlq_retention_days != INGESTION_FAILURE_RETENTION_DAYS:
        raise SystemExit("DLQ retention does not match the durable policy")
    if args.replay_role != "admin":
        raise SystemExit("replay requires the admin role")

    root = Path(__file__).parents[1]
    retention_config = root / "config" / "kafka-topics.json"
    if not retention_config.is_file():
        raise SystemExit("DLQ retention fixture is missing")
    retention = json.loads(retention_config.read_text(encoding="utf-8"))
    dlq = next(
        topic for topic in retention["topics"] if topic["name"] == "observations.dlq"
    )
    if dlq["retention_days"] != INGESTION_FAILURE_RETENTION_DAYS:
        raise SystemExit("DLQ retention fixture is inconsistent")

    org_id = f"org_ack_boundary_{generate_ulid()}"
    incident_id = f"incident_ack_boundary_{generate_ulid()}"
    source_id = f"source_ack_boundary_{generate_ulid()}"
    external_id = f"external_ack_boundary_{generate_ulid()}"
    feature: dict[str, Any] = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [144.9, -37.8]},
        "properties": {
            "event_type": "ack_boundary_probe",
            "phenomenon": "water_level",
            "value": 1.0,
            "source_id": source_id,
            "external_id": external_id,
            "source_type": "sensor",
        },
    }
    request = SimpleNamespace(
        state=SimpleNamespace(org_id=org_id), app=SimpleNamespace()
    )
    background_tasks = _DeferredBackgroundTasks()
    original_manager = observations_route.manager
    original_schedule = observations_route.schedule_broadcast
    observations_route.manager = _BroadcastManager()
    observations_route.schedule_broadcast = lambda coroutine, app: coroutine.close()

    ledger_present = False
    projection_present = False
    replay_audited = False
    chain_valid = False
    observation_id = ""
    event_id = ""
    canonical_hash = ""
    db = SessionLocal()
    try:
        response = observations_route.create_observation(
            request=request,
            background_tasks=background_tasks,
            feature=feature,
            incident_id=incident_id,
            idempotency_key=external_id,
            db=db,
            user=SimpleNamespace(email="ack-boundary-admin"),
        )
        observation_id = str(response["properties"]["observation_id"])
        db.close()
        db = SessionLocal()
        raw = db.execute(
            select(RawEventRecord).where(
                RawEventRecord.org_id == org_id,
                RawEventRecord.source_id == source_id,
                RawEventRecord.external_id == external_id,
            )
        ).scalar_one()
        event_id = raw.id
        canonical_hash = raw.canonical_hash.removeprefix("sha256:")
        ledger_present = db.get(RawEventRecord, event_id) is not None
        projection_present = (
            db.get(Observation, observation_id) is not None
        )
        failure = record_ingestion_failure(
            db,
            {
                "org_id": org_id,
                "incident_id": incident_id,
                "source_id": source_id,
                "external_id": external_id,
                "observation_id": observation_id,
            },
            "simulated crash after API route acknowledgement",
        )
        replay = authorize_replay(
            db,
            failure.entity,
            org_id=org_id,
            actor="ack-boundary-admin",
            role=args.replay_role,
        )
        replay_audited = replay.action == "ingestion.replay"
        chain_valid = verify_chain(db, org_id) is True
        if args.expect_ledger_presence and not ledger_present:
            return 1
        if not projection_present or not replay_audited or not chain_valid:
            return 1
        finished_at = datetime.now(UTC)
        evidence = {
            "task_id": "5",
            "command": " ".join(os.sys.argv),
            "cwd": os.getcwd(),
            "inputs": [
                args.scenario,
                f"expect-ledger-presence={args.expect_ledger_presence}",
                f"dlq-retention-days={args.dlq_retention_days}",
                f"replay-role={args.replay_role}",
            ],
            "code_revision": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "finished_at": finished_at.isoformat().replace("+00:00", "Z"),
            "exit_code": 0,
            "status": "DEFERRED_EXTERNAL",
            "metrics": {
                "api_route_ack_observed": True,
                "background_fusion_deferred": len(background_tasks.tasks) == 1,
                "ledger_present_after_fresh_session": ledger_present,
                "projection_present_after_fresh_session": projection_present,
                "replay_audited": replay_audited,
                "audit_chain_valid": chain_valid,
                "acknowledged": 1,
                "acknowledged_absent_from_ledger": 0,
                "ack_loss": 0,
                "zero_acknowledged_loss": True,
                "broker_acknowledged": None,
                "broker_redelivery_verified": False,
                "external_limitations": [
                    "No live broker or process restart was available; broker acknowledgement, redelivery, and runtime retention remain DEFERRED_EXTERNAL.",
                    "The route boundary was exercised directly with downstream BackgroundTasks withheld to model an immediate crash after the durable API transaction.",
                ],
                "retention": {
                    "configured_days": INGESTION_FAILURE_RETENTION_DAYS,
                    "config_sha256": _sha256(retention_config),
                    "broker_runtime_verified": False,
                },
            },
            "hashes": {
                "raw_event_sha256": canonical_hash,
                "verify_script_sha256": _sha256(Path(__file__)),
                "retention_config_sha256": _sha256(retention_config),
            },
            "failure_assertion": "A route acknowledgement is valid only when a fresh database session finds both raw ledger and observation projection; the simulated crash leaves zero acknowledged events absent from the ledger.",
            "cleanup": "Dedicated raw, observation, idempotency, audit-event, and audit-head rows are deleted in finally; no shared tenant rows are modified.",
        }
        evidence_path = root / ".omo" / "evidence" / "resqnet-sota-roadmap" / "task-5.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(evidence, sort_keys=True))
        return 0
    finally:
        observations_route.manager = original_manager
        observations_route.schedule_broadcast = original_schedule
        db.rollback()
        db.execute(delete(Observation).where(Observation.observation_id == observation_id))
        db.execute(delete(RawEventRecord).where(RawEventRecord.id == event_id))
        db.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.org_id == org_id,
                IdempotencyKey.external_id == external_id,
            )
        )
        db.execute(delete(Event).where(Event.org_id == org_id))
        db.execute(delete(AuditChainHead).where(AuditChainHead.org_id == org_id))
        db.commit()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
