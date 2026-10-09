"""Temperature conversion utilities for Gray16 thermal images."""
from __future__ import annotations
import numpy as np


# --- Calibration Constants (adjust to your camera specs) ---
# FLIR-style linear mapping: temp = pixel * scale + offset
# For simulated/demo Gray16 images:
GRAY16_MIN_TEMP = -20.0   # °C at pixel value 0
GRAY16_MAX_TEMP = 150.0   # °C at pixel value 65535

SCALE = (GRAY16_MAX_TEMP - GRAY16_MIN_TEMP) / 65535.0
OFFSET = GRAY16_MIN_TEMP


def pixel_to_celsius(pixel_value: float) -> float:
    """Convert a raw Gray16 pixel value to Celsius."""
    return float(pixel_value) * SCALE + OFFSET


def pixel_to_fahrenheit(pixel_value: float) -> float:
    """Convert a raw Gray16 pixel value to Fahrenheit."""
    return pixel_to_celsius(pixel_value) * 9.0 / 5.0 + 32.0


def gray16_to_display(gray16: np.ndarray, colormap: int) -> np.ndarray:  # noqa: E501
    """
    Normalize a Gray16 image to 8-bit and apply a colormap.
    Returns a BGR image ready for cv2.imshow.
    """
    import cv2
    norm = cv2.normalize(gray16, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    colored = cv2.applyColorMap(norm, colormap)
    return colored


def temp_range(gray16: np.ndarray) -> tuple:
    """Return (min_temp_C, max_temp_C) for the frame."""
    return pixel_to_celsius(gray16.min()), pixel_to_celsius(gray16.max())
