"""Building damage classification (xBD/xView2) + road passability (SpaceNet 8).

Classify buildings into {no_damage, minor, major, destroyed} from post-event
imagery. Compute per-vehicle-class road passability — a road can be passable
for a boat while unsafe for an ambulance. ML inference goes through
``ModelServing`` (T22); tests mock the model serving layer.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

# ─── Enums ─────────────────────────────────────────────────────────────────


class DamageClass(str, enum.Enum):
    """xBD/xView2 building damage classes."""

    no_damage = "no_damage"
    minor = "minor"
    major = "major"
    destroyed = "destroyed"


class VehicleClass(str, enum.Enum):
    """Vehicle classes for road passability assessment."""

    ambulance = "ambulance"
    fire_truck = "fire_truck"
    boat = "boat"
    high_clearance_vehicle = "high_clearance_vehicle"
    regular_vehicle = "regular_vehicle"


# ─── Result dataclasses ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BuildingDamageResult:
    """Building damage classification result with probability + uncertainty."""

    damage_class: DamageClass
    probability: float
    uncertainty: float
    class_probabilities: dict[str, float]
    model_version: str
    has_pre_event: bool
    feature_id: str | None = None
    geometry: dict | None = None


@dataclass(frozen=True, slots=True)
class RoadPassabilityResult:
    """Per-vehicle-class road passability result (SpaceNet 8 operational output)."""

    vehicle_class_passabilities: dict[str, float]
    traversal_speed: float
    failure_time: float | None
    last_confirmation: str
    alternate_routes: list[str]
    uncertainty: float
    feature_id: str | None = None
    geometry: dict | None = None


# ─── Vehicle-class factors ────────────────────────────────────────────────
# (flood_factor, damage_factor) per vehicle class.
# flood_factor: 0 = flood has no effect, 1 = flood fully blocks.
#   Negative means flood ENABLES passage (boat).
# damage_factor: 0 = damage has no effect, 1 = damage fully blocks.

_VEHICLE_FACTORS: dict[VehicleClass, tuple[float, float]] = {
    VehicleClass.ambulance: (0.90, 0.50),
    VehicleClass.fire_truck: (0.70, 0.60),
    VehicleClass.boat: (-1.0, 0.50),
    VehicleClass.high_clearance_vehicle: (0.50, 0.70),
    VehicleClass.regular_vehicle: (0.95, 0.90),
}

# Base traversal speeds by road class (m/s).
_BASE_SPEED: dict[str, float] = {
    "highway": 25.0,
    "primary": 20.0,
    "secondary": 15.0,
    "residential": 10.0,
    "service": 5.0,
}
_DEFAULT_SPEED = 12.0

# Passability thresholds for failure-time estimation.
_FAILURE_THRESHOLD = 0.3
_SAFE_THRESHOLD = 0.7


# ─── DamageAssessor ───────────────────────────────────────────────────────


class DamageAssessor:
    """Building damage classification + road passability assessment.

    Uses ``ModelServing`` (T22) for ONNX inference. Tests inject a mock
    object with a ``run_inference(model_id, input_data) -> dict`` method.
    """

    def __init__(
        self,
        model_serving: Any | None = None,
        model_id: str = "building-damage",
    ) -> None:
        self._model_serving = model_serving
        self._model_id = model_id

    # ── Building damage ──────────────────────────────────────────────

    def assess_building_damage(
        self,
        image_tensor: Any,
        pre_event_tensor: Any | None = None,
    ) -> BuildingDamageResult:
        """Classify building damage from post-event imagery.

        When ``pre_event_tensor`` is None, a single-post-event-image model
        is used and uncertainty is penalized.
        """
        input_data = self._prepare_damage_input(image_tensor, pre_event_tensor)

        if self._model_serving is not None:
            result = self._model_serving.run_inference(self._model_id, input_data)
            logits = np.asarray(result["outputs"]["damage_class"])
            model_version = result["model_version"]
        else:
            logits = np.array([[0.5, 0.5, 1.0, 0.5]])
            model_version = "heuristic:1.0.0"

        probs = self._softmax(logits[-1])
        class_probs = {
            c.value: float(probs[i]) for i, c in enumerate(DamageClass)
        }
        idx = int(np.argmax(probs))
        damage_class = list(DamageClass)[idx]
        probability = float(probs[idx])
        uncertainty = 1.0 - probability
        if pre_event_tensor is None:
            uncertainty = min(1.0, uncertainty + 0.1)

        return BuildingDamageResult(
            damage_class=damage_class,
            probability=probability,
            uncertainty=uncertainty,
            class_probabilities=class_probs,
            model_version=model_version,
            has_pre_event=pre_event_tensor is not None,
        )

    # ── Road passability ─────────────────────────────────────────────

    def assess_road_passability(
        self,
        road_segment: dict,
        flood_prob: float,
        damage_prob: float,
    ) -> RoadPassabilityResult:
        """Assess per-vehicle-class passability for a road segment.

        ``road_segment`` is a GeoJSON-like dict with ``id``, ``geometry``,
        and ``properties``. Flood/damage probs are attached to ``properties``
        so ``compute_vehicle_class_passability`` can read them.
        """
        props = road_segment.setdefault("properties", {})
        props["flood_prob"] = float(flood_prob)
        props["damage_prob"] = float(damage_prob)

        passabilities: dict[str, float] = {}
        for vc in VehicleClass:
            passabilities[vc.value] = self.compute_vehicle_class_passability(
                road_segment, vc
            )

        road_class = props.get("road_class", "residential")
        base_speed = _BASE_SPEED.get(road_class, _DEFAULT_SPEED)
        non_boat = [
            p for vc, p in passabilities.items()
            if vc != VehicleClass.boat.value
        ]
        min_pass = min(non_boat) if non_boat else 0.0
        traversal_speed = base_speed * min_pass

        worst = min(passabilities.values())
        if worst < _FAILURE_THRESHOLD:
            failure_time: float | None = 0.0
        elif worst > _SAFE_THRESHOLD:
            failure_time = None
        else:
            failure_time = worst * 3600.0

        probs_list = list(passabilities.values())
        mean_p = sum(probs_list) / len(probs_list)
        variance = sum((p - mean_p) ** 2 for p in probs_list) / len(probs_list)
        uncertainty = math.sqrt(variance)

        return RoadPassabilityResult(
            vehicle_class_passabilities=passabilities,
            traversal_speed=traversal_speed,
            failure_time=failure_time,
            last_confirmation=props.get("last_confirmation", "satellite_imagery"),
            alternate_routes=list(props.get("alternate_routes", [])),
            uncertainty=uncertainty,
            feature_id=road_segment.get("id"),
            geometry=road_segment.get("geometry"),
        )

    def compute_vehicle_class_passability(
        self,
        road_segment: dict,
        vehicle_class: VehicleClass | str,
    ) -> float:
        """P(passable) for a specific vehicle class on a road segment."""
        if isinstance(vehicle_class, str):
            vehicle_class = VehicleClass(vehicle_class)

        props = road_segment.get("properties", {})
        flood_prob = float(props.get("flood_prob", 0.0))
        damage_prob = float(props.get("damage_prob", 0.0))

        flood_factor, damage_factor = _VEHICLE_FACTORS[vehicle_class]

        if flood_factor < 0:
            p = flood_prob * (1.0 - damage_prob * damage_factor)
        else:
            p = (1.0 - flood_prob * flood_factor) * (
                1.0 - damage_prob * damage_factor
            )

        return max(0.0, min(1.0, p))

    # ── GeoJSON output ───────────────────────────────────────────────

    @staticmethod
    def to_geojson(
        results: list[BuildingDamageResult | RoadPassabilityResult],
    ) -> dict:
        """Serialize results as GeoJSON FeatureCollection with damage probability + uncertainty."""
        features: list[dict] = []
        for r in results:
            if isinstance(r, BuildingDamageResult):
                props: dict[str, Any] = {
                    "type": "building_damage",
                    "damage_class": r.damage_class.value,
                    "probability": r.probability,
                    "uncertainty": r.uncertainty,
                    "class_probabilities": r.class_probabilities,
                    "model_version": r.model_version,
                    "has_pre_event": r.has_pre_event,
                }
            elif isinstance(r, RoadPassabilityResult):
                props = {
                    "type": "road_passability",
                    "vehicle_class_passabilities": r.vehicle_class_passabilities,
                    "traversal_speed": r.traversal_speed,
                    "failure_time": r.failure_time,
                    "last_confirmation": r.last_confirmation,
                    "alternate_routes": r.alternate_routes,
                    "uncertainty": r.uncertainty,
                }
            else:
                continue
            features.append({
                "type": "Feature",
                "id": r.feature_id,
                "geometry": r.geometry,
                "properties": props,
            })
        return {"type": "FeatureCollection", "features": features}

    # ── Internals ─────────────────────────────────────────────────────

    def _prepare_damage_input(
        self,
        image_tensor: Any,
        pre_event_tensor: Any | None,
    ) -> dict[str, Any]:
        """Convert tensors to ONNX input dict."""
        post = self._to_numpy(image_tensor)
        if pre_event_tensor is not None:
            pre = self._to_numpy(pre_event_tensor)
            return {"post_image": post, "pre_image": pre}
        return {"post_image": post}

    @staticmethod
    def _to_numpy(tensor: Any) -> np.ndarray:
        """Convert torch tensor or numpy array to numpy, add batch dim if 3D."""
        if hasattr(tensor, "detach"):
            arr = tensor.detach().cpu().numpy()
        else:
            arr = np.asarray(tensor)
        if arr.ndim == 3:
            arr = arr[np.newaxis, ...]
        return arr

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        """Numerically stable softmax."""
        shifted = logits - np.max(logits)
        exp = np.exp(shifted)
        return exp / np.sum(exp)


__all__ = [
    "BuildingDamageResult",
    "DamageAssessor",
    "DamageClass",
    "RoadPassabilityResult",
    "VehicleClass",
]
