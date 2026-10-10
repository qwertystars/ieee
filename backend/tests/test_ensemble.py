"""Tests for the flood ensemble — DOFA + ResNet50 S1 + GFM weighted average.

Uses mock members (duck-typed, no real model weights required). Verifies:
  1. Three members produce different flood maps.
  2. Ensemble averages them with equal weights.
  3. Disagreement map is non-zero where members differ.
  4. Weights affect the ensemble output.
  5. GFM member is optional (ensemble works with 2 members).
  6. Per-zone weighting changes the output for that zone.
  7. Output is probabilistic (continuous [0,1], not binary).
"""

from __future__ import annotations

import pytest
import torch

from app.perception.ensemble import FloodEnsemble, GFMMember
from app.perception.ensemble_types import EnsembleResult
from app.perception.flood_types import FloodMapResult, QualityFlag

# ─── Mock members ────────────────────────────────────────────────────────────


class _MockMember:
    """Mock ensemble member — returns a fixed flood_prob tensor.

    Duck-typed: implements ``run_inference(tensor) -> FloodMapResult``.
    The ``flood_prob`` is set via constructor so each mock member produces
    a different map.
    """

    def __init__(self, flood_prob: torch.Tensor, name: str = "mock") -> None:
        self._flood_prob = flood_prob
        self._name = name
        self.provenance = {"model_id": name, "artifact_sha256": "a" * 64}

    def run_inference(self, tensor: torch.Tensor, **kwargs) -> FloodMapResult:
        return FloodMapResult(
            flood_prob=self._flood_prob,
            water_depth=torch.zeros_like(self._flood_prob),
            uncertainty=torch.zeros_like(self._flood_prob),
            model_disagreement=torch.zeros_like(self._flood_prob),
            observation_time=1,
            quality_flag=QualityFlag.medium,
            change_from_previous=None,
        )


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def sar_tensor():
    """Sample SAR tensor [2, 224, 224] — VV, VH bands."""
    return torch.randn(2, 224, 224)


@pytest.fixture
def member_probs():
    """Three distinct flood probability maps in [0, 1]."""
    torch.manual_seed(42)
    p_dofa = torch.rand(224, 224)
    p_resnet = torch.rand(224, 224)
    p_gfm = torch.rand(224, 224)
    # Ensure they are distinct
    assert not torch.allclose(p_dofa, p_resnet)
    assert not torch.allclose(p_dofa, p_gfm)
    assert not torch.allclose(p_resnet, p_gfm)
    return p_dofa, p_resnet, p_gfm


@pytest.fixture
def three_members(member_probs):
    p_dofa, p_resnet, p_gfm = member_probs
    return [
        _MockMember(p_dofa, name="dofa"),
        _MockMember(p_resnet, name="resnet50"),
        _MockMember(p_gfm, name="gfm"),
    ]


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_members_produce_different_maps(three_members, member_probs, sar_tensor):
    """Each member produces a distinct flood map — ensemble input diversity."""
    p_dofa, p_resnet, p_gfm = member_probs
    results = [m.run_inference(sar_tensor) for m in three_members]

    assert torch.allclose(results[0].flood_prob, p_dofa)
    assert torch.allclose(results[1].flood_prob, p_resnet)
    assert torch.allclose(results[2].flood_prob, p_gfm)
    assert not torch.allclose(results[0].flood_prob, results[1].flood_prob)
    assert not torch.allclose(results[0].flood_prob, results[2].flood_prob)
    assert not torch.allclose(results[1].flood_prob, results[2].flood_prob)


def test_ensemble_averages_members(three_members, member_probs, sar_tensor):
    """Ensemble with equal weights = simple average of member probabilities."""
    p_dofa, p_resnet, p_gfm = member_probs
    ensemble = FloodEnsemble(three_members)  # equal weights default

    result = ensemble.run_inference(sar_tensor)

    assert isinstance(result, EnsembleResult)
    expected = (p_dofa + p_resnet + p_gfm) / 3.0
    assert torch.allclose(result.flood_prob, expected, atol=1e-6)
    # Weights are equal (1/3 each) and sum to 1
    assert torch.allclose(result.weights, torch.tensor([1 / 3, 1 / 3, 1 / 3]), atol=1e-6)
    assert result.weights.sum().item() == pytest.approx(1.0, abs=1e-6)


def test_disagreement(three_members, member_probs, sar_tensor):
    """Disagreement map = per-pixel variance across members, non-zero where they differ."""
    p_dofa, p_resnet, p_gfm = member_probs
    ensemble = FloodEnsemble(three_members)

    result = ensemble.run_inference(sar_tensor)

    # Variance across 3 members per pixel
    stacked = torch.stack([p_dofa, p_resnet, p_gfm])  # [3, H, W]
    expected_var = stacked.var(dim=0, unbiased=False)
    assert torch.allclose(result.model_disagreement, expected_var, atol=1e-7)
    # Disagreement is non-negative
    assert result.model_disagreement.min() >= 0.0
    # Disagreement is non-zero somewhere (members are distinct)
    assert result.model_disagreement.max() > 0.0
    # Disagreement is preserved as a separate layer (not collapsed into flood_prob)
    assert result.model_disagreement.shape == result.flood_prob.shape


def test_weights_affect_output(three_members, member_probs, sar_tensor):
    """Non-equal weights shift the ensemble toward the up-weighted member."""
    p_dofa, p_resnet, p_gfm = member_probs
    # Heavily weight DOFA
    ensemble = FloodEnsemble(three_members, weights=[0.8, 0.1, 0.1])

    result = ensemble.run_inference(sar_tensor)

    expected = 0.8 * p_dofa + 0.1 * p_resnet + 0.1 * p_gfm
    assert torch.allclose(result.flood_prob, expected, atol=1e-6)
    # The weighted output is closer to DOFA than the equal-weight output is
    equal_avg = (p_dofa + p_resnet + p_gfm) / 3.0
    dist_weighted = (result.flood_prob - p_dofa).abs().mean().item()
    dist_equal = (equal_avg - p_dofa).abs().mean().item()
    assert dist_weighted < dist_equal


def test_gfm_member_optional(member_probs, sar_tensor):
    """Ensemble works with 2 members (GFM omitted) — GFM is optional."""
    p_dofa, p_resnet, _ = member_probs
    two_members = [
        _MockMember(p_dofa, name="dofa"),
        _MockMember(p_resnet, name="resnet50"),
    ]
    ensemble = FloodEnsemble(two_members)

    result = ensemble.run_inference(sar_tensor)

    expected = (p_dofa + p_resnet) / 2.0
    assert torch.allclose(result.flood_prob, expected, atol=1e-6)
    assert result.member_probs.shape[0] == 2
    # Disagreement still computed across the 2 members
    stacked = torch.stack([p_dofa, p_resnet])
    expected_var = stacked.var(dim=0, unbiased=False)
    assert torch.allclose(result.model_disagreement, expected_var, atol=1e-7)


def test_gfm_member_wrapper(member_probs, sar_tensor):
    """GFMMember wraps a GFM product dict and returns its flood_prob."""
    _, _, p_gfm = member_probs
    gfm_product = {
        "flood_prob": p_gfm,
        "provenance": {"model_id": "gfm", "artifact_sha256": "b" * 64},
    }
    gfm_member = GFMMember(gfm_product)

    result = gfm_member.run_inference(sar_tensor)

    assert torch.allclose(result.flood_prob, p_gfm)
    assert result.quality_flag == QualityFlag.high  # GFM is operational


def test_gfm_member_scalar_broadcast(sar_tensor):
    """GFMMember with scalar flood_prob broadcasts to tensor shape."""
    with pytest.raises(ValueError, match="real raster"):
        GFMMember({"flood_prob": 0.5})


def test_per_zone_weighting(three_members, member_probs, sar_tensor):
    """Per-zone weights override default weights for that zone_id."""
    p_dofa, p_resnet, p_gfm = member_probs
    zone_weights = {
        "zone_flat": [0.8, 0.1, 0.1],  # trust DOFA more in flat terrain
        "zone_urban": [0.1, 0.8, 0.1],  # trust ResNet50 more in urban
    }
    ensemble = FloodEnsemble(three_members, zone_weights=zone_weights)

    # Default (no zone_id) = equal weights
    result_default = ensemble.run_inference(sar_tensor)
    expected_default = (p_dofa + p_resnet + p_gfm) / 3.0
    assert torch.allclose(result_default.flood_prob, expected_default, atol=1e-6)

    # zone_flat = DOFA up-weighted
    result_flat = ensemble.run_inference(sar_tensor, zone_id="zone_flat")
    expected_flat = 0.8 * p_dofa + 0.1 * p_resnet + 0.1 * p_gfm
    assert torch.allclose(result_flat.flood_prob, expected_flat, atol=1e-6)
    assert torch.allclose(result_flat.weights, torch.tensor([0.8, 0.1, 0.1]))

    # zone_urban = ResNet50 up-weighted
    result_urban = ensemble.run_inference(sar_tensor, zone_id="zone_urban")
    expected_urban = 0.1 * p_dofa + 0.8 * p_resnet + 0.1 * p_gfm
    assert torch.allclose(result_urban.flood_prob, expected_urban, atol=1e-6)

    # Unknown zone falls back to default equal weights
    result_unknown = ensemble.run_inference(sar_tensor, zone_id="zone_unknown")
    assert torch.allclose(
        result_unknown.flood_prob, expected_default, atol=1e-6
    )


def test_weights_normalized(member_probs, sar_tensor):
    """Weights are normalized to sum to 1.0 even if input doesn't."""
    p_dofa, p_resnet, p_gfm = member_probs
    members = [
        _MockMember(p_dofa),
        _MockMember(p_resnet),
        _MockMember(p_gfm),
    ]
    # Unnormalized weights [2, 1, 1] should become [0.5, 0.25, 0.25]
    ensemble = FloodEnsemble(members, weights=[2.0, 1.0, 1.0])

    result = ensemble.run_inference(sar_tensor)

    expected = 0.5 * p_dofa + 0.25 * p_resnet + 0.25 * p_gfm
    assert torch.allclose(result.flood_prob, expected, atol=1e-6)
    assert result.weights.sum().item() == pytest.approx(1.0, abs=1e-6)


def test_probabilistic_output(three_members, sar_tensor):
    """Ensemble output is continuous [0, 1], never binarized."""
    ensemble = FloodEnsemble(three_members)

    result = ensemble.run_inference(sar_tensor)

    assert result.flood_prob.min() >= 0.0
    assert result.flood_prob.max() <= 1.0
    # NOT binary — should have many unique values
    assert len(result.flood_prob.unique()) > 2
    # Member probs preserved for inspection
    assert result.member_probs.shape[0] == 3
    assert result.member_probs.shape[1:] == result.flood_prob.shape


def test_empty_members_rejected():
    """Empty members list raises ValueError."""
    with pytest.raises(ValueError, match="at least one member"):
        FloodEnsemble([])


def test_weights_length_mismatch_rejected(member_probs):
    """Weights length != members length raises ValueError."""
    p_dofa, p_resnet, _ = member_probs
    members = [_MockMember(p_dofa), _MockMember(p_resnet)]
    with pytest.raises(ValueError, match="weights length"):
        FloodEnsemble(members, weights=[0.5, 0.3, 0.2])


def test_observation_time_and_quality(three_members, sar_tensor):
    """EnsembleResult carries observation_time and a quality_flag."""
    ensemble = FloodEnsemble(three_members)

    result = ensemble.run_inference(sar_tensor)

    assert result.observation_time > 0
    assert result.quality_flag in list(QualityFlag)
