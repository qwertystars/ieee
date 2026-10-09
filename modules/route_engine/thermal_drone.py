"""
================================================================================
 ResQnet - Thermal Drone Vision System
================================================================================
 Senior Computer Vision Pipeline that:
   1. Simulates a thermal drone feed (or ingests a real video / webcam)
   2. Pre-processes frames: grayscale → Gaussian Blur → Adaptive Threshold
   3. Detects blobs via findContours + area-based filtering
   4. Calculates centroid (X, Y) from cv2.moments for every valid blob
   5. Maps pixel coords → normalised [0.0, 1.0] FOV space
   6. Locks signatures stable across 5 frames and POSTs to FastAPI
   7. Renders a professional COLORMAP_JET overlay with bounding boxes

 Usage:
   python thermal_drone.py                  # pure simulation
   python thermal_drone.py --video thermal.mp4
   python thermal_drone.py --camera 0

 Requires (pip install):
   opencv-python  numpy  requests
================================================================================
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import requests

# ─────────────────────────────── Configuration ───────────────────────────────

API_ENDPOINT   = "http://127.0.0.1:8765/api/hazard"
TARGET_FPS     = 30
FRAME_W, FRAME_H = 960, 540     # synthetic simulation resolution

# ── Contour area filter (human-sized heat blobs) ──────────────────────────────
MIN_AREA       = 120    # px²  — below this → sensor noise / interference
MAX_AREA       = 9_000  # px²  — above this → burning debris / large fire

# ── Signature locking / debounce ─────────────────────────────────────────────
STABILITY_FRAMES     = 5          # consecutive frames blob must appear to "lock"
LOCK_COOLDOWN_S      = 2.0        # seconds between API pushes for the same blob
POSITION_CHANGE_PX   = 30         # pixels: if centroid moves > this → new blob

# ── Visual style ──────────────────────────────────────────────────────────────
COLORMAP            = cv2.COLORMAP_JET
BBOX_COLOR_TRACKING = (  0, 255, 128)   # green — actively tracking
BBOX_COLOR_LOCKED   = (  0, 200, 255)   # cyan  — locked & reported
BBOX_COLOR_TEXT     = (255, 255, 255)   # white label text
OVERLAY_ALPHA       = 0.35              # thermal overlay blend weight


# ─────────────────────────────── Data classes ────────────────────────────────

@dataclass
class Blob:
    """Tracks a single detected heat blob across frames."""
    cx: int
    cy: int
    area: float
    radius: float
    frame_count: int = 1          # how many consecutive frames seen
    last_seen_ts: float = field(default_factory=time.time)
    last_api_ts:  float = 0.0     # timestamp of last successful POST
    locked: bool = False          # True once we have posted to the API


@dataclass
class SignatureTracker:
    """
    Maintains a dictionary of active blobs, merges detections across frames,
    and determines when a blob is 'stable' enough to be reported.
    """
    blobs: Dict[int, Blob] = field(default_factory=dict)
    _next_id: int = 0

    # ──────────────────────────────────────────────────────────────────────────
    def update(self, detections: List[Tuple[int, int, float, float]]) -> List[Blob]:
        """
        Match incoming (cx, cy, area, radius) detections to existing blobs.
        Returns the list of blobs that crossed the STABILITY_FRAMES threshold
        and are ready to be reported (or re-reported after cooldown).
        """
        now = time.time()
        matched_ids: set[int] = set()

        # ── Match detections to existing blobs ────────────────────────────────
        for cx, cy, area, radius in detections:
            best_id   = None
            best_dist = POSITION_CHANGE_PX

            for bid, blob in self.blobs.items():
                dist = math.hypot(cx - blob.cx, cy - blob.cy)
                if dist < best_dist:
                    best_dist = dist
                    best_id   = bid

            if best_id is not None:
                # Update existing blob
                b = self.blobs[best_id]
                b.cx, b.cy       = cx, cy
                b.area, b.radius = area, radius
                b.frame_count   += 1
                b.last_seen_ts   = now
                matched_ids.add(best_id)
            else:
                # Register new blob
                self.blobs[self._next_id] = Blob(cx, cy, area, radius)
                matched_ids.add(self._next_id)
                self._next_id += 1

        # ── Evict blobs not seen this frame ───────────────────────────────────
        stale = [bid for bid, b in self.blobs.items()
                 if bid not in matched_ids and (now - b.last_seen_ts) > 0.5]
        for bid in stale:
            del self.blobs[bid]

        # ── Return lockable blobs ─────────────────────────────────────────────
        lockable = []
        for blob in self.blobs.values():
            if blob.frame_count >= STABILITY_FRAMES:
                if now - blob.last_api_ts >= LOCK_COOLDOWN_S:
                    lockable.append(blob)
        return lockable


# ────────────────────────────── Thermal Simulation ───────────────────────────

class ThermalSimulator:
    """
    Generates a synthetic thermal video feed when no real source is available.
    Simulates human heat signatures as bright Gaussian blobs drifting across
    a noisy dark background.
    """

    def __init__(self, w: int = FRAME_W, h: int = FRAME_H):
        self.w, self.h = w, h
        self._agents   = [self._spawn_agent() for _ in range(random.randint(2, 5))]
        self._rng      = np.random.default_rng(42)
        self._tick     = 0

    def _spawn_agent(self) -> dict:
        return {
            "x":    float(random.randint(80, FRAME_W - 80)),
            "y":    float(random.randint(80, FRAME_H - 80)),
            "vx":   random.uniform(-0.7, 0.7),
            "vy":   random.uniform(-0.7, 0.7),
            "heat": random.randint(200, 255),
            "size": random.randint(18, 35),   # sigma of Gaussian in pixels
        }

    def _update_agents(self):
        for a in self._agents:
            a["x"] = np.clip(a["x"] + a["vx"], 60, self.w - 60)
            a["y"] = np.clip(a["y"] + a["vy"], 60, self.h - 60)
            # Bounce off edges
            if a["x"] in (60, self.w - 60):
                a["vx"] *= -1
            if a["y"] in (60, self.h - 60):
                a["vy"] *= -1
            # Flicker heat ±5
            a["heat"] = int(np.clip(a["heat"] + random.randint(-5, 5), 160, 255))

    def read(self) -> Tuple[bool, np.ndarray]:
        """Return (True, grayscale_frame) mimicking cv2.VideoCapture.read()."""
        self._tick += 1
        self._update_agents()

        # ── Base ambient noise (cold background = low pixel values) ──────────
        frame = self._rng.integers(10, 50, (self.h, self.w), dtype=np.uint8)

        # ── Paint each agent as a Gaussian hot blob ───────────────────────────
        Y, X = np.ogrid[:self.h, :self.w]
        for a in self._agents:
            sig2 = a["size"] ** 2
            blob = a["heat"] * np.exp(
                -((X - a["x"]) ** 2 + (Y - a["y"]) ** 2) / (2 * sig2)
            )
            frame = np.clip(frame.astype(np.int32) + blob.astype(np.int32), 0, 255).astype(np.uint8)

        # ── Add occasional large warm region (debris / fire) ─────────────────
        if self._tick % 90 == 0:
            rx  = random.randint(100, self.w - 100)
            ry  = random.randint(100, self.h - 100)
            rr  = random.randint(60, 120)
            cv2.circle(frame, (rx, ry), rr, 180, -1)

        return True, frame


# ──────────────────────────── Pre-processing Pipeline ────────────────────────

def preprocess(frame_gray: np.ndarray) -> np.ndarray:
    """
    Convert to grayscale (if needed) → Gaussian Blur → Adaptive Threshold.

    Returns a binary mask where 255 = "hot" region.
    """
    if len(frame_gray.shape) == 3:
        gray = cv2.cvtColor(frame_gray, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame_gray.copy()

    # ── Step 1: Gaussian Blur (σ=3) to suppress sensor noise ─────────────────
    blurred = cv2.GaussianBlur(gray, (9, 9), sigmaX=3, sigmaY=3)

    # ── Step 2: Adaptive Threshold — local mean comparison ───────────────────
    #   blockSize: neighbourhood size (must be odd)
    #   C:  constant subtracted from mean (negative = keep only hot pixels)
    thresh = cv2.adaptiveThreshold(
        blurred,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=31,
        C=-25,
    )

    # ── Step 3: Morphological close — fill small holes inside blobs ───────────
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    return closed


# ───────────────────────── Blob Detection & Filtering ────────────────────────

def detect_blobs(
    binary: np.ndarray,
) -> List[Tuple[int, int, float, float]]:
    """
    Find contours, filter by area, calculate centroid and radius.

    Returns list of (cx, cy, area, radius) for human-sized blobs.
    """
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    detections: List[Tuple[int, int, float, float]] = []

    for cnt in contours:
        area = cv2.contourArea(cnt)

        # ── Area gate: human-sized only ──────────────────────────────────────
        if area < MIN_AREA or area > MAX_AREA:
            continue

        # ── Centroid from image moments ───────────────────────────────────────
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])

        # ── Equivalent radius from area ───────────────────────────────────────
        radius = math.sqrt(area / math.pi)

        detections.append((cx, cy, area, radius))

    return detections


# ─────────────────────────────── Spatial Mapping ─────────────────────────────

def pixel_to_normalised(
    cx: int, cy: int, frame_w: int, frame_h: int
) -> Tuple[float, float]:
    """
    Map pixel (cx, cy) → normalised (0.0–1.0, 0.0–1.0) coordinates
    representing the drone's current field of view on the disaster map.
    """
    nx = round(cx / frame_w, 6)
    ny = round(cy / frame_h, 6)
    return nx, ny


# ────────────────────────────── API Integration ──────────────────────────────

def post_detection(
    blob: Blob,
    frame_w: int,
    frame_h: int,
    confidence: float,
    session: requests.Session,
) -> bool:
    """
    POST a THERMAL_DETECTION event to the FastAPI backend.

    Returns True on success, False on any network / server error.
    """
    nx, ny = pixel_to_normalised(blob.cx, blob.cy, frame_w, frame_h)
    payload = {
        "type":       "THERMAL_DETECTION",
        "coords":     [nx, ny],
        "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 4),
        "radius":     round(blob.radius, 2),
    }

    try:
        resp = session.post(API_ENDPOINT, json=payload, timeout=1.5)
        if resp.status_code == 201:
            data = resp.json()
            print(
                f"  ✓ POST OK  → id={data['id']}  "
                f"coords=({nx:.3f}, {ny:.3f})  "
                f"conf={payload['confidence']}  r={payload['radius']:.1f}px"
            )
            return True
        else:
            print(f"  ✗ POST {resp.status_code}: {resp.text[:120]}")
    except requests.exceptions.ConnectionError:
        print("  ✗ Cannot reach API (is thermal_server.py running?)")
    except requests.exceptions.Timeout:
        print("  ✗ API timeout — will retry next lock cycle")
    return False


# ──────────────────────────── Visual Feedback Renderer ───────────────────────

# Thin divider colour between panels
_DIVIDER_COLOR = (40, 40, 40)
_DIVIDER_W     = 3

# Panel label style
_LABEL_BG   = (15, 15, 15)
_LABEL_H    = 22


def _draw_panel_label(panel: np.ndarray, text: str, accent: Tuple[int, int, int]) -> None:
    """Draw a small footer label bar at the bottom of a single panel in-place."""
    h, w = panel.shape[:2]
    cv2.rectangle(panel, (0, h - _LABEL_H), (w, h), _LABEL_BG, -1)
    cv2.putText(
        panel, text, (6, h - 6),
        cv2.FONT_HERSHEY_SIMPLEX, 0.42, accent, 1, cv2.LINE_AA
    )


def _build_detection_panel(
    frame_gray: np.ndarray,
    binary:     np.ndarray,
    detections: List[Tuple[int, int, float, float]],
    tracker:    SignatureTracker,
) -> np.ndarray:
    """
    Right panel: COLORMAP_JET thermal + hot-region overlay + bounding boxes.
    """
    # ── Thermal colourmap ────────────────────────────────────────────────────
    thermal = cv2.applyColorMap(frame_gray, COLORMAP)

    # ── Hot-region overlay (semi-transparent red wash) ───────────────────────
    overlay    = thermal.copy()
    hot_region = np.zeros_like(overlay)
    hot_region[binary > 0] = (0, 0, 200)
    cv2.addWeighted(hot_region, OVERLAY_ALPHA, overlay, 1.0, 0, dst=overlay)
    thermal = overlay

    # ── Per-blob annotations ─────────────────────────────────────────────────
    for cx, cy, area, radius in detections:
        best_blob: Optional[Blob] = None
        min_dist = POSITION_CHANGE_PX
        for b in tracker.blobs.values():
            d = math.hypot(cx - b.cx, cy - b.cy)
            if d < min_dist:
                min_dist = d
                best_blob = b

        is_locked = best_blob is not None and best_blob.locked
        frame_cnt = best_blob.frame_count if best_blob else 0
        box_color = BBOX_COLOR_LOCKED if is_locked else BBOX_COLOR_TRACKING
        r_int     = max(int(radius) + 15, 20)

        # Bounding box
        cv2.rectangle(thermal,
                      (cx - r_int, cy - r_int),
                      (cx + r_int, cy + r_int),
                      box_color, 2)

        # Crosshair
        cv2.drawMarker(thermal, (cx, cy), box_color,
                       markerType=cv2.MARKER_CROSS,
                       markerSize=16, thickness=2)

        # Stability progress bar
        bar_max  = r_int * 2
        bar_fill = int(bar_max * min(frame_cnt, STABILITY_FRAMES) / STABILITY_FRAMES)
        cv2.rectangle(thermal,
                      (cx - r_int, cy + r_int + 4),
                      (cx - r_int + bar_max, cy + r_int + 10),
                      (50, 50, 50), -1)
        cv2.rectangle(thermal,
                      (cx - r_int, cy + r_int + 4),
                      (cx - r_int + bar_fill, cy + r_int + 10),
                      box_color, -1)

        # Label
        status_str = "LOCKED" if is_locked else f"TRACK {frame_cnt}/{STABILITY_FRAMES}"
        label      = f"{status_str}  A:{int(area)}px"
        cv2.putText(thermal, label,
                    (cx - r_int, max(cy - r_int - 8, 16)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, BBOX_COLOR_TEXT, 1, cv2.LINE_AA)

    return thermal


def build_visual_frame(
    frame_gray:  np.ndarray,
    binary:      np.ndarray,
    detections:  List[Tuple[int, int, float, float]],
    tracker:     SignatureTracker,
) -> np.ndarray:
    """
    Compose a 3-panel side-by-side display frame:

      [  RAW SENSOR  ] | [  BINARY MASK  ] | [  THERMAL DETECTION  ]

    All three panels share the same height; the total width is 3× the source
    frame width plus 2 dividers.
    """
    h, w = frame_gray.shape[:2]

    # ── Panel 1: Raw grayscale input (false-colour green-tint for readability) ─
    raw_bgr  = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2BGR)
    # Subtle green tint to signal "raw sensor"
    tint          = np.zeros_like(raw_bgr)
    tint[:, :, 1] = (frame_gray * 0.18).astype(np.uint8)   # green channel boost
    raw_panel     = cv2.add(raw_bgr, tint)
    _draw_panel_label(raw_panel, "[1] RAW SENSOR INPUT", (100, 200, 100))

    # ── Panel 2: Binary threshold mask (coloured for clarity) ────────────────
    # Blue = thresholded hot regions; dark background
    mask_bgr   = np.zeros((h, w, 3), dtype=np.uint8)
    # Background: very dark blue-grey
    mask_bgr[:] = (18, 14, 10)
    # Hot regions: cyan-white
    mask_bgr[binary > 0] = (220, 200, 60)   # warm gold for hot pixels

    # Draw all contours (both valid and rejected) in different colours
    all_contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in all_contours:
        area = cv2.contourArea(cnt)
        if area < MIN_AREA:
            color = (60, 60, 180)      # red-ish = too small (noise)
        elif area > MAX_AREA:
            color = (180, 60, 60)      # blue-ish = too large (fire/debris)
        else:
            color = (60, 255, 180)     # green = valid human-sized blob
        cv2.drawContours(mask_bgr, [cnt], -1, color, 1)

    _draw_panel_label(mask_bgr, "[2] ADAPTIVE THRESHOLD MASK", (60, 200, 220))

    # ── Panel 3: Full thermal detection overlay ───────────────────────────────
    det_panel = _build_detection_panel(frame_gray, binary, detections, tracker)
    _draw_panel_label(det_panel, "[3] THERMAL DETECTION (JET)", (0, 200, 255))

    # ── Vertical dividers ─────────────────────────────────────────────────────
    div = np.full((h, _DIVIDER_W, 3), _DIVIDER_COLOR, dtype=np.uint8)

    # ── Horizontal stack ──────────────────────────────────────────────────────
    composite = np.hstack([raw_panel, div, mask_bgr, div, det_panel])
    return composite


def draw_hud(
    frame: np.ndarray,
    fps: float,
    blob_count: int,
    locked_count: int,
    api_ok: bool,
) -> np.ndarray:
    """Overlay a shared HUD bar across the full composite (3-panel) frame."""
    h, w = frame.shape[:2]
    HUD_H = 38

    # ── Semi-transparent top bar spanning all 3 panels ────────────────────────
    bar = frame.copy()
    cv2.rectangle(bar, (0, 0), (w, HUD_H), (8, 8, 8), -1)
    cv2.addWeighted(bar, 0.78, frame, 0.22, 0, dst=frame)

    # Panel boundary markers on the HUD bar
    panel_w = (w - 2 * _DIVIDER_W) // 3
    for px in [panel_w + _DIVIDER_W, 2 * panel_w + 2 * _DIVIDER_W]:
        cv2.line(frame, (px, 0), (px, HUD_H), (55, 55, 55), 1)

    # ── HUD text ──────────────────────────────────────────────────────────────
    api_color = (0, 220, 80) if api_ok else (50, 50, 220)
    api_label = "API ONLINE" if api_ok else "API OFFLINE"

    entries = [
        ("ResQnet  THERMAL",            (10, 24),      (0, 220, 150)),
        (f"{fps:5.1f} FPS",             (190, 24),     (140, 220, 255)),
        (f"BLOBS  {blob_count}",        (310, 24),     (0, 200, 255)),
        (f"LOCKED  {locked_count}",     (430, 24),     (0, 255, 128)),
        (api_label,                     (560, 24),     api_color),
        (time.strftime("%H:%M:%S"),     (w - 105, 24), (160, 160, 160)),
    ]
    for text, pos, color in entries:
        cv2.putText(frame, text, pos,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, color, 1, cv2.LINE_AA)

    # ── Legend strip along the bottom (right panel quadrant) ─────────────────
    lx = 2 * panel_w + 2 * _DIVIDER_W + 6
    ly = h - _LABEL_H - 28
    legend = [
        (BBOX_COLOR_TRACKING, "TRACKING"),
        (BBOX_COLOR_LOCKED,   "LOCKED"),
    ]
    for i, (col, lbl) in enumerate(legend):
        ox = lx + i * 115
        cv2.rectangle(frame, (ox, ly), (ox + 12, ly + 12), col, -1)
        cv2.putText(frame, lbl, (ox + 16, ly + 11),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)

    return frame


# ─────────────────────────────────── Main Loop ───────────────────────────────

def main(source: Optional[str] = None, camera_id: Optional[int] = None) -> None:
    """
    Main processing loop.

    Args:
        source:    Path to a video file (or None for simulation).
        camera_id: Webcam device ID (or None if using file / simulation).
    """

    # ── Source selection ──────────────────────────────────────────────────────
    use_sim = (source is None and camera_id is None)

    if use_sim:
        print("[INFO] No source provided — running built-in thermal simulation.")
        cap = ThermalSimulator(FRAME_W, FRAME_H)
        fw, fh = FRAME_W, FRAME_H
    elif camera_id is not None:
        print(f"[INFO] Opening camera device {camera_id}")
        cap = cv2.VideoCapture(camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    else:
        print(f"[INFO] Opening video: {source}")
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            sys.exit(f"[ERROR] Cannot open video file: {source}")
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"[INFO] Frame size: {fw}×{fh}")
    print(f"[INFO] Target FPS: {TARGET_FPS}")
    print(f"[INFO] API endpoint: {API_ENDPOINT}")
    print("[INFO] Press 'q' to quit | 's' to save screenshot\n")

    tracker        = SignatureTracker()
    session        = requests.Session()
    frame_interval = 1.0 / TARGET_FPS
    last_frame_ts  = 0.0
    api_last_ok    = False
    locked_total   = 0

    # FPS rolling average
    fps_times: deque[float] = deque(maxlen=30)

    while True:
        # ── Frame-rate throttle ───────────────────────────────────────────────
        now = time.time()
        elapsed = now - last_frame_ts
        if elapsed < frame_interval:
            time.sleep(frame_interval - elapsed)
        last_frame_ts = time.time()

        # ── Read frame ────────────────────────────────────────────────────────
        ret, frame = cap.read()
        if not ret:
            if use_sim:
                continue                  # simulator always returns True
            # Video ended — loop
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        # Ensure grayscale
        if len(frame.shape) == 3 and not use_sim:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame            # simulator already returns uint8 gray

        # ── Pre-processing ────────────────────────────────────────────────────
        binary = preprocess(gray)

        # ── Blob detection ────────────────────────────────────────────────────
        detections = detect_blobs(binary)

        # ── Tracker update + locking ──────────────────────────────────────────
        lockable = tracker.update(detections)

        for blob in lockable:
            # Confidence = frame_count / STABILITY_FRAMES (capped at 1.0)
            confidence = min(blob.frame_count / STABILITY_FRAMES, 1.0)
            ok = post_detection(blob, fw, fh, confidence, session)
            blob.last_api_ts = time.time()
            blob.locked      = True
            api_last_ok      = ok
            if ok:
                locked_total += 1

        # ── Visual frame construction ─────────────────────────────────────────
        visual = build_visual_frame(gray, binary, detections, tracker)

        # ── FPS calculation ───────────────────────────────────────────────────
        fps_times.append(time.time())
        if len(fps_times) >= 2:
            fps = (len(fps_times) - 1) / (fps_times[-1] - fps_times[0])
        else:
            fps = 0.0

        visual = draw_hud(
            visual,
            fps         = fps,
            blob_count  = len(detections),
            locked_count= locked_total,
            api_ok      = api_last_ok,
        )

        # ── Display (side-by-side composite) ─────────────────────────────────
        cv2.imshow("ResQnet — Thermal Drone Vision  [RAW | MASK | DETECTION]", visual)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            print("[INFO] Quit requested.")
            break
        elif key == ord("s"):
            fname = f"thermal_capture_{int(time.time())}.png"
            cv2.imwrite(fname, visual)
            print(f"[INFO] Screenshot saved → {fname}")

    cv2.destroyAllWindows()
    if not use_sim:
        cap.release()
    session.close()
    print(f"[INFO] Session ended. Total locked signatures reported: {locked_total}")


# ─────────────────────────────── CLI ─────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ResQnet Thermal Drone Vision System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python thermal_drone.py                      # run thermal simulation
  python thermal_drone.py --video thermal.mp4  # process a video file
  python thermal_drone.py --camera 0           # use webcam device 0
        """,
    )
    parser.add_argument("--video",  type=str, default=None, help="Path to thermal video file")
    parser.add_argument("--camera", type=int, default=None, help="Webcam device ID (e.g. 0)")
    args = parser.parse_args()

    main(source=args.video, camera_id=args.camera)
