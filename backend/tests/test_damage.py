"""Tests for building damage classification + road passability assessment.

Uses fixture image tensors (torch.randn) and a mock model serving layer —
no real imagery or ML model weights required. All tests are pure unit tests
with no DB, MinIO, or Redpanda dependencies.

Verification command:
    docker compose run --rm -e PYTHONPATH=/app backend sh -c \
        "pip install pytest -q && python -m pytest tests/test_damage.py -q"
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
import torch

from app.perception.damage import (
    BuildingDamageResult,
    DamageAssessor,
    DamageClass,
    RoadPassabilityResult,
    VehicleClass,
)

ORG_ID = "org_test_damage"


# ─── Mock model serving ───────────────────────────────────────────────────


class _MockModelServing:
    """Mock ModelServing — returns fixed logits favoring 'major' damage.

    Logits [0.5, 1.0, 3.0, 0.5] softmax to ~[0.06, 0.10, 0.77, 0.06],
    so the predicted class is 'major' with probability ~0.77.
    """

    def __init__(self, logits: tuple = (0.5, 1.0, 3.0, 0.5)) -> None:
        self._logits = np.array([logits], dtype=np.float32)
        self.calls: list[tuple[str, dict]] = []

    def run_inference(
        self, model_id: str, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((model_id, input_data))
        return {
            "outputs": {"damage_class": self._logits},
            "model_version": "building-damage:1.0.0",
        }


# ─── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_serving() -> _MockModelServing:
    return _MockModelServing()


@pytest.fixture
def assessor(mock_serving: _MockModelServing) -> DamageAssessor:
    return DamageAssessor(model_serving=mock_serving, model_id="building-damage")


@pytest.fixture
def image_tensor() -> torch.Tensor:
    """Fixture post-event image tensor (3, 256, 256)."""
    return torch.randn(3, 256, 256)


@pytest.fixture
def pre_event_tensor() -> torch.Tensor:
    """Fixture pre-event image tensor (3, 256, 256)."""
    return torch.randn(3, 256, 256)


@pytest.fixture
def flooded_road() -> dict:
    """A flooded road segment — high flood, low damage."""
    return {
        "id": "road_001",
        "geometry": {
            "type": "LineString",
            "coordinates": [[0.0, 0.0], [1.0, 1.0]],
        },
        "properties": {
            "road_class": "residential",
            "last_confirmation": "satellite_imagery",
            "alternate_routes": ["road_002", "road_003"],
        },
    }


# ─── Tests ─────────────────────────────────────────────────────────────────


def test_building_damage_classification(
    assessor: DamageAssessor,
    image_tensor: torch.Tensor,
    mock_serving: _MockModelServing,
):
    """Fixture image → damage class + probability.

    Given: a post-event image tensor and a mock model that returns logits
           favoring 'major' damage.
    When:  assess_building_damage is called.
    Then:  the result has damage_class=major, probability > 0.5, and
           model_version from the mock.
    """
    result = assessor.assess_building_damage(image_tensor)

    assert isinstance(result, BuildingDamageResult)
    assert result.damage_class == DamageClass.major
    assert result.probability > 0.5
    assert result.model_version == "building-damage:1.0.0"
    assert len(mock_serving.calls) == 1
    assert mock_serving.calls[0][0] == "building-damage"
    # All 4 class probabilities present and sum to ~1.0.
    assert len(result.class_probabilities) == 4
    total = sum(result.class_probabilities.values())
    assert total == pytest.approx(1.0, abs=1e-5)


def test_vehicle_class_passability(
    assessor: DamageAssessor, flooded_road: dict
):
    """Flooded road: ambulance P≈0.2 (low), boat P≈0.9 (high).

    Given: a road with flood_prob=0.9, damage_prob=0.1.
    When:  assess_road_passability is called.
    Then:  ambulance passability < 0.3 (blocked by flood),
           boat passability > 0.8 (flood enables boat passage).
    """
    result = assessor.assess_road_passability(
        flooded_road, flood_prob=0.9, damage_prob=0.1
    )

    assert isinstance(result, RoadPassabilityResult)
    amb = result.vehicle_class_passabilities["ambulance"]
    boat = result.vehicle_class_passabilities["boat"]

    # Ambulance: (1 - 0.9*0.9) * (1 - 0.1*0.5) = 0.19 * 0.95 ≈ 0.18
    assert amb < 0.3
    # Boat: 0.9 * (1 - 0.1*0.5) = 0.9 * 0.95 ≈ 0.86
    assert boat > 0.8
    # Boat is more passable than ambulance on a flooded road.
    assert boat > amb


def test_road_passability_differs_by_class(
    assessor: DamageAssessor, flooded_road: dict
):
    """Different vehicle classes get different P(passable).

    Given: a road with moderate flood and damage.
    When:  assess_road_passability is called.
    Then:  at least 3 distinct passability values across 5 vehicle classes,
           and boat differs from all non-boat classes.
    """
    result = assessor.assess_road_passability(
        flooded_road, flood_prob=0.7, damage_prob=0.2
    )

    passabilities = result.vehicle_class_passabilities
    assert len(passabilities) == 5

    # All 5 vehicle classes present.
    for vc in VehicleClass:
        assert vc.value in passabilities
        assert 0.0 <= passabilities[vc.value] <= 1.0

    # At least 3 distinct values — classes are differentiated.
    distinct = {round(p, 4) for p in passabilities.values()}
    assert len(distinct) >= 3

    # Boat differs from ambulance and regular_vehicle.
    assert passabilities["boat"] != passabilities["ambulance"]
    assert passabilities["boat"] != passabilities["regular_vehicle"]

    # Direct call to compute_vehicle_class_passability matches.
    direct = assessor.compute_vehicle_class_passability(
        flooded_road, VehicleClass.ambulance
    )
    assert direct == pytest.approx(passabilities["ambulance"], abs=1e-6)


def test_geojson_output(
    assessor: DamageAssessor,
    image_tensor: torch.Tensor,
    flooded_road: dict,
):
    """Results serialized as GeoJSON FeatureCollection with damage probability.

    Given: a BuildingDamageResult and a RoadPassabilityResult.
    When:  to_geojson is called with both.
    Then:  output is a valid GeoJSON FeatureCollection with 2 features,
           each carrying probability + uncertainty in properties.
    """
    building_result = assessor.assess_building_damage(image_tensor)
    road_result = assessor.assess_road_passability(
        flooded_road, flood_prob=0.8, damage_prob=0.2
    )

    geojson = DamageAssessor.to_geojson([building_result, road_result])

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2

    # Building feature.
    bf = geojson["features"][0]
    assert bf["type"] == "Feature"
    assert bf["properties"]["type"] == "building_damage"
    assert bf["properties"]["damage_class"] == "major"
    assert "probability" in bf["properties"]
    assert "uncertainty" in bf["properties"]
    assert "class_probabilities" in bf["properties"]
    assert bf["properties"]["probability"] > 0.5

    # Road feature.
    rf = geojson["features"][1]
    assert rf["type"] == "Feature"
    assert rf["properties"]["type"] == "road_passability"
    assert "vehicle_class_passabilities" in rf["properties"]
    assert "traversal_speed" in rf["properties"]
    assert "uncertainty" in rf["properties"]
    assert rf["properties"]["vehicle_class_passabilities"]["boat"] > 0.5
    assert rf["id"] == "road_001"
    assert rf["geometry"]["type"] == "LineString"


def test_uncertainty(
    assessor: DamageAssessor,
    image_tensor: torch.Tensor,
    pre_event_tensor: torch.Tensor,
):
    """Damage assessment includes uncertainty; higher without pre-event imagery.

    Given: a post-event image with and without pre-event imagery.
    When:  assess_building_damage is called both ways.
    Then:  uncertainty is in [0, 1] for both, and uncertainty is higher
           when pre-event imagery is missing (less context for change detection).
    """
    result_with_pre = assessor.assess_building_damage(
        image_tensor, pre_event_tensor=pre_event_tensor
    )
    result_without_pre = assessor.assess_building_damage(image_tensor)

    # Uncertainty is present and valid.
    assert 0.0 <= result_with_pre.uncertainty <= 1.0
    assert 0.0 <= result_without_pre.uncertainty <= 1.0

    # Uncertainty is higher without pre-event imagery.
    assert result_without_pre.uncertainty > result_with_pre.uncertainty

    # has_pre_event flag is correct.
    assert result_with_pre.has_pre_event is True
    assert result_without_pre.has_pre_event is False

    # Uncertainty = 1 - probability (plus penalty if no pre-event).
    assert result_with_pre.uncertainty == pytest.approx(
        1.0 - result_with_pre.probability, abs=1e-6
    )
    assert result_without_pre.uncertainty == pytest.approx(
        1.0 - result_without_pre.probability + 0.1, abs=1e-6
    )


def test_road_passability_failure_time_and_speed(
    assessor: DamageAssessor, flooded_road: dict
):
    """Road passability includes traversal speed, failure time, alternates.

    Given: a severely flooded road (flood=0.95, damage=0.3).
    When:  assess_road_passability is called.
    Then:  traversal_speed is reduced from base, failure_time is 0 (already
           failed for some vehicle class), and alternate_routes are carried.
    """
    result = assessor.assess_road_passability(
        flooded_road, flood_prob=0.95, damage_prob=0.3
    )

    # Traversal speed is reduced (base residential = 10 m/s * min_pass).
    assert result.traversal_speed < 10.0
    assert result.traversal_speed >= 0.0

    # At least one vehicle class is below failure threshold → failure_time=0.
    min_pass = min(result.vehicle_class_passabilities.values())
    if min_pass < 0.3:
        assert result.failure_time == 0.0
    else:
        assert result.failure_time is not None

    # Alternate routes and last confirmation are carried from road_segment.
    assert result.alternate_routes == ["road_002", "road_003"]
    assert result.last_confirmation == "satellite_imagery"

    # Uncertainty is present and valid.
    assert 0.0 <= result.uncertainty <= 1.0
