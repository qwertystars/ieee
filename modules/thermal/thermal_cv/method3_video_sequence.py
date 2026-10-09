"""
Method 3 – Measuring Temperature from a Thermal Video (image sequence)
=======================================================================
• Iterates through Gray16 PNG frames in a folder
• Mouse hover → live temperature at cursor
• Click → pin a measurement point that persists across frames
• Keyboard: SPACE=pause, 'c'=clear pins, '['/']'=step, ESC=exit
"""
from __future__ import annotations
import os
import glob
import time

import cv2
import numpy as np

from .temperature import gray16_to_display, temp_range
from .overlay import draw_crosshair, draw_temp_label, draw_colorbar, draw_stats_bar, C_ACCENT

_state = {"mx": 0, "my": 0, "pins": []}


def _mouse(event, x, y, flags, param):
    _state["mx"], _state["my"] = x, y
    if event == cv2.EVENT_LBUTTONDOWN:
        _state["pins"].append((x, y))


def _load_frame(path: str) -> np.ndarray | None:
    frame = cv2.imread(path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)
    if frame is None:
        return None
    if frame.dtype != np.uint16:
        frame = frame.astype(np.uint16) * 257
    return frame


def run(frames_folder: str | None = None,
        fps: float = 10.0,
        colormap: int = cv2.COLORMAP_INFERNO,
        generate_if_missing: bool = True) -> None:
    from .synthetic import generate_sequence, make_gray16_frame

    # ── Resolve frame list ────────────────────────────────────────────────────
    if frames_folder is None:
        frames_folder = os.path.join(os.path.dirname(__file__),
                                     "..", "thermal_frames_demo")
    frames_folder = os.path.abspath(frames_folder)

    patterns = ["*.png", "*.tiff", "*.tif"]
    paths = []
    for p in patterns:
        paths += sorted(glob.glob(os.path.join(frames_folder, p)))

    if not paths:
        if generate_if_missing:
            print(f"[Method 3] No frames found in '{frames_folder}' – generating synthetic sequence …")
            generate_sequence(frames_folder, n_frames=60)
            paths = sorted(glob.glob(os.path.join(frames_folder, "*.png")))
        else:
            print(f"[Method 3] No Gray16 frames found in '{frames_folder}'.")
            return

    print(f"[Method 3] {len(paths)} frames found. SPACE=pause, '['/']'=step, 'c'=clear, ESC=exit")

    win = "Method 3 – Thermal Video Sequence"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, _mouse)

    idx = 0
    paused = False
    delay = max(1, int(1000 / fps))

    while True:
        gray16 = _load_frame(paths[idx])
        if gray16 is None:
            idx = (idx + 1) % len(paths)
            continue

        h, w = gray16.shape
        min_t, max_t = temp_range(gray16)
        display = gray16_to_display(gray16, colormap).copy()
        draw_colorbar(display, colormap, min_t, max_t)

        # Pinned points
        for (px, py) in _state["pins"]:
            if 0 <= py < h and 0 <= px < w:
                val = int(gray16[py, px])
                draw_crosshair(display, px, py, color=(0, 255, 150))
                draw_temp_label(display, px, py, val, unit="both", color=(0, 255, 150))

        # Live cursor
        mx, my = _state["mx"], _state["my"]
        if 0 <= my < h and 0 <= mx < w:
            val = int(gray16[my, mx])
            draw_crosshair(display, mx, my)
            draw_temp_label(display, mx, my, val)

        draw_stats_bar(display, gray16, mx, my, frame_idx=idx)

        # Frame counter
        label = f"Frame {idx + 1}/{len(paths)}  {'[PAUSED]' if paused else ''}"
        cv2.putText(display, label, (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, C_ACCENT, 1, cv2.LINE_AA)

        cv2.imshow(win, display)
        key = cv2.waitKey(delay if not paused else 0) & 0xFF

        if key == 27:                            # ESC
            break
        elif key == ord(' '):
            paused = not paused
        elif key == ord('c'):
            _state["pins"].clear()
        elif key == ord(']') or (not paused):    # next frame
            idx = (idx + 1) % len(paths)
        elif key == ord('['):                    # previous frame
            idx = (idx - 1) % len(paths)

        if not paused and key == 0xFF:           # no key – auto advance
            idx = (idx + 1) % len(paths)

    cv2.destroyAllWindows()
