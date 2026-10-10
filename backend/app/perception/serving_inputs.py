"""Validated raster input preparation for registered inference."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.perception.serving_contracts import ContractState


@dataclass(frozen=True, slots=True)
class RasterInputMetadata:
    """Validated spatial metadata and quality measurements for raster input."""

    crs: str
    resolution_m: float
    valid_fraction: float
    nodata_fraction: float
    snr_db: float


@dataclass(frozen=True, slots=True)
class PreparedRasterInput:
    """Validated raster tensor and its contract-level disposition."""

    state: ContractState
    tensor: np.ndarray | None
    reason: str


def prepare_raster_input(
    tensor: np.ndarray,
    metadata: RasterInputMetadata,
    expected_shape: tuple[int, ...],
) -> PreparedRasterInput:
    """Validate shape, spatial metadata, finite values, and quality."""
    if tuple(tensor.shape) != expected_shape:
        return PreparedRasterInput(ContractState.incompatible, None, "input_shape_mismatch")
    if not np.isfinite(tensor).all():
        return PreparedRasterInput(ContractState.incompatible, None, "input_non_finite")
    crs_parts = metadata.crs.upper().split(":")
    if len(crs_parts) != 2 or crs_parts[0] != "EPSG" or not crs_parts[1].isdigit():
        return PreparedRasterInput(ContractState.incompatible, None, "input_crs_invalid")
    if not np.isfinite(metadata.resolution_m) or metadata.resolution_m <= 0:
        return PreparedRasterInput(ContractState.incompatible, None, "input_resolution_invalid")
    quality_values = (
        metadata.valid_fraction,
        metadata.nodata_fraction,
        metadata.snr_db,
    )
    if not all(np.isfinite(value) for value in quality_values):
        return PreparedRasterInput(ContractState.incompatible, None, "input_quality_invalid")
    if (
        metadata.valid_fraction < 0.9
        or metadata.nodata_fraction > 0.1
        or metadata.snr_db < -5.0
    ):
        return PreparedRasterInput(ContractState.abstain, None, "input_quality_low")
    return PreparedRasterInput(
        ContractState.available,
        np.ascontiguousarray(tensor, dtype=np.float32),
        "",
    )


__all__ = ["PreparedRasterInput", "RasterInputMetadata", "prepare_raster_input"]
