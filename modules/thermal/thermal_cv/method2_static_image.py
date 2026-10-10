from __future__ import annotations

"""
Method 2 – Measuring Temperature from a Thermal Image
======================================================
• Load a Gray16 image (or synthesise one)
• Click any pixel → see its temperature in °C and °F
• Displays Inferno false-colour overlay with colorbar
"""
import cv2
import numpy as np

from .temperature import pixel_to_celsius, pixel_to_fahrenheit, gray16_to_display, temp_range
from .overlay import draw_crosshair, draw_temp_label, draw_colorbar, draw_stats_bar

_state = {"gray16": None, "display": None, "mx": 0, "my": 0,
          "colormap": cv2.COLORMAP_INFERNO, "clicks": []}


def _mouse(event, x, y, flags, param):
    _state["mx"], _state["my"] = x, y
    if event == cv2.EVENT_LBUTTONDOWN:
        _state["clicks"].append((x, y))


def run(image_path: str | None = None,
        colormap: int = cv2.COLORMAP_INFERNO) -> None:
    from .synthetic import make_gray16_frame

    # ── Load ─────────────────────────────────────────────────────────────────
    if image_path:
        gray16 = cv2.imread(image_path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)
        if gray16 is None or gray16.dtype != np.uint16:
            print("[warn] Not a valid Gray16 image – using synthetic.")
            gray16 = make_gray16_frame(0)
    else:
        gray16 = make_gray16_frame(0)

    _state["gray16"] = gray16
    _state["colormap"] = colormap
    h, w = gray16.shape
    min_t, max_t = temp_range(gray16)

    win = "Method 2 – Static Image  (click=pin, 'c'=clear, ESC=exit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, _mouse)

    print("[Method 2] Click pixels to read temperature. 'c' clears pins. ESC exits.")

    while True:
        display = gray16_to_display(gray16, colormap).copy()

        # Draw colour bar
        draw_colorbar(display, colormap, min_t, max_t)

        # Draw pinned measurements
        for (px, py) in _state["clicks"]:
            if 0 <= py < h and 0 <= px < w:
                val = int(gray16[py, px])
                draw_crosshair(display, px, py, size=10, color=(0, 255, 150))
                draw_temp_label(display, px, py, val, unit="both",
                                color=(0, 255, 150))

        # Live cursor indicator
        mx, my = _state["mx"], _state["my"]
        if 0 <= my < h and 0 <= mx < w:
            val = int(gray16[my, mx])
            draw_crosshair(display, mx, my)
            draw_temp_label(display, mx, my, val)

        draw_stats_bar(display, gray16, mx, my)

        # Title
        cv2.putText(display, "THERMAL IMAGE ANALYSIS", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 1, cv2.LINE_AA)

        cv2.imshow(win, display)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:     # ESC
            break
        if key == ord('c'):
            _state["clicks"].clear()

    cv2.destroyAllWindows()
