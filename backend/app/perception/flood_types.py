"""Flood mapping result types — probabilistic flood maps from SAR imagery.

All outputs are PROBABILISTIC — ``flood_prob`` is a float tensor in [0, 1],
never a binary mask. Uncertainty comes from MC Dropout. Water depth is
estimated via the HAND (Height Above Nearest Drainage) method.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from torch import Tensor


class QualityFlag(str, enum.Enum):
    """Quality flag for a flood map observation."""

    high = "high"
    medium = "medium"
    low = "low"
    cloud_obscured = "cloud_obscured"
    no_data = "no_data"


@dataclass(frozen=True, slots=True)
class FloodMapResult:
    """Probabilistic flood map result.

    All tensor fields are [H, W]. ``flood_prob`` is in [0, 1].
    ``water_depth`` is in meters. ``uncertainty`` is the MC Dropout
    standard deviation. ``model_disagreement`` is |model_prob - gfm_prob|.
    ``change_from_previous`` is the delta from the prior observation.
    """

    flood_prob: Tensor
    water_depth: Tensor
    uncertainty: Tensor
    model_disagreement: Tensor
    observation_time: int
    quality_flag: QualityFlag
    change_from_previous: Tensor | None = None


__all__ = ["FloodMapResult", "QualityFlag"]
