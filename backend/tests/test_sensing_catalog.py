"""Tests for the sensing action catalog (T31).

Test cases:
  1. test_catalog_returns_all_action_types — all 11 sensing action types present
  2. test_get_top_actions_returns_top_n_with_display — top-3 ranked by EVI with display text
  3. test_dispatch_creates_task — dispatch creates an OperationalTask row
  4. test_action_has_cost_gain_impact_fields — action has cost/gain/impact fields
  5. test_dispatch_requires_human_approval — dispatch returns pending status (no auto-dispatch)

Verification command:
    docker compose run --rm -e PYTHONPATH=/app backend sh -c \
        "pip install pytest -q && python -m pytest tests/test_sensing_catalog.py -q"
"""

from __future__ import annotations

from app.models.entities import OperationalTask
from app.sensing.catalog import SensingActionCatalog
from app.sensing.catalog_types import ActionCost, CatalogAction, RiskLevel
from app.sensing.evi_types import SensingActionType


class _FakeSession:
    """Minimal Session fake that captures objects passed to add()."""

    def __init__(self) -> None:
        self.added: list[OperationalTask] = []

    def add(self, obj: OperationalTask) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        pass


_EXPECTED_ACTION_IDS = {
    "ask_responder",
    "task_drone",
    "request_citizen_photo",
    "call_shelter",
    "poll_river_sensor",
    "request_satellite",
    "deploy_lora_relay",
    "query_traffic_probe",
    "contact_hospital",
    "ask_utility",
    "move_uav",
    "deploy_rescue_ball",
}


def _make_catalog() -> SensingActionCatalog:
    return SensingActionCatalog()


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_catalog_returns_all_action_types() -> None:
    """Catalog returns all 11 sensing action types from SOTA spec §9.3."""
    catalog = _make_catalog()
    actions = catalog.get_actions()

    assert len(actions) == 12
    action_ids = {a.id for a in actions}
    assert action_ids == _EXPECTED_ACTION_IDS

    action_types = {a.action_type for a in actions}
    assert action_types == set(SensingActionType)


def test_get_top_actions_returns_top_n_with_display() -> None:
    """get_top_actions returns top-3 by expected information gain with display text.

    Satellite (0.90) > drone (0.85) > river_sensor (0.70) should be the top 3.
    Each recommendation must have non-empty operational display text.
    """
    catalog = _make_catalog()
    recommendations = catalog.get_top_actions("incident_1", n=3)

    assert len(recommendations) == 3

    gains = [r.action.expected_information_gain for r in recommendations]
    assert gains == sorted(gains, reverse=True)

    assert recommendations[0].action.id == "request_satellite"
    assert recommendations[1].action.id == "task_drone"
    assert recommendations[2].action.id == "poll_river_sensor"

    for rec in recommendations:
        assert rec.display_text
        assert "Recommended information request:" in rec.display_text
        assert "within" in rec.display_text
        assert "minutes" in rec.display_text
        assert "Confirmation would" in rec.display_text


def test_dispatch_creates_task() -> None:
    """dispatch_action creates an OperationalTask row in the database."""
    catalog = _make_catalog()
    db = _FakeSession()

    result = catalog.dispatch_action(
        incident_id="incident_1",
        action_id="task_drone",
        db=db,
        org_id="org_1",
    )

    assert result.action_id == "task_drone"
    assert result.incident_id == "incident_1"
    assert result.task_id

    assert len(db.added) == 1
    task = db.added[0]
    assert task.id == result.task_id
    assert task.incident_id == "incident_1"
    assert task.org_id == "org_1"
    assert "Sensing:" in task.title
    assert task.properties["action_id"] == "task_drone"
    assert task.properties["sensing"] is True


def test_action_has_cost_gain_impact_fields() -> None:
    """Each catalog action has cost (time, resource, risk), expected gain, and impact."""
    catalog = _make_catalog()
    actions = catalog.get_actions()

    for action in actions:
        assert isinstance(action, CatalogAction)
        assert isinstance(action.cost, ActionCost)
        assert action.cost.time_minutes > 0
        assert action.cost.resource
        assert isinstance(action.cost.risk_level, RiskLevel)
        assert 0.0 <= action.expected_information_gain <= 1.0
        assert action.potential_impact_on_plan
        assert action.description
        assert action.target


def test_dispatch_requires_human_approval() -> None:
    """dispatch_action returns pending status — no autonomous dispatch.

    Sensing actions must NOT be dispatched autonomously. The task row is
    created with status="pending", requiring human approval before execution.
    """
    catalog = _make_catalog()
    db = _FakeSession()

    result = catalog.dispatch_action(
        incident_id="incident_1",
        action_id="request_satellite",
        db=db,
        org_id="org_1",
    )

    assert result.status == "pending"

    assert len(db.added) == 1
    task = db.added[0]
    assert task.status == "pending"
    assert task.properties["requires_approval"] is True
