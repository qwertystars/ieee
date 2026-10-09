"""
Method 4 - Real-time Thermal Simulation on any Camera (Webcam or Thermal)
==========================================================================
Works with:
  - Regular webcam (uint8, YUV420/BGR/Gray) -> simulated thermal via colormap
  - Real Gray16 thermal camera (uint16)     -> actual calibrated temperature

Simulated mode:
  Brightness in each frame is mapped to a user-defined temperature range
  (default 20 degC - 40 degC) using per-frame adaptive normalisation.
  Brighter pixels -> hotter, darker pixels -> cooler.

Controls:
  Mouse hover -> live temperature at cursor
  Click       -> pin a temperature measurement
  'c'         -> clear all pins
  's'         -> save screenshot
  '+'/'='     -> raise max simulated temp
  '-'         -> lower max simulated temp
  ESC         -> exit
"""
from __future__ import annotations
import time
import os

import cv2
import numpy as np

from .overlay import (draw_crosshair, draw_temp_label, draw_colorbar,
                      draw_stats_bar, C_ACCENT)

# ── Simulated temperature range (degC) ────────────────────────────────────
SIM_TEMP_MIN = 20.0   # darkest pixel = this temperature
SIM_TEMP_MAX = 40.0   # brightest pixel = this temperature

_state = {"mx": 0, "my": 0, "pins": []}


def _mouse(event, x, y, flags, param):
    _state["mx"], _state["my"] = x, y
    if event == cv2.EVENT_LBUTTONDOWN:
        _state["pins"].append((x, y))


# ── Frame decoding ─────────────────────────────────────────────────────────

def _decode_frame(raw: np.ndarray) -> np.ndarray | None:
    """
    Convert whatever shape/dtype the camera gives into a standard
    BGR uint8 image.

    Handles:
      (H, W, 3) uint8 BGR   -> pass through
      (H, W)    uint8 gray  -> convert to BGR
      (1, N)    uint8       -> likely YUV420 NV12/YU12; try to decode
      (H, W)    uint16      -> real thermal Gray16; returned unchanged (uint16)
    """
    if raw is None:
        return None

    # ---- Real Gray16 thermal frame ----------------------------------------
    if raw.dtype == np.uint16:
        return raw  # handled separately in the main loop

    # ---- Standard 3-channel BGR -------------------------------------------
    if raw.ndim == 3 and raw.shape[2] == 3:
        return raw

    # ---- 2-D grayscale ----------------------------------------------------
    if raw.ndim == 2:
        return cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)

    # ---- Flat / 1-row buffer (YUV420 or raw bytes) ------------------------
    if raw.ndim <= 2:
        flat = raw.flatten()
        n = flat.size

        # YUV420 NV12 / YU12: total_bytes = W * H * 1.5  ->  W*H = n * 2/3
        yuv_pixels = (n * 2) // 3
        # Try common resolutions whose W*H == yuv_pixels
        candidates = []
        for w in [1280, 960, 848, 800, 640, 480, 424, 320, 256, 176, 160]:
            if yuv_pixels % w == 0:
                h = yuv_pixels // w
                candidates.append((h, w))

        for (h, w) in candidates:
            if h * w * 3 // 2 == n:
                try:
                    yuv = flat.reshape(h * 3 // 2, w)
                    bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV12)
                    return bgr
                except Exception:
                    try:
                        yuv = flat.reshape(h * 3 // 2, w)
                        bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_YV12)
                        return bgr
                    except Exception:
                        pass

        # Last resort: treat as raw grayscale, pick largest square-ish shape
        for w in [1280, 960, 640, 480, 320, 256, 176]:
            if n % w == 0:
                h = n // w
                gray = flat[:h * w].reshape(h, w)
                return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    return None


def _bgr_to_simulated_thermal(bgr: np.ndarray,
                               sim_min: float,
                               sim_max: float,
                               colormap: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert a BGR webcam frame to a false-colour thermal display.

    Returns:
      display  - colormap-applied BGR image for rendering
      gray8    - 0-255 grayscale image (used as proxy for 'temperature')

    Strategy:
      1. Convert to grayscale (luminance)
      2. Apply a gentle Gaussian blur to reduce noise
      3. Normalize per-frame to 0-255 (adaptive: uses the frame's own min/max
         expanded slightly so stable areas don't wash out)
      4. Apply the chosen thermal colormap
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Blur reduces pixel noise so temps don't flicker every frame
    gray = cv2.GaussianBlur(gray, (7, 7), 2)

    # Adaptive normalisation: use percentile clipping (2nd–98th) so
    # a single bright spec or dark shadow doesn't crush the whole range
    lo = int(np.percentile(gray, 2))
    hi = int(np.percentile(gray, 98))
    if hi <= lo:
        hi = lo + 1

    norm = np.clip((gray.astype(np.float32) - lo) / (hi - lo), 0, 1)
    gray8 = (norm * 255).astype(np.uint8)

    display = cv2.applyColorMap(gray8, colormap)
    return display, gray8


def _pixel_to_sim_temp(gray8_val: int, sim_min: float, sim_max: float) -> float:
    """Map a normalised 0-255 brightness value to the simulated temp range."""
    return sim_min + (gray8_val / 255.0) * (sim_max - sim_min)


def _draw_sim_temp_label(img: np.ndarray, x: int, y: int,
                         gray8: np.ndarray,
                         sim_min: float, sim_max: float,
                         color=(0, 220, 255)) -> None:
    h, w = gray8.shape
    if not (0 <= y < h and 0 <= x < w):
        return
    val = int(gray8[y, x])
    temp = _pixel_to_sim_temp(val, sim_min, sim_max)
    label = f"{temp:.1f}C"
    (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    bx = min(x + 15, img.shape[1] - tw - 10)
    by = max(y - 10, th + 5)
    cv2.rectangle(img, (bx - 4, by - th - 4), (bx + tw + 4, by + bl + 2),
                  (0, 0, 0), -1)
    cv2.rectangle(img, (bx - 4, by - th - 4), (bx + tw + 4, by + bl + 2),
                  color, 1)
    cv2.putText(img, label, (bx, by),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


def _draw_sim_stats(img: np.ndarray, gray8: np.ndarray,
                    mx: int, my: int,
                    sim_min: float, sim_max: float, frame_idx: int) -> None:
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, h - 32), (w, h), (20, 20, 20), -1)
    g_h, g_w = gray8.shape
    val = int(gray8[my, mx]) if 0 <= my < g_h and 0 <= mx < g_w else 0
    cur = _pixel_to_sim_temp(val, sim_min, sim_max)
    info = (f"  XY({mx},{my})  Temp:{cur:.1f}C  |  "
            f"Est.Min:{sim_min:.0f}C  Est.Max:{sim_max:.0f}C  |  "
            f"Frame:{frame_idx}  [+/-] adjust range")
    cv2.putText(img, info, (6, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)


# ── Main run function ──────────────────────────────────────────────────────

def run(camera_source: int | str = 1,
        colormap: int = cv2.COLORMAP_INFERNO,
        alert_threshold_c: float = 40.0,
        sim_temp_min: float = SIM_TEMP_MIN,
        sim_temp_max: float = SIM_TEMP_MAX) -> None:
    """
    Stream any camera (webcam or thermal) with a thermal false-colour overlay.

    For webcams: brightness -> simulated temperature in [sim_temp_min, sim_temp_max].
    For real Gray16 thermal cameras: actual calibrated temperature.
    """
    cap = cv2.VideoCapture(camera_source)

    if not cap.isOpened():
        print(f"[Method 4] Cannot open camera '{camera_source}'.")
        return

    # Try to get the native resolution reported by the driver
    cap_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[Method 4] Camera '{camera_source}' opened  "
          f"reported size={cap_w}x{cap_h}")

    # Probe first frame to detect dtype
    ret, probe = cap.read()
    if not ret or probe is None:
        print("[Method 4] Could not read from camera.")
        cap.release()
        return

    is_real_thermal = (probe.dtype == np.uint16)
    mode = "REAL THERMAL (uint16)" if is_real_thermal else "WEBCAM THERMAL SIM"
    print(f"[Method 4] Mode: {mode}  dtype={probe.dtype}  shape={probe.shape}")

    win = "Method 4 - Thermal Camera (s=screenshot, c=clear pins, +/-=temp range, ESC=exit)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, _mouse)

    frame_idx = 0
    screenshot_dir = os.path.join(os.path.dirname(__file__), "..", "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    fps_buf = []

    # Reuse the probe frame as the first frame
    raw = probe

    while True:
        t0 = time.time()

        # ── Decode frame ────────────────────────────────────────────────────
        if is_real_thermal:
            # Real Gray16: use existing pipeline
            from .temperature import gray16_to_display, temp_range
            gray16 = raw if raw.dtype == np.uint16 else raw.astype(np.uint16) * 257
            if gray16.ndim != 2:
                gray16 = gray16[:, :, 0]
            h, w = gray16.shape
            min_t, max_t = temp_range(gray16)
            display = gray16_to_display(gray16, colormap).copy()
            draw_colorbar(display, colormap, min_t, max_t)

            mx, my = _state["mx"], _state["my"]
            for (px, py) in _state["pins"]:
                if 0 <= py < h and 0 <= px < w:
                    draw_crosshair(display, px, py, color=(0, 255, 150))
                    draw_temp_label(display, px, py, int(gray16[py, px]),
                                    unit="both", color=(0, 255, 150))
            if 0 <= my < h and 0 <= mx < w:
                draw_crosshair(display, mx, my)
                draw_temp_label(display, mx, my, int(gray16[my, mx]))
            draw_stats_bar(display, gray16, mx, my, frame_idx)

        else:
            # Webcam: simulate thermal
            bgr = _decode_frame(raw)
            if bgr is None:
                ret, raw = cap.read()
                continue

            display, gray8 = _bgr_to_simulated_thermal(
                bgr, sim_temp_min, sim_temp_max, colormap)
            h, w = display.shape[:2]

            draw_colorbar(display, colormap, sim_temp_min, sim_temp_max)

            mx, my = _state["mx"], _state["my"]
            for (px, py) in _state["pins"]:
                draw_crosshair(display, px, py, color=(0, 255, 150))
                _draw_sim_temp_label(display, px, py, gray8,
                                     sim_temp_min, sim_temp_max,
                                     color=(0, 255, 150))
            if 0 <= my < h and 0 <= mx < w:
                draw_crosshair(display, mx, my)
                _draw_sim_temp_label(display, mx, my, gray8,
                                     sim_temp_min, sim_temp_max)
            _draw_sim_stats(display, gray8, mx, my,
                            sim_temp_min, sim_temp_max, frame_idx)

            # Alert when simulated hot spot exceeds threshold
            if sim_temp_max >= alert_threshold_c:
                hot_val = int(np.percentile(gray8, 98))
                hot_temp = _pixel_to_sim_temp(hot_val, sim_temp_min, sim_temp_max)
                if hot_temp >= alert_threshold_c:
                    cv2.rectangle(display, (0, 0), (w - 1, h - 1), (0, 0, 255), 3)

        # ── FPS + mode header ────────────────────────────────────────────────
        elapsed = time.time() - t0
        fps_buf.append(elapsed)
        if len(fps_buf) > 20:
            fps_buf.pop(0)
        fps = 1.0 / (sum(fps_buf) / len(fps_buf) + 1e-9)

        header = f"[{mode}]  FPS:{fps:.1f}"
        cv2.putText(display, header, (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, C_ACCENT, 1, cv2.LINE_AA)

        cv2.imshow(win, display)

        # ── Read next frame while processing keys ────────────────────────────
        key = cv2.waitKey(1) & 0xFF
        ret, raw = cap.read()
        if not ret:
            print("[Method 4] Frame grab failed.")
            break
        frame_idx += 1

        if key == 27:                          # ESC
            break
        elif key == ord('c'):
            _state["pins"].clear()
        elif key in (ord('+'), ord('=')):      # raise max temp
            sim_temp_max = min(sim_temp_max + 1, 100.0)
        elif key == ord('-'):                  # lower max temp
            sim_temp_max = max(sim_temp_max - 1, sim_temp_min + 1)
        elif key == ord('s'):
            path = os.path.join(screenshot_dir, f"thermal_{frame_idx:05d}.png")
            cv2.imwrite(path, display)
            print(f"[Method 4] Screenshot -> {path}")

    cap.release()
    cv2.destroyAllWindows()
