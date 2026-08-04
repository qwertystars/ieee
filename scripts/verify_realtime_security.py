#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "fastapi"]
# ///

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Annotated
from unittest.mock import MagicMock, patch

import typer
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path.cwd()))

import app.deps as deps_module
from app.auth.seed import seed_demo_users
from app.db import SessionLocal
from app.deps import revoke_token
from app.main import app
from app.models.incident import Incident
from app.realtime.manager import _filter_message

PASSWORD = "demo1234"
ORG_ID = "org_demo"


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        data={"username": "admin@demo.disaster", "password": PASSWORD},
    )
    if response.status_code != 200:
        typer.echo(f"login failed: {response.status_code}", err=True)
        raise typer.Exit(code=1)
    return response.json()["access_token"]


def _ensure_incident() -> tuple[str, bool]:
    db = SessionLocal()
    try:
        seed_demo_users(db)
        incident_id = "01J9VERIFYREALTIME00000000"
        created = db.query(Incident).filter(Incident.id == incident_id).first() is None
        if created:
            db.add(
                Incident(
                    id=incident_id,
                    org_id=ORG_ID,
                    title="Realtime security verification",
                    disaster_type="flood",
                    severity="moderate",
                    status="active",
                    start_time=1_700_000_000_000,
                    created_at=1_700_000_000_000,
                    updated_at=1_700_000_000_000,
                )
            )
            db.commit()
        return incident_id, created
    finally:
        db.close()


def _cleanup_incident(incident_id: str, created: bool) -> None:
    if not created:
        return
    db = SessionLocal()
    try:
        db.query(Incident).filter(Incident.id == incident_id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def _run_checks(incident_id: str, deadline_s: float, close_code: int) -> list[CheckResult]:
    results: list[CheckResult] = []
    with TestClient(app) as client:
        token = _login(client)
        with client.websocket_connect(
            f"/ws/realtime/{incident_id}?token={token}"
        ) as websocket:
            started = time.monotonic()
            with patch.object(deps_module, "get_redis", return_value=None):
                revoke_token(token, 3600)
            websocket.send_text("recheck-auth")
            try:
                websocket.receive_text()
            except WebSocketDisconnect as exc:
                elapsed = time.monotonic() - started
                results.append(
                    CheckResult(
                        "revocation_deadline",
                        exc.code == close_code and elapsed <= deadline_s,
                        f"close={exc.code} elapsed_s={elapsed:.3f}",
                    )
                )

        with deps_module._local_revoked_lock:
            deps_module._local_revoked_tokens.clear()
        fresh_token = _login(client)
        redis_for_auth = MagicMock()
        redis_for_auth.sismember.return_value = 0
        with patch.object(deps_module, "get_redis", return_value=redis_for_auth):
            wrong = client.get(
                "/api/incidents/01J9UNKNOWNREALTIME0000000000/updates?since=0",
                headers={"Authorization": f"Bearer {fresh_token}"},
            )
        results.append(
            CheckResult("wrong_incident_denied", wrong.status_code == 403, str(wrong.status_code))
        )
        with patch.object(deps_module, "get_redis", return_value=None):
            outage = client.get(
                f"/api/incidents/{incident_id}/updates?since=0",
                headers={"Authorization": f"Bearer {fresh_token}"},
            )
        results.append(
            CheckResult("redis_outage_denied", outage.status_code == 401, str(outage.status_code))
        )

    sensitive = _filter_message(
        {
            "type": "new_observation",
            "payload": {
                "access_policy": "sensitive",
                "raw_data_hash": "protected",
            },
        },
        "viewer",
    )
    results.append(
        CheckResult("zero_protected_fields", sensitive is None, str(sensitive))
    )
    return results


def main(
    revocation_deadline_s: Annotated[float, typer.Option(min=0.0)] = 60.0,
    expect_close_code: Annotated[int, typer.Option()] = 4401,
    expect_zero_protected_fields: Annotated[bool, typer.Option()] = False,
) -> None:
    """Run live realtime authorization denial checks."""
    incident_id, created = _ensure_incident()
    try:
        results = _run_checks(incident_id, revocation_deadline_s, expect_close_code)
        if not expect_zero_protected_fields:
            results = [result for result in results if result.name != "zero_protected_fields"]
        for result in results:
            typer.echo(f"{'PASS' if result.passed else 'FAIL'} {result.name}: {result.detail}")
        if not all(result.passed for result in results):
            raise typer.Exit(code=1)
    finally:
        _cleanup_incident(incident_id, created)


if __name__ == "__main__":
    typer.run(main)
