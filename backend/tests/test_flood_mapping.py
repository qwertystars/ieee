"""Tests for SAR flood mapping pipeline — DOFA inference, uncertainty, COG.

Uses a mock DOFA model with dropout (no real weights required) and a mock
MinIO client that records put_object calls. No real satellite data needed.
"""

from __future__ import annotations

import os

import pytest
import torch
from torch import nn

from app.perception.flood_mapping import SARFloodMapper
from app.perception.flood_types import FloodMapResult, QualityFlag

# ─── Mocks ──────────────────────────────────────────────────────────────────


class _MockDOFA(nn.Module):
    """Mock DOFA model with dropout for MC Dropout uncertainty testing."""

    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(2, 2, kernel_size=3, padding=1)
        self.dropout = nn.Dropout(p=0.5)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.dropout(self.conv(x))


class _MockMinio:
    """Mock MinIO client — records put_object calls."""

    def __init__(self) -> None:
        self.put_object_calls: list[tuple[str, str, int]] = []

    def put_object(self, bucket: str, key: str, data, length: int) -> None:
        self.put_object_calls.append((bucket, key, length))


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def model():
    return _MockDOFA()


@pytest.fixture
def minio_client():
    return _MockMinio()


@pytest.fixture
def mapper(model, minio_client):
    return SARFloodMapper(model=model, minio_client=minio_client)


@pytest.fixture
def sar_tensor():
    """Sample SAR tensor [2, 224, 224] — VV, VH bands."""
    return torch.randn(2, 224, 224)


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_inference(mapper, sar_tensor):
    """run_inference returns FloodMapResult with [224,224] prob in [0,1]."""
    result = mapper.run_inference(sar_tensor)

    assert isinstance(result, FloodMapResult)
    assert result.flood_prob.shape == (224, 224)
    assert result.water_depth.shape == (224, 224)
    assert result.uncertainty.shape == (224, 224)
    assert result.model_disagreement.shape == (224, 224)
    assert result.observation_time > 0
    assert result.quality_flag in list(QualityFlag)
    assert result.flood_prob.min() >= 0.0
    assert result.flood_prob.max() <= 1.0
    # NOT binary — should have continuous values
    assert len(result.flood_prob.unique()) > 2


def test_uncertainty(mapper, sar_tensor):
    """MC Dropout uncertainty is non-negative and [224,224]."""
    uncertainty = mapper.compute_uncertainty(sar_tensor, n_samples=10)

    assert uncertainty.shape == (224, 224)
    assert uncertainty.min() >= 0.0
    assert uncertainty.mean() > 0.0


def test_water_depth(mapper, sar_tensor):
    """HAND method — water_depth = flood_prob * max(dem_max - dem, 0)."""
    flood_prob = torch.rand(224, 224)
    dem = torch.rand(224, 224) * 10

    depth = mapper.estimate_water_depth(flood_prob, dem)

    assert depth.shape == (224, 224)
    assert depth.min() >= 0.0
    assert depth.max() <= flood_prob.max() * 10.0

    # Without DEM, depth should be zeros
    depth_no_dem = mapper.estimate_water_depth(flood_prob, None)
    assert torch.all(depth_no_dem == 0.0)


def test_cog_output(mapper, minio_client, sar_tensor):
    """save_as_cog writes COG file and uploads to MinIO."""
    result = mapper.run_inference(sar_tensor)
    object_key = "flood-map-2024-01-01.tif"

    path = mapper.save_as_cog(result, object_key)

    assert os.path.exists(path)
    assert path.endswith(".tif")
    assert len(minio_client.put_object_calls) == 1
    bucket, key, length = minio_client.put_object_calls[0]
    assert bucket == "flood-maps"
    assert key == object_key
    assert length > 0


def test_gfm_fusion(mapper, sar_tensor):
    """fuse_with_gfm produces weighted average and disagreement."""
    result = mapper.run_inference(sar_tensor)
    gfm_prob = torch.rand(224, 224)
    gfm_product = {
        "flood_prob": gfm_prob,
        "provenance": {"model_id": "gfm", "artifact_sha256": "b" * 64},
    }

    fused = mapper.fuse_with_gfm(result, gfm_product)

    assert fused.flood_prob.shape == (224, 224)
    expected = 0.6 * result.flood_prob + 0.4 * gfm_prob
    assert torch.allclose(fused.flood_prob, expected, atol=1e-5)
    expected_disagree = torch.abs(result.flood_prob - gfm_prob)
    assert torch.allclose(fused.model_disagreement, expected_disagree, atol=1e-5)
