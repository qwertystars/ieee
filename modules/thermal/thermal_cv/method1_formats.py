"""
Method 1 – Understanding Image Formats (Gray8 vs Gray16)
=========================================================
Demonstrates the key difference:
  • Gray8  (8-bit)  : standard grayscale, 0–255, NO temperature info
  • Gray16 (16-bit) : thermal grayscale, 0–65535, encodes raw sensor data
"""
from __future__ import annotations

import cv2
import numpy as np

from .temperature import pixel_to_celsius, gray16_to_display
from .overlay import draw_colorbar, temp_range


def run(image_path: str | None = None, colormap: int = cv2.COLORMAP_INFERNO) -> None:
    """
    Load (or synthesise) a Gray16 image and show a side-by-side comparison:
      Left  → Gray8 (downsampled to 8-bit) – loses temperature precision
      Right → Gray16 false-colour (Inferno) with temperature values
    """
    from .synthetic import make_gray16_frame

    # ── Load or generate ────────────────────────────────────────────────────
    if image_path:
        gray16 = cv2.imread(image_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)
        if gray16 is None:
            print(f"[warn] Could not open '{image_path}' – using synthetic frame.")
            gray16 = make_gray16_frame(0)
        if gray16.dtype != np.uint16:
            gray16 = gray16.astype(np.uint16) * 257   # stretch 8-bit → 16-bit
    else:
        gray16 = make_gray16_frame(0)

    h, w = gray16.shape

    # ── Gray8 panel ─────────────────────────────────────────────────────────
    gray8 = cv2.normalize(gray16, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    panel8 = cv2.cvtColor(gray8, cv2.COLOR_GRAY2BGR)
    cv2.putText(panel8, "Gray8  (8-bit)  – No Temp Info", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(panel8, "Range: 0 – 255 values", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (150, 150, 150), 1, cv2.LINE_AA)

    # ── Gray16 false-colour panel ────────────────────────────────────────────
    panel16 = gray16_to_display(gray16, colormap)
    min_t, max_t = temp_range(gray16)
    draw_colorbar(panel16, colormap, min_t, max_t)
    cv2.putText(panel16, "Gray16 (16-bit) – Thermal Data", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 1, cv2.LINE_AA)
    cv2.putText(panel16, f"Range: {min_t:.1f}C - {max_t:.1f}C", (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180, 220, 180), 1, cv2.LINE_AA)

    # ── Sample pixel values ──────────────────────────────────────────────────
    sample_points = [(w // 4, h // 4), (w // 2, h // 2), (3 * w // 4, 3 * h // 4)]
    for (px, py) in sample_points:
        val = int(gray16[py, px])
        temp = pixel_to_celsius(val)
        cv2.circle(panel16, (px, py), 5, (0, 255, 255), 2)
        cv2.putText(panel16, f"{temp:.1f}C", (px + 8, py - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

    # ── Info table ───────────────────────────────────────────────────────────
    info_h = 80
    info = np.zeros((info_h, w * 2, 3), dtype=np.uint8)
    rows = [
        "Format    Bit-depth   Unique Values   Temp Resolution   Use-case",
        "Gray8     8-bit       256             N/A               Display / standard CV",
        "Gray16    16-bit      65,536          ~0.0026C/LSB      Thermal measurement",
    ]
    for i, row in enumerate(rows):
        color = (0, 220, 255) if i == 0 else (200, 200, 200)
        cv2.putText(info, row, (12, 20 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, color, 1, cv2.LINE_AA)

    combined = np.hstack([panel8, panel16])
    full = np.vstack([combined, info])

    win = "Method 1 – Gray8 vs Gray16 (press any key to exit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.imshow(win, full)
    print("[Method 1] Showing Gray8 vs Gray16 comparison. Press any key …")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
