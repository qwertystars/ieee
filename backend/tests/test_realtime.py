"""Tests for the realtime WebSocket manager and polling fallback router.

Uses duck-typed MockWebSocket objects (no starlette test client required)
and a MockDB for the polling endpoint. Runs via plain asyncio.run — no
pytest-asyncio dependency.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db
from app.realtime.manager import WebSocketManager, router


class MockWebSocket:
    """Duck-typed WebSocket: records every send_json payload in `sent`."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    async def receive_text(self) -> str:
        # Block forever — tests don't drive the receive loop.
        await asyncio.Event().wait()
        return ""


class MockResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> MockResult:
        return self

    def all(self) -> list[Any]:
        return self._rows


class MockDB:
    """Minimal Session stub: execute(stmt) returns MockResult(scalars().all())."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows or []
        self.last_stmt: Any = None

    def execute(self, stmt: Any) -> MockResult:
        self.last_stmt = stmt
        return MockResult(self.rows)

    def close(self) -> None:  # pragma: no cover - not exercised
        pass


class FakeObservation:
    """Lightweight stand-in for an Observation ORM row."""

    def __init__(
        self,
        observation_id: str = "obs_1",
        incident_id: str = "inc_001",
        event_type: str = "flood",
        phenomenon: str = "water_level",
        value: float | None = 2.5,
        unit: str | None = "m",
        observed_at: int = 2000,
        received_at: int = 2100,
        source_id: str = "src_1",
        source_type: Any = None,
        corroboration_state: Any = None,
        access_policy: Any = None,
    ) -> None:
        self.observation_id = observation_id
        self.incident_id = incident_id
        self.event_type = event_type
        self.phenomenon = phenomenon
        self.value = value
        self.unit = unit
        self.observed_at = observed_at
        self.received_at = received_at
        self.source_id = source_id
        self.source_type = source_type
        self.corroboration_state = corroboration_state
        self.access_policy = access_policy


def test_broadcast_to_connected() -> None:
    """Given a connected ws, broadcast_observation delivers a new_observation msg."""

    async def scenario() -> None:
        mgr = WebSocketManager()
        ws = MockWebSocket()
        await mgr.connect(ws, "inc_001")
        await mgr.broadcast_observation(
            "inc_001", {"observation_id": "obs_1", "event_type": "flood"}
        )
        assert ws.accepted is True
        assert len(ws.sent) == 1
        msg = ws.sent[0]
        assert msg["type"] == "new_observation"
        assert msg["payload"]["observation_id"] == "obs_1"

    asyncio.run(scenario())


def test_concurrent_clients() -> None:
    """Two clients on the same incident both receive the broadcast."""

    async def scenario() -> None:
        mgr = WebSocketManager()
        ws_a = MockWebSocket()
        ws_b = MockWebSocket()
        await mgr.connect(ws_a, "inc_001")
        await mgr.connect(ws_b, "inc_001")
        await mgr.broadcast_hypothesis("inc_001", {"id": "h_1"})
        assert len(ws_a.sent) == 1
        assert len(ws_b.sent) == 1
        assert ws_a.sent[0]["type"] == "hypothesis_changed"
        assert ws_b.sent[0]["payload"]["id"] == "h_1"

    asyncio.run(scenario())


def test_no_cross_incident_leak() -> None:
    """A broadcast to inc_A must not reach a client subscribed to inc_B."""

    async def scenario() -> None:
        mgr = WebSocketManager()
        ws_a = MockWebSocket()
        ws_b = MockWebSocket()
        await mgr.connect(ws_a, "inc_A")
        await mgr.connect(ws_b, "inc_B")
        await mgr.broadcast_plan("inc_A", {"plan_id": "p_1"})
        assert len(ws_a.sent) == 1
        assert ws_a.sent[0]["type"] == "plan_updated"
        assert len(ws_b.sent) == 0

    asyncio.run(scenario())


def test_connection_count() -> None:
    """get_connection_count reflects connect/disconnect accurately."""

    async def scenario() -> None:
        mgr = WebSocketManager()
        ws_a = MockWebSocket()
        ws_b = MockWebSocket()
        await mgr.connect(ws_a, "inc_001")
        await mgr.connect(ws_b, "inc_001")
        assert mgr.get_connection_count("inc_001") == 2
        await mgr.disconnect(ws_a, "inc_001")
        assert mgr.get_connection_count("inc_001") == 1
        await mgr.disconnect(ws_b, "inc_001")
        assert mgr.get_connection_count("inc_001") == 0

    asyncio.run(scenario())


def test_polling_fallback() -> None:
    """GET /api/incidents/{id}/updates?since=N returns observations newer than N."""
    obs_rows = [
        FakeObservation(
            observation_id="obs_a",
            incident_id="inc_001",
            observed_at=1500,
            received_at=1600,
        ),
        FakeObservation(
            observation_id="obs_b",
            incident_id="inc_001",
            observed_at=1800,
            received_at=1900,
        ),
    ]
    mock_db = MockDB(rows=obs_rows)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db

    client = TestClient(app)
    resp = client.get("/api/incidents/inc_001/updates?since=1000")
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_id"] == "inc_001"
    assert body["since"] == 1000
    assert body["count"] == 2
    ids = [o["observation_id"] for o in body["observations"]]
    assert ids == ["obs_a", "obs_b"]
    assert body["observations"][0]["observed_at"] == 1500
