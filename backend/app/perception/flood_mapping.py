"""SAR flood mapping pipeline — Sentinel-1 acquisition + DOFA inference.

Acquires Sentinel-1 SAR scenes from Copernicus Dataspace (via cdsetool),
loads them as [2, H, W] tensors (VV, VH bands), runs DOFA (Foundation
Model for Earth Observation) inference via TorchGeo, and produces
probabilistic flood maps with uncertainty estimates.

Outputs are PROBABILISTIC — ``flood_prob`` is a [H, W] float tensor in
[0, 1], never a binary mask. Uncertainty comes from MC Dropout. Water
depth is estimated via the HAND method when a DEM is provided.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Protocol

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from app.lib.time import now_ms
from app.perception.flood_types import FloodMapResult, QualityFlag

logger = logging.getLogger(__name__)

_PATCH_SIZE = 224
_GFM_ALPHA = 0.6  # model weight
_GFM_BETA = 0.4   # GFM weight


class _MinioLike(Protocol):
    """Structural type for the MinIO client methods we use."""

    def put_object(self, bucket: str, key: str, data: object, length: int) -> object: ...


class _DOFASegmentation(nn.Module):
    """DOFA encoder + lightweight segmentation head for flood mapping.

    The DOFA encoder is loaded from TorchGeo. A Conv2D head maps encoder
    features to 2-class logits (background, water). Lazy-imports
    ``torchgeo.models`` inside ``__init__``.
    """

    def __init__(self, pretrained: bool = True) -> None:
        super().__init__()
        self.encoder = self._load_dofa(pretrained)
        enc_dim = getattr(self.encoder, "embed_dim", 256)
        self.head = nn.Conv2d(enc_dim, 2, kernel_size=1)
        self.dropout = nn.Dropout(p=0.1)

    @staticmethod
    def _load_dofa(pretrained: bool) -> nn.Module:
        """Lazy-import torchgeo.models and load DOFA encoder."""
        if not pretrained:
            raise RuntimeError("DOFA requires a registered pretrained artifact")
        try:
            from torchgeo.models import dofa
            return dofa(pretrained=pretrained)  # type: ignore[operator]
        except (ImportError, OSError, RuntimeError) as exc:
            raise RuntimeError("DOFA weights unavailable") from exc

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[1] == 2:
            x = x.repeat(1, 3, 1, 1)  # replicate VV, VH to 3 bands
        feats = self.encoder(x)
        if feats.dim() == 3:
            # transformer output [B, N, C] -> [B, C, H, W]
            B, N, C = feats.shape
            H = W = int(N ** 0.5)
            feats = feats.transpose(1, 2).reshape(B, C, H, W)
        return self.head(self.dropout(feats))


class SARFloodMapper:
    """SAR-based flood mapping pipeline with probabilistic output.

    Acquires Sentinel-1 scenes, runs DOFA inference, and produces
    probabilistic flood maps with MC Dropout uncertainty. Optionally
    fuses with GFM (Global Flood Monitoring) product.
    """

    def __init__(
        self,
        model: nn.Module | None = None,
        minio_client: _MinioLike | None = None,
        cache_dir: str | None = None,
        minio_bucket: str = "flood-maps",
    ) -> None:
        self._model = model
        self._minio = minio_client
        self._cache_dir = cache_dir
        self._bucket = minio_bucket

    # ── Public API ──────────────────────────────────────────────────────

    def acquire_sentinel1(
        self,
        bbox: tuple[float, float, float, float],
        datetime_range: tuple[str, str],
    ) -> list[dict]:
        """Query Sentinel-1 scenes from Copernicus Dataspace via cdsetool."""
        try:
            from cdsetool import query
        except ImportError:
            logger.warning("cdsetool not installed, returning empty scene list")
            return []
        w, s, e, n = bbox
        start, end = datetime_range
        return list(query(
            "Sentinel-1",
            {"bbox": f"{w},{s},{e},{n}", "startDate": start, "endDate": end},
        ))

    def load_scene(self, scene_id: str) -> torch.Tensor:
        """Load a Sentinel-1 scene as [2, H, W] tensor (VV, VH bands)."""
        import rasterio

        with rasterio.open(scene_id) as src:
            vv = src.read(1).astype(np.float32)
            vh = src.read(2).astype(np.float32) if src.count >= 2 else vv.copy()
        return torch.stack([
            torch.from_numpy(vv),
            torch.from_numpy(vh),
        ], dim=0)

    def run_inference(
        self,
        tensor: torch.Tensor,
        dem: torch.Tensor | None = None,
        previous: FloodMapResult | None = None,
    ) -> FloodMapResult:
        """Run DOFA inference, return probabilistic flood map."""
        x = self._preprocess(tensor)
        model = self._get_model()

        was_training = model.training
        model.eval()
        try:
            with torch.no_grad():
                logits = model(x.unsqueeze(0))
                flood_prob = F.softmax(logits, dim=1)[0, 1]
        finally:
            model.train(was_training)

        uncertainty = self.compute_uncertainty(tensor)
        water_depth = self.estimate_water_depth(flood_prob, dem)
        change = flood_prob - previous.flood_prob if previous else None
        quality = self._assess_quality(uncertainty)

        return FloodMapResult(
            flood_prob=flood_prob,
            water_depth=water_depth,
            uncertainty=uncertainty,
            model_disagreement=torch.zeros_like(flood_prob),
            observation_time=now_ms(),
            quality_flag=quality,
            change_from_previous=change,
        )

    def compute_uncertainty(
        self,
        tensor: torch.Tensor,
        n_samples: int = 30,
    ) -> torch.Tensor:
        """MC Dropout uncertainty — std over n forward passes in train mode."""
        model = self._get_model()
        was_training = model.training
        model.train()
        try:
            x = self._preprocess(tensor).unsqueeze(0)
            samples: list[torch.Tensor] = []
            with torch.no_grad():
                for _ in range(n_samples):
                    logits = model(x)
                    samples.append(F.softmax(logits, dim=1)[0, 1])
        finally:
            model.train(was_training)
        return torch.stack(samples).std(dim=0)

    def estimate_water_depth(
        self,
        flood_prob: torch.Tensor,
        dem: torch.Tensor | None,
    ) -> torch.Tensor:
        """HAND method — water_depth = flood_prob * max(dem_max - dem, 0)."""
        if dem is None:
            return torch.zeros_like(flood_prob)
        dem_2d = dem.unsqueeze(0).unsqueeze(0)
        dem_max = F.max_pool2d(dem_2d, kernel_size=7, stride=1, padding=3)
        dem_max = dem_max.squeeze(0).squeeze(0)
        return flood_prob * torch.clamp(dem_max - dem, min=0)

    def save_as_cog(self, result: FloodMapResult, object_key: str) -> str:
        """Write flood probability map as COG to temp file, upload to MinIO."""
        import rasterio
        from rasterio.transform import from_bounds

        prob = result.flood_prob.detach().cpu().numpy().astype(np.float32)
        H, W = prob.shape
        tmp_path = os.path.join(
            tempfile.gettempdir(), f"{object_key.replace('/', '_')}.tif"
        )
        with rasterio.open(
            tmp_path, "w",
            driver="COG",
            height=H, width=W,
            count=1, dtype="float32",
            crs="EPSG:4326",
            transform=from_bounds(0, 0, 1, 1, W, H),
        ) as dst:
            dst.write(prob, 1)

        if self._minio is not None:
            size = os.path.getsize(tmp_path)
            with open(tmp_path, "rb") as f:
                self._minio.put_object(self._bucket, object_key, f, size)
            logger.info("uploaded COG to %s/%s", self._bucket, object_key)
        return tmp_path

    def fuse_with_gfm(
        self,
        model_output: FloodMapResult,
        gfm_product: dict,
    ) -> FloodMapResult:
        """Fuse model output with GFM product — weighted average."""
        gfm_data = gfm_product.get("flood_prob")
        provenance = gfm_product.get("provenance")
        if isinstance(gfm_data, (float, int)) or gfm_data is None:
            raise ValueError("GFM requires a real raster product, not a constant")
        if not isinstance(provenance, dict) or not provenance:
            raise ValueError("GFM raster product provenance is required")
        gfm_prob = torch.as_tensor(
            gfm_data, dtype=model_output.flood_prob.dtype
        )
        if gfm_prob.dim() == 0:
            gfm_prob = gfm_prob.expand_as(model_output.flood_prob)

        fused = _GFM_ALPHA * model_output.flood_prob + _GFM_BETA * gfm_prob
        disagreement = torch.abs(model_output.flood_prob - gfm_prob)

        return FloodMapResult(
            flood_prob=fused,
            water_depth=model_output.water_depth,
            uncertainty=model_output.uncertainty,
            model_disagreement=disagreement,
            observation_time=model_output.observation_time,
            quality_flag=model_output.quality_flag,
            change_from_previous=model_output.change_from_previous,
        )

    # ── Internals ────────────────────────────────────────────────────────

    def _preprocess(self, x: torch.Tensor) -> torch.Tensor:
        """Resize to 224x224 if needed."""
        if x.dim() == 2:
            x = x.unsqueeze(0).expand(2, *x.shape)
        if x.shape[-1] != _PATCH_SIZE or x.shape[-2] != _PATCH_SIZE:
            x = F.interpolate(
                x.unsqueeze(0), size=(_PATCH_SIZE, _PATCH_SIZE),
                mode="bilinear", align_corners=False,
            ).squeeze(0)
        return x

    def _get_model(self) -> nn.Module:
        if self._model is None:
            raise RuntimeError("SAR model weights unavailable")
        return self._model

    @staticmethod
    def _assess_quality(uncertainty: torch.Tensor) -> QualityFlag:
        mean_unc = float(uncertainty.mean())
        if mean_unc < 0.1:
            return QualityFlag.high
        if mean_unc < 0.25:
            return QualityFlag.medium
        return QualityFlag.low


__all__ = ["SARFloodMapper"]
