"""HUD overlay drawing helpers."""
import cv2
import numpy as np

from .temperature import pixel_to_celsius, pixel_to_fahrenheit, temp_range

# Colours (BGR)
C_WHITE = (255, 255, 255)
C_BLACK = (0, 0, 0)
C_ACCENT = (0, 220, 255)    # cyan-yellow
C_HOT    = (0, 80, 255)     # red-ish in BGR
C_COOL   = (255, 180, 0)    # blue-ish in BGR

# cv2.putText only supports basic ASCII – never use Unicode ° here.
DEG = "C"     # suffix used after temperature values  e.g. "37.5 C"


def _temp_str(temp_c: float, temp_f: float, unit: str) -> str:
    """Build an ASCII-safe temperature string."""
    if unit == "both":
        return f"{temp_c:.1f}C  ({temp_f:.1f}F)"
    if unit == "F":
        return f"{temp_f:.1f}F"
    return f"{temp_c:.1f}C"


def draw_crosshair(img: np.ndarray, x: int, y: int,
                   size: int = 12, color=C_ACCENT, thickness: int = 2) -> None:
    cv2.line(img, (x - size, y), (x + size, y), color, thickness)
    cv2.line(img, (x, y - size), (x, y + size), color, thickness)
    cv2.circle(img, (x, y), size // 2, color, thickness)


def draw_temp_label(img: np.ndarray, x: int, y: int,
                    pixel_val: int,
                    unit: str = "C",
                    color=C_ACCENT) -> None:
    """Draw a temperature bubble near the crosshair."""
    temp_c = pixel_to_celsius(pixel_val)
    temp_f = pixel_to_fahrenheit(pixel_val)
    label = _temp_str(temp_c, temp_f, unit)

    (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    bx, by = x + 15, y - 10
    # clamp inside frame
    bx = min(bx, img.shape[1] - tw - 10)
    by = max(by, th + 5)

    cv2.rectangle(img, (bx - 4, by - th - 4), (bx + tw + 4, by + bl + 2),
                  C_BLACK, -1)
    cv2.rectangle(img, (bx - 4, by - th - 4), (bx + tw + 4, by + bl + 2),
                  color, 1)
    cv2.putText(img, label, (bx, by),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


def draw_colorbar(img: np.ndarray, colormap: int,
                  min_temp: float, max_temp: float,
                  x: int = None, y: int = 20, height: int = 200,
                  width: int = 18) -> None:
    """Draw a vertical colour scale bar on the right edge."""
    h, w = img.shape[:2]

    if x is None:
        x = w - width - 10

    # Clamp so the bar always fits inside the image
    x      = max(0, min(x, w - width))
    y      = max(0, min(y, h - 1))
    height = min(height, h - y)
    width  = min(width,  w - x)

    if height <= 0 or width <= 0:
        return

    bar = np.linspace(255, 0, height, dtype=np.uint8).reshape(height, 1)
    bar = cv2.applyColorMap(bar, colormap)   # (height, 1, 3)
    bar = cv2.resize(bar, (width, height))
    img[y:y + height, x:x + width] = bar

    for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
        temp = max_temp - frac * (max_temp - min_temp)
        ty = y + int(frac * height)
        label_x = max(0, x - 46)
        if 0 < ty < h:
            # Pure ASCII label: "150C", "-20C" etc.
            cv2.putText(img, f"{temp:.0f}C", (label_x, ty + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, C_WHITE, 1, cv2.LINE_AA)


def draw_stats_bar(img: np.ndarray, gray16: np.ndarray,
                   mx: int, my: int, frame_idx: int = 0) -> None:
    """Draw the bottom status bar with min/max/cursor temperature."""
    h, w = img.shape[:2]
    bar_h = 32
    cv2.rectangle(img, (0, h - bar_h), (w, h), (20, 20, 20), -1)

    min_t, max_t = temp_range(gray16)
    g_h, g_w = gray16.shape
    px = int(gray16[my, mx]) if 0 <= my < g_h and 0 <= mx < g_w else 0
    cur_t = pixel_to_celsius(px)

    # All ASCII – no Unicode characters
    info = (f"  XY({mx},{my})  "
            f"Temp:{cur_t:.1f}C  |  "
            f"Min:{min_t:.1f}C  Max:{max_t:.1f}C  |  "
            f"Frame:{frame_idx}")
    cv2.putText(img, info, (6, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, C_WHITE, 1, cv2.LINE_AA)
