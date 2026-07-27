"""Foundation model ensemble for flood mapping — DOFA + ResNet50 S1 + GFM.

Combines multiple flood mapping models into a weighted ensemble. The ensemble
output is the per-pixel weighted average of member probabilities. Model
disagreement (per-pixel variance across members) is preserved as a separate
output layer so downstream consumers can flag high-disagreement zones.

Members are duck-typed: any object with ``run_inference(tensor) -> FloodMapResult``
works. ``ResNet50S1Mapper`` and ``GFMMember`` are provided as convenience
members; ``SARFloodMapper`` (DOFA) from ``flood_mapping.py`` is the third
default member. Tests inject mock members directly — no real weights needed.

Per-zone weighting: pass ``zone_weights`` mapping zone_id -> weight list to
up/down-weight members per H3 zone based on calibration performance (T17).
Default is equal weights.

All outputs are PROBABILISTIC — ``flood_prob`` is in [0, 1], never binarized.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import torch
import torch.nn.functional as F
from torch import nn

from app.lib.time import now_ms
from app.perception.ensemble_types import _ResNet50S1Segmentation
from app.perception.flood_types import FloodMapResult, QualityFlag

logger = logging.getLogger(__name__)

_PATCH_SIZE = 224


class _FloodMemberLike(Protocol):
    """Structural type for ensemble members."""

    def run_inference(
        self,
        tensor: torch.Tensor,
        dem: torch.Tensor | None = None,
        previous: FloodMapResult | None = None,
    ) -> FloodMapResult: ...


class ResNet50S1Mapper:
    """SAR flood mapping via ResNet50 (SENTINEL1_GRD_MOCO) + segmentation head.

    Same duck-typed interface as ``SARFloodMapper`` — ``run_inference(tensor)
    -> FloodMapResult`` — so it can be injected as an ensemble member. The
    encoder is lazy-loaded on first use; falls back to ``_RandomEncoder``
    when torchgeo weights are unavailable.
    """

    def __init__(self, model: nn.Module | None = None) -> None:
        self._model = model

    def run_inference(
        self,
        tensor: torch.Tensor,
        dem: torch.Tensor | None = None,
        previous: FloodMapResult | None = None,
    ) -> FloodMapResult:
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
        return FloodMapResult(
            flood_prob=flood_prob,
            water_depth=torch.zeros_like(flood_prob),
            uncertainty=torch.zeros_like(flood_prob),
            model_disagreement=torch.zeros_like(flood_prob),
            observation_time=now_ms(),
            quality_flag=QualityFlag.medium,
            change_from_previous=None,
        )

    def _get_model(self) -> nn.Module:
        if self._model is None:
            self._model = _ResNet50S1Segmentation(pretrained=False)
        return self._model

    @staticmethod
    def _preprocess(x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 2:
            x = x.unsqueeze(0).expand(2, *x.shape)
        if x.shape[-1] != _PATCH_SIZE or x.shape[-2] != _PATCH_SIZE:
            x = F.interpolate(
                x.unsqueeze(0), size=(_PATCH_SIZE, _PATCH_SIZE),
                mode="bilinear", align_corners=False,
            ).squeeze(0)
        return x


class GFMMember:
    """Copernicus GFM operational product as an ensemble member.

    GFM is an external operational product (not a model that runs on the
    input tensor). ``run_inference`` ignores the input tensor and returns
    the stored flood probability map. The product dict must contain
    ``flood_prob`` (tensor or scalar in [0, 1]).
    """

    def __init__(self, gfm_product: dict) -> None:
        self._product = gfm_product

    def run_inference(
        self,
        tensor: torch.Tensor,
        dem: torch.Tensor | None = None,
        previous: FloodMapResult | None = None,
    ) -> FloodMapResult:
        gfm_data = self._product.get("flood_prob", 0.0)
        gfm_prob = torch.as_tensor(gfm_data, dtype=torch.float32)
        if gfm_prob.dim() == 0:
            H, W = tensor.shape[-2], tensor.shape[-1]
            gfm_prob = gfm_prob.expand(H, W)
        return FloodMapResult(
            flood_prob=gfm_prob,
            water_depth=torch.zeros_like(gfm_prob),
            uncertainty=torch.zeros_like(gfm_prob),
            model_disagreement=torch.zeros_like(gfm_prob),
            observation_time=now_ms(),
            quality_flag=QualityFlag.high,
            change_from_previous=None,
        )


class FloodEnsemble:
    """Weighted ensemble of flood mapping models with disagreement tracking.

    Members are duck-typed: any object with ``run_inference(tensor) ->
    FloodMapResult`` works. The ensemble:

    1. Runs each member on the input tensor.
    2. Stacks per-member flood probabilities into [N, H, W].
    3. Computes weighted average: ``ensemble_prob = Σ w_i * p_i``.
    4. Computes per-pixel variance across members as ``model_disagreement``.

    Weights default to equal (1/N each). Pass ``zone_weights`` to up/down-weight
    members per H3 zone based on calibration performance (T17). Weights are
    normalized to sum to 1.0 at inference time.

    Model disagreement is NEVER hidden — it is preserved as a separate
    output layer in ``EnsembleResult.model_disagreement``. No single model
    solves flood mapping universally; the ensemble preserves the spread.
    """

    def __init__(
        self,
        members: list[_FloodMemberLike],
        weights: list[float] | None = None,
        zone_weights: dict[str, list[float]] | None = None,
    ) -> None:
        if not members:
            raise ValueError("FloodEnsemble requires at least one member")
        self._members = list(members)
        n = len(self._members)
        if weights is None:
            self._default_weights = [1.0 / n] * n
        else:
            if len(weights) != n:
                raise ValueError(
                    f"weights length {len(weights)} != members length {n}"
                )
            self._default_weights = list(weights)
        self._zone_weights = dict(zone_weights or {})

    def run_inference(
        self,
        tensor: torch.Tensor,
        zone_id: str | None = None,
    ) -> Any:
        from app.perception.ensemble_types import EnsembleResult

        weights = self._resolve_weights(zone_id)
        member_results = [m.run_inference(tensor) for m in self._members]
        member_probs = torch.stack([r.flood_prob for r in member_results])  # [N, H, W]

        w_tensor = torch.tensor(
            weights, dtype=member_probs.dtype, device=member_probs.device
        ).view(-1, 1, 1)
        ensemble_prob = (w_tensor * member_probs).sum(dim=0)  # [H, W]
        disagreement = member_probs.var(dim=0, unbiased=False)  # [H, W]

        return EnsembleResult(
            flood_prob=ensemble_prob,
            model_disagreement=disagreement,
            member_probs=member_probs,
            weights=torch.tensor(weights),
            observation_time=now_ms(),
            quality_flag=self._assess_quality(float(disagreement.mean())),
        )

    def _resolve_weights(self, zone_id: str | None) -> list[float]:
        if zone_id is not None and zone_id in self._zone_weights:
            raw = self._zone_weights[zone_id]
        else:
            raw = self._default_weights
        return self._normalize(raw)

    @staticmethod
    def _normalize(weights: list[float]) -> list[float]:
        total = sum(weights)
        if total <= 0:
            n = len(weights)
            return [1.0 / n] * n
        return [w / total for w in weights]

    @staticmethod
    def _assess_quality(mean_disagreement: float) -> QualityFlag:
        if mean_disagreement < 0.01:
            return QualityFlag.high
        if mean_disagreement < 0.05:
            return QualityFlag.medium
        return QualityFlag.low


__all__ = ["FloodEnsemble", "GFMMember", "ResNet50S1Mapper"]
