"""Type definitions for the flood ensemble — EnsembleResult + ResNet50 S1 member.

The ensemble combines multiple flood mapping models (DOFA, ResNet50 with
SENTINEL1_GRD_MOCO weights, Copernicus GFM). ``EnsembleResult`` carries the
weighted-average flood probability, the per-pixel variance across members
(model disagreement), and the per-member probability maps so downstream
consumers can inspect the spread.

All outputs are PROBABILISTIC — ``flood_prob`` is a float tensor in [0, 1],
never a binary mask. Model disagreement is preserved as a separate output
layer; it is never collapsed into the probability or silently discarded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import torch
from torch import nn

from app.perception.flood_types import QualityFlag

logger = logging.getLogger(__name__)

_PATCH_SIZE = 224


@dataclass(frozen=True, slots=True)
class EnsembleResult:
    """Ensemble flood map result.

    ``flood_prob`` is the weighted average of member probabilities ([H, W],
    in [0, 1]). ``model_disagreement`` is the per-pixel variance across
    members ([H, W], >= 0) — high values flag zones where models disagree.
    ``member_probs`` is the stacked per-member probability tensor ([N, H, W]).
    ``weights`` is the weight vector used for the average ([N], sums to 1).
    """

    flood_prob: torch.Tensor
    model_disagreement: torch.Tensor
    member_probs: torch.Tensor
    weights: torch.Tensor
    observation_time: int
    quality_flag: QualityFlag


class _RandomEncoder(nn.Module):
    """Fallback encoder when ResNet50 S1 weights are unavailable."""

    out_features = 2048

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, _, H, W = x.shape
        return torch.randn(B, self.out_features, H // 32, W // 32)


class _ResNet50S1Segmentation(nn.Module):
    """ResNet50 (SENTINEL1_GRD_MOCO) encoder + lightweight segmentation head.

    Lazy-imports ``torchgeo.models.resnet50`` with
    ``ResNet50_Weights.SENTINEL1_GRD_MOCO`` inside ``__init__``. If torchgeo
    is unavailable or the weights API has changed, falls back to
    ``_RandomEncoder`` so the module still imports and tests can inject
    mocks. A Conv2d head maps encoder features to 2-class logits
    (background, water).
    """

    def __init__(self, pretrained: bool = True) -> None:
        super().__init__()
        self.encoder = self._load_resnet50(pretrained)
        enc_dim = getattr(self.encoder, "out_features", 2048)
        self.head = nn.Conv2d(enc_dim, 2, kernel_size=1)
        self.dropout = nn.Dropout(p=0.1)

    @staticmethod
    def _load_resnet50(pretrained: bool) -> nn.Module:
        """Lazy-import torchgeo.models and load ResNet50 S1 MOCO weights."""
        try:
            from torchgeo.models import ResNet50_Weights, resnet50

            weights = ResNet50_Weights.SENTINEL1_GRD_MOCO if pretrained else None
            return resnet50(weights=weights)
        except Exception:
            logger.warning("ResNet50 S1 MOCO unavailable, using random encoder")
            return _RandomEncoder()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.shape[1] == 2:
            x = x.repeat(1, 3, 1, 1)  # replicate VV, VH to 3 bands for ResNet
        feats = self.encoder(x)
        if feats.dim() == 3:
            B, N, C = feats.shape
            H = W = int(N ** 0.5)
            feats = feats.transpose(1, 2).reshape(B, C, H, W)
        return self.head(self.dropout(feats))


__all__ = ["EnsembleResult", "_RandomEncoder", "_ResNet50S1Segmentation"]
