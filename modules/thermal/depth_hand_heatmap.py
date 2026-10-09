#!/usr/bin/env python3
"""
================================================================================
UNMUTED - 3D Hand Tracking, Depth Math & Radiative Thermal Heatmap Engine
================================================================================
Introduces:
  1. Simultaneous Dual-Hand 3D Tracking (21 landmarks/hand) via MediaPipe Tasks.
  2. Mathematical Depth Estimation via Pinhole Camera Biometrics & Focal Physics.
  3. 3D Euclidean Spatial Metrics (Pinch Distance, Proximity Velocity dZ/dt, Gestures).
  4. Real-time Depth-Modulated Radiative Thermal Heatmap with Dual-Layer Glow,
     skeleton heat filaments, fingertip radiation, and red-orange thermal palettes.
  5. Tactical Cyberpunk 4-Quadrant HUD, 3D Isometric Wireframes & Oscilloscope Telemetry.
================================================================================
"""

import os
import sys
import time
import math
import argparse
import threading
import urllib.request
import numpy as np
import cv2

# Suppress verbose TensorFlow / MediaPipe C++ logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
except ImportError:
    print("❌ Error: mediapipe is not installed. Please run: pip install mediapipe")
    sys.exit(1)


# ==============================================================================
# 1. MODEL DOWNLOADER & ASSET MANAGEMENT
# ==============================================================================

MODEL_FILENAME = "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"

def ensure_model_exists(target_path: str = MODEL_FILENAME) -> str:
    """Ensure the MediaPipe Hand Landmarker model exists locally; download if absent."""
    if os.path.exists(target_path) and os.path.getsize(target_path) > 5000000:
        return target_path

    print(f"📦 MediaPipe Hand Landmarker model checking '{target_path}'...")
    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        print(f"⏳ File is currently being downloaded ({os.path.getsize(target_path) / (1024*1024):.2f} MB)... Waiting for completion.")
        for _ in range(60):
            time.sleep(1.0)
            if os.path.exists(target_path) and os.path.getsize(target_path) > 7500000:
                print(f"✅ Model download verified ({os.path.getsize(target_path) / (1024*1024):.2f} MB).")
                return target_path

    print(f"⬇️  Downloading from official Google Storage:\n   {MODEL_URL}")
    
    def reporthook(count, block_size, total_size):
        percent = int(count * block_size * 100 / total_size)
        percent = min(100, max(0, percent))
        sys.stdout.write(f"\r   Progress: [{'=' * (percent // 4):<25}] {percent}% ({count * block_size / (1024*1024):.1f} MB)")
        sys.stdout.flush()

    try:
        temp_target = target_path + ".tmp"
        urllib.request.urlretrieve(MODEL_URL, temp_target, reporthook)
        os.rename(temp_target, target_path)
        sys.stdout.write("\n")
        print(f"✅ Model downloaded successfully ({os.path.getsize(target_path) / (1024*1024):.2f} MB).")
    except Exception as e:
        print(f"\n❌ Failed to download model: {e}")
        print(f"💡 Please manually download '{MODEL_FILENAME}' from {MODEL_URL} and place it in the current directory.")
        sys.exit(1)

    return target_path


# ==============================================================================
# 2. NON-BLOCKING VIDEO & CAMERA CAPTURE
# ==============================================================================

class ThreadedCamera:
    """Non-blocking threaded webcam reader to eliminate I/O frame lag on macOS/Linux/Win."""
    def __init__(self, src=0, target_w: int = 1280, target_h: int = 720):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = False
        self.ret = False
        self.frame = None
        self.lock = threading.Lock()
        
        if self.cap.isOpened():
            self.ret, self.frame = self.cap.read()
            if self.ret and self.frame is not None:
                self.running = True
                self.thread = threading.Thread(target=self._update, daemon=True)
                self.thread.start()

    def _update(self):
        while self.running:
            if not self.cap.isOpened():
                time.sleep(0.01)
                continue
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.ret = ret
                    self.frame = frame
            else:
                time.sleep(0.005)

    def is_opened(self) -> bool:
        return self.cap.isOpened() and self.running

    def read(self) -> tuple[bool, np.ndarray]:
        with self.lock:
            if not self.ret or self.frame is None:
                return False, None
            return True, self.frame.copy()

    def release(self):
        self.running = False
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=0.2)
        if self.cap.isOpened():
            self.cap.release()


class VideoLooper:
    """Accurately paces video playback to a target speed multiplier in a continuous loop."""
    def __init__(self, video_path: str, speed_multiplier: float = 1.0):
        self.cap = cv2.VideoCapture(video_path)
        self.raw_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.raw_fps <= 0 or np.isnan(self.raw_fps):
            self.raw_fps = 30.0
        self.speed = max(0.1, min(speed_multiplier, 3.0))
        self.frame_interval = 1.0 / (self.raw_fps * self.speed)
        self.last_frame = None
        self.last_update_time = time.time()
        
        if self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.last_frame = frame

    def set_speed(self, speed_multiplier: float):
        self.speed = max(0.1, min(speed_multiplier, 3.0))
        self.frame_interval = 1.0 / (self.raw_fps * self.speed)
        self.last_update_time = time.time()

    def is_opened(self) -> bool:
        return self.cap.isOpened()

    def get_frame(self) -> tuple[bool, np.ndarray]:
        if not self.cap.isOpened():
            return False, None
        now = time.time()
        elapsed = now - self.last_update_time
        if elapsed >= self.frame_interval:
            frames_to_advance = int(elapsed / self.frame_interval)
            for _ in range(frames_to_advance):
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                if ret and frame is not None:
                    self.last_frame = frame
            self.last_update_time += frames_to_advance * self.frame_interval
        return (self.last_frame is not None), self.last_frame

    def release(self):
        if self.cap.isOpened():
            self.cap.release()


# ==============================================================================
# 3. MATHEMATICAL DEPTH & HAND KINEMATICS ENGINE
# ==============================================================================

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # Index
    (5, 9), (9, 10), (10, 11), (11, 12),   # Middle
    (9, 13), (13, 14), (14, 15), (15, 16), # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
    (0, 17)                                # Palm base closure
]

FINGERTIP_INDICES = [4, 8, 12, 16, 20]
MCP_INDICES = [1, 5, 9, 13, 17]
PALM_CENTER_INDICES = [0, 5, 9, 13, 17]


class HandState:
    """Stores biomechanical, 3D metric, depth, and kinematic telemetry for a single hand."""
    def __init__(self, handedness: str = "Unknown"):
        self.handedness = handedness  # "Left" or "Right"
        self.confidence = 0.0
        self.landmarks_norm = []      # 21 Normalized (x, y, z)
        self.landmarks_px = []        # 21 Image pixel (u, v)
        self.landmarks_3d = []        # 21 Metric 3D points (X_cm, Y_cm, Z_cm)
        self.depth_cm = 50.0          # Estimated distance in centimeters
        self.depth_smooth = 50.0      # Smoothed distance
        self.velocity_z = 0.0         # Proximity speed in cm/s (dZ/dt)
        self.pinch_dist_3d = 0.0      # 3D Euclidean distance between Thumb Tip and Index Tip in cm
        self.is_pinching = False
        self.gesture_name = "OPEN"
        self.hand_openness = 1.0      # Metric spread of fingers (0.0=Fist to 1.0=Open)
        self.bbox = (0, 0, 0, 0)      # (x_min, y_min, x_max, y_max)
        self.palm_center_px = (0, 0)
        self.history_depth = []       # Ring buffer of recent depth readings
        self.last_timestamp = time.time()


class HandDepthMathEngine:
    """
    Mathematical Hand Depth Reconstruction & Kinematics Engine.
    
    Depth Math Principles:
      1. Pinhole Perspective Model:
         Focal length f ≈ 0.85 * Image_Width (assuming standard 65 deg FOV).
      2. Biometric Scale Invariant:
         Average adult human hand index-to-pinky MCP span (breadth) W_palm ≈ 8.5 cm.
         Estimated Depth: Z_est = (f * W_palm) / d_palm_px.
      3. Metric 3D Reconstruction:
         X_i = (u_i - c_x) * Z_i / f_x
         Y_i = (v_i - c_y) * Z_i / f_y
         Z_i = Z_est + z_i_rel * Scale
      4. 3D Euclidean Pinch Metric:
         D_pinch = sqrt((X_thumb - X_index)^2 + (Y_thumb - Y_index)^2 + (Z_thumb - Z_index)^2)
      5. Kinematic Proximity Velocity:
         v_z = dZ / dt (Approaching vs Receding in cm/s)
    """
    def __init__(self, img_w: int, img_h: int, fov_deg: float = 65.0):
        self.img_w = img_w
        self.img_h = img_h
        self.cx = img_w / 2.0
        self.cy = img_h / 2.0
        
        # Pinhole focal length from horizontal field of view
        fov_rad = math.radians(fov_deg)
        self.fx = (img_w / 2.0) / math.tan(fov_rad / 2.0)
        self.fy = self.fx  # Square pixels assumption
        
        # Anatomical biometric reference constants
        self.PALM_BREADTH_REF_CM = 8.5   # Distance between Index MCP (5) and Pinky MCP (17)
        self.HAND_LENGTH_REF_CM = 18.5   # Distance between Wrist (0) and Middle Tip (12)
        
        # Temporal smoothing buffers for hands
        self.tracked_hands: dict[str, HandState] = {
            "Left": HandState("Left"),
            "Right": HandState("Right")
        }

    def process_landmarks(self, raw_landmarks_list, handedness_list, timestamp: float) -> list[HandState]:
        """Convert raw MediaPipe outputs into calibrated 3D metric telemetry."""
        active_states = []

        for idx, (landmarks, hand_info) in enumerate(zip(raw_landmarks_list, handedness_list)):
            label = hand_info[0].category_name  # "Left" or "Right"
            conf = hand_info[0].score
            
            if label not in self.tracked_hands:
                self.tracked_hands[label] = HandState(label)
            state = self.tracked_hands[label]
            state.confidence = conf
            state.landmarks_norm = [(lm.x, lm.y, lm.z) for lm in landmarks]
            
            # 1. Convert normalized coordinates to pixel coordinates
            pts_px = []
            xs, ys = [], []
            for lm in landmarks:
                u = int(np.clip(lm.x * self.img_w, 0, self.img_w - 1))
                v = int(np.clip(lm.y * self.img_h, 0, self.img_h - 1))
                pts_px.append((u, v))
                xs.append(u)
                ys.append(v)
            state.landmarks_px = pts_px
            state.bbox = (min(xs), min(ys), max(xs), max(ys))
            
            # Palm center pixel
            state.palm_center_px = (
                int(sum(pts_px[i][0] for i in PALM_CENTER_INDICES) / len(PALM_CENTER_INDICES)),
                int(sum(pts_px[i][1] for i in PALM_CENTER_INDICES) / len(PALM_CENTER_INDICES))
            )

            # 2. Biometric Depth Math (Triangulation via Palm MCP span)
            p_idx_mcp = np.array(pts_px[5], dtype=np.float32)
            p_pky_mcp = np.array(pts_px[17], dtype=np.float32)
            palm_px = float(np.linalg.norm(p_idx_mcp - p_pky_mcp))
            palm_px = max(15.0, palm_px)
            
            # Raw distance formula: Z = (f * W) / d_px
            z_raw_cm = (self.fx * self.PALM_BREADTH_REF_CM) / palm_px
            z_raw_cm = float(np.clip(z_raw_cm, 12.0, 200.0))
            
            # Double Adaptive EMA Filter for smooth, jitter-free reading
            dt = max(1e-3, timestamp - state.last_timestamp)
            state.last_timestamp = timestamp
            
            alpha = 0.25
            state.depth_smooth = (alpha * z_raw_cm) + ((1.0 - alpha) * state.depth_smooth)
            state.depth_cm = state.depth_smooth
            
            # Compute Proximity Velocity (dZ/dt) in cm/s
            v_inst = (z_raw_cm - state.depth_smooth) / dt
            state.velocity_z = (0.2 * v_inst) + (0.8 * state.velocity_z)
            
            # Maintain rolling depth waveform history
            state.history_depth.append(state.depth_smooth)
            if len(state.history_depth) > 120:
                state.history_depth.pop(0)

            # 3. 3D Metric Reconstruction of All 21 Keypoints
            pts_3d = []
            for i, lm in enumerate(landmarks):
                z_i = state.depth_smooth + (lm.z * state.depth_smooth * 1.5)
                x_i = ((lm.x * self.img_w) - self.cx) * (z_i / self.fx)
                y_i = ((lm.y * self.img_h) - self.cy) * (z_i / self.fy)
                pts_3d.append((x_i, y_i, z_i))
            state.landmarks_3d = pts_3d

            # 4. 3D Euclidean Pinch Distance (Thumb Tip [4] vs Index Tip [8])
            p_thumb_3d = np.array(pts_3d[4])
            p_index_3d = np.array(pts_3d[8])
            pinch_dist_3d = float(np.linalg.norm(p_thumb_3d - p_index_3d))
            state.pinch_dist_3d = pinch_dist_3d
            state.is_pinching = (pinch_dist_3d < 3.2)

            # 5. Hand Openness & Gesture Recognition
            p_wrist_3d = np.array(pts_3d[0])
            tip_distances = [np.linalg.norm(np.array(pts_3d[tip]) - p_wrist_3d) for tip in FINGERTIP_INDICES]
            avg_tip_dist = float(np.mean(tip_distances))
            
            state.hand_openness = float(np.clip((avg_tip_dist - 7.0) / 11.0, 0.0, 1.0))
            state.gesture_name = self._classify_gesture(pts_3d, pts_px, state.is_pinching, state.hand_openness)

            active_states.append(state)

        return active_states

    def _classify_gesture(self, pts_3d: list, pts_px: list, is_pinching: bool, openness: float) -> str:
        """Classify biological hand gestures based on 3D geometry and knuckle flexion."""
        if is_pinching:
            return "PINCH / GRAB"
        
        wrist = np.array(pts_3d[0])
        d_idx = np.linalg.norm(np.array(pts_3d[8]) - wrist)
        d_mid = np.linalg.norm(np.array(pts_3d[12]) - wrist)
        d_rng = np.linalg.norm(np.array(pts_3d[16]) - wrist)
        d_pky = np.linalg.norm(np.array(pts_3d[20]) - wrist)
        d_thb = np.linalg.norm(np.array(pts_3d[4]) - wrist)

        idx_open = d_idx > 12.0
        mid_open = d_mid > 12.5
        rng_open = d_rng > 11.0
        pky_open = d_pky > 10.0
        thb_open = d_thb > 9.5

        if idx_open and mid_open and rng_open and pky_open:
            return "OPEN PALM"
        elif not idx_open and not mid_open and not rng_open and not pky_open:
            if thb_open:
                return "THUMBS UP"
            return "CLOSED FIST"
        elif idx_open and not mid_open and not rng_open and not pky_open:
            return "POINTING"
        elif idx_open and mid_open and not rng_open and not pky_open:
            return "PEACE / V"
        elif idx_open and not mid_open and not rng_open and pky_open:
            return "ROCK / METAL"
        
        return "DYNAMIC"


# ==============================================================================
# 4. RADIATIVE THERMAL HEATMAP ACCUMULATOR (RED-ORANGE PATTERN)
# ==============================================================================

class DepthThermalHeatmapAccumulator:
    """
    High-Performance Thermal Heatmap Engine with Depth-Modulated Radiation Physics.
    
    Physics Model:
      - Hands closer to the camera/sensor radiate exponentially higher thermal signatures.
      - Dual-layer radiation: Sharp inner core + Wide outer radiating red-orange glow.
      - Exact Unmuted Red-Orange Thermal LUT (Black -> Deep Red -> Vibrant Orange -> Yellow -> White).
      - Joint-to-joint thermal filaments create anatomical continuity.
      - Temporal heat accumulation and realistic atmospheric dissipation.
    """
    def __init__(self, render_w: int, render_h: int, internal_scale: float = 0.5):
        self.render_w = render_w
        self.render_h = render_h
        self.scale = internal_scale
        
        # Internal low-latency grid
        self.grid_w = max(64, int(render_w * internal_scale))
        self.grid_h = max(36, int(render_h * internal_scale))
        
        # Heat buffer (Float32)
        self.heat_buffer = np.zeros((self.grid_h, self.grid_w), dtype=np.float32)
        
        # Reference calibration depth (40 cm = standard interactive zone)
        self.Z_REF_CM = 40.0
        self.decay_rate = 0.86  # Smooth temporal dissipation

        # Colormaps
        self.current_colormap_idx = 0
        self.colormap_names = ["RED-ORANGE THERMAL", "INFERNO", "WHITE-HOT FLIR", "JET (RAINBOW)"]
        self.red_orange_lut = self._build_red_orange_lut()

    def _build_red_orange_lut(self) -> np.ndarray:
        """Create exact red-orange thermal colormap (Black -> Red -> Orange -> Yellow -> White)."""
        lut = np.zeros((256, 1, 3), dtype=np.uint8)
        for i in range(256):
            if i == 0:
                lut[i, 0] = [0, 0, 0]
            elif i <= 80:
                lut[i, 0] = [0, 0, int((i / 80.0) * 255)] # Blue=0, Green=0, Red=0..255 (Pure Red)
            elif i <= 160:
                lut[i, 0] = [0, int(((i - 80) / 80.0) * 140), 255] # Blue=0, Green=0..140, Red=255 (Red -> Orange)
            elif i <= 220:
                lut[i, 0] = [0, 140 + int(((i - 160) / 60.0) * 90), 255] # Blue=0, Green=140..230, Red=255 (Orange -> Bright Yellow)
            else:
                lut[i, 0] = [int(((i - 220) / 35.0) * 200), 230 + int(((i - 220) / 35.0) * 25), 255] # Yellow -> Incandescent White
        return lut

    def cycle_colormap(self) -> str:
        """Switch between thermal palettes."""
        self.current_colormap_idx = (self.current_colormap_idx + 1) % len(self.colormap_names)
        return self.colormap_names[self.current_colormap_idx]

    def clear(self):
        """Reset thermal accumulation buffer."""
        self.heat_buffer.fill(0)

    def inject_hand_thermal_energy(self, hands: list[HandState]):
        """Inject depth-modulated radiation from all active hands into thermal buffer."""
        # 1. Dissipate existing heat slightly
        self.heat_buffer *= self.decay_rate
        
        # Convection diffusion
        self.heat_buffer = cv2.GaussianBlur(self.heat_buffer, (3, 3), 0.5)

        for hand in hands:
            # Proximity thermal multiplier: closer hand = much hotter radiation!
            z_factor = float(np.clip(self.Z_REF_CM / max(10.0, hand.depth_smooth), 0.4, 3.5))
            base_radius_px = int(np.clip(16 * z_factor * self.scale, 4, 32))
            
            grid_pts = []
            for (u, v) in hand.landmarks_px:
                gu = int(u * self.scale)
                gv = int(v * self.scale)
                gu = np.clip(gu, 0, self.grid_w - 1)
                gv = np.clip(gv, 0, self.grid_h - 1)
                grid_pts.append((gu, gv))

            # A. Bone Filament Thermal Heat Bridges
            for idx1, idx2 in HAND_CONNECTIONS:
                pt1, pt2 = grid_pts[idx1], grid_pts[idx2]
                bone_thickness = max(1, int(4 * z_factor * self.scale))
                bone_intensity = 0.8 * z_factor
                cv2.line(self.heat_buffer, pt1, pt2, float(bone_intensity), bone_thickness, cv2.LINE_AA)

            # B. Joint & Fingertip Hotspots
            for i, (gu, gv) in enumerate(grid_pts):
                if i in FINGERTIP_INDICES:
                    weight = 1.8
                    r = base_radius_px
                elif i in PALM_CENTER_INDICES:
                    weight = 2.2
                    r = int(base_radius_px * 1.3)
                else:
                    weight = 1.2
                    r = int(base_radius_px * 0.8)

                cv2.circle(self.heat_buffer, (gu, gv), max(2, r), float(weight * z_factor), -1)

            # C. Pinch Energy Flare
            if hand.is_pinching:
                p_thb = grid_pts[4]
                p_idx = grid_pts[8]
                contact = ((p_thb[0] + p_idx[0]) // 2, (p_thb[1] + p_idx[1]) // 2)
                cv2.circle(self.heat_buffer, contact, int(base_radius_px * 1.6), float(5.0 * z_factor), -1)

    def _apply_lut_to_heat(self, heat: np.ndarray, max_heat: float, mode: int) -> np.ndarray:
        norm = np.clip(heat / max_heat * 255.0, 0.0, 255.0).astype(np.uint8)
        if mode == 0:    # RED-ORANGE THERMAL
            return cv2.LUT(cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR), self.red_orange_lut)
        elif mode == 1:  # INFERNO
            return cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)
        elif mode == 2:  # WHITE-HOT FLIR
            return cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR)
        else:            # JET
            return cv2.applyColorMap(norm, cv2.COLORMAP_JET)

    def render_thermal_image(self, target_w: int, target_h: int) -> np.ndarray:
        """Render dual-layer high-resolution thermal map with inner hot core and radiating red-orange outer glow."""
        mode = self.current_colormap_idx

        # 1. Inner Core Layer (sharper, max heat 5.0 -> hot yellow/white at center)
        inner_heat = cv2.GaussianBlur(self.heat_buffer, (0, 0), 2.5)
        inner_color = self._apply_lut_to_heat(inner_heat, max_heat=5.0, mode=mode)
        
        # 2. Outer Radiating Glow Layer (softer, max heat 9.0 -> deep crimson red and vibrant fiery orange)
        glow_heat = cv2.GaussianBlur(self.heat_buffer, (0, 0), 9.0)
        glow_color = self._apply_lut_to_heat(glow_heat, max_heat=9.0, mode=mode)

        # Merge layers for rich radiant incandescent thermal look
        int_heatmap = cv2.max(inner_color, glow_color)

        thermal_upscaled = cv2.resize(int_heatmap, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        return thermal_upscaled

    def blend_ar_overlay(self, rgb_frame: np.ndarray, alpha_boost: float = 0.80) -> np.ndarray:
        """Blend thermal heatmap directly onto RGB video with depth-proportional glow transparency."""
        h, w = rgb_frame.shape[:2]
        thermal = self.render_thermal_image(w, h)
        
        glow_heat = cv2.GaussianBlur(self.heat_buffer, (0, 0), 6.0)
        heat_up = cv2.resize(glow_heat, (w, h), interpolation=cv2.INTER_LINEAR)
        
        alpha = np.clip((heat_up / 4.5) * alpha_boost, 0.0, 0.85)
        alpha = np.expand_dims(alpha, axis=2)
        
        blended = (rgb_frame.astype(np.float32) * (1.0 - alpha) + 
                   thermal.astype(np.float32) * alpha)
        return blended.astype(np.uint8)


# ==============================================================================
# 5. TACTICAL CYBERPUNK HUD & 3D TELEMETRY PRESENTER
# ==============================================================================

class TacticalHUDPresenter:
    """Renders military/cyberpunk sci-fi telemetry, 3D waveforms, and HUD graphics."""

    @staticmethod
    def draw_corner_brackets(canvas: np.ndarray, color=(0, 180, 255), thickness=2, length=20):
        h, w = canvas.shape[:2]
        pad = 10
        # TL
        cv2.line(canvas, (pad, pad), (pad + length, pad), color, thickness)
        cv2.line(canvas, (pad, pad), (pad, pad + length), color, thickness)
        # TR
        cv2.line(canvas, (w - pad, pad), (w - pad - length, pad), color, thickness)
        cv2.line(canvas, (w - pad, pad), (w - pad, pad + length), color, thickness)
        # BL
        cv2.line(canvas, (pad, h - pad), (pad + length, h - pad), color, thickness)
        cv2.line(canvas, (pad, h - pad), (pad, h - pad - length), color, thickness)
        # BR
        cv2.line(canvas, (w - pad, h - pad), (w - pad - length, h - pad), color, thickness)
        cv2.line(canvas, (w - pad, h - pad), (w - pad, h - pad - length), color, thickness)

    @staticmethod
    def draw_panel_title(canvas: np.ndarray, title: str, subtitle: str = "", color=(0, 220, 255)):
        banner_w = len(title) * 11 + 30
        cv2.rectangle(canvas, (10, 10), (10 + banner_w, 38), (15, 15, 15), -1)
        cv2.rectangle(canvas, (10, 10), (10 + banner_w, 38), color, 1)
        cv2.putText(canvas, title, (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        if subtitle:
            cv2.putText(canvas, subtitle, (18 + banner_w + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)

    @staticmethod
    def draw_hand_skeletons(canvas: np.ndarray, hands: list[HandState]):
        """Render 3D depth-colored skeleton nodes, vectors, and laser links."""
        for hand in hands:
            color_accent = (0, 255, 200) if hand.handedness == "Left" else (0, 140, 255)
            
            # 1. Bone Segments
            for (idx1, idx2) in HAND_CONNECTIONS:
                pt1 = hand.landmarks_px[idx1]
                pt2 = hand.landmarks_px[idx2]
                cv2.line(canvas, pt1, pt2, color_accent, 2, cv2.LINE_AA)

            # 2. Keypoint Nodes with 3D Depth Rings
            for i, (u, v) in enumerate(hand.landmarks_px):
                z_i = hand.landmarks_3d[i][2] if i < len(hand.landmarks_3d) else hand.depth_cm
                ring_r = max(3, int(np.clip(250.0 / z_i, 3, 10)))
                
                if i in FINGERTIP_INDICES:
                    cv2.circle(canvas, (u, v), ring_r, (0, 255, 255), -1, cv2.LINE_AA)
                    cv2.circle(canvas, (u, v), ring_r + 2, (255, 255, 255), 1, cv2.LINE_AA)
                else:
                    cv2.circle(canvas, (u, v), max(2, ring_r - 2), (220, 220, 220), -1, cv2.LINE_AA)

            # 3. Pinch Raycast / Laser Line
            p_thb = hand.landmarks_px[4]
            p_idx = hand.landmarks_px[8]
            laser_color = (0, 0, 255) if hand.is_pinching else (0, 255, 120)
            cv2.line(canvas, p_thb, p_idx, laser_color, 2 if not hand.is_pinching else 4, cv2.LINE_AA)
            
            mid_pinch = ((p_thb[0] + p_idx[0]) // 2, (p_thb[1] + p_idx[1]) // 2)
            cv2.putText(canvas, f"{hand.pinch_dist_3d:.1f}cm", (mid_pinch[0] + 8, mid_pinch[1]), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, laser_color, 1, cv2.LINE_AA)

            # 4. Target Bounding Box & HUD Card
            bx1, by1, bx2, by2 = hand.bbox
            cv2.rectangle(canvas, (bx1 - 10, by1 - 28), (bx2 + 10, by2 + 10), color_accent, 1)
            
            card_text = f"[{hand.handedness.upper()}] {hand.depth_cm:.1f}cm | {hand.gesture_name}"
            cv2.rectangle(canvas, (bx1 - 10, by1 - 28), (bx1 - 10 + len(card_text)*8 + 14, by1 - 8), (15, 15, 15), -1)
            cv2.rectangle(canvas, (bx1 - 10, by1 - 28), (bx1 - 10 + len(card_text)*8 + 14, by1 - 8), color_accent, 1)
            cv2.putText(canvas, card_text, (bx1 - 5, by1 - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)

    @staticmethod
    def draw_isometric_skeleton_3d(canvas: np.ndarray, hand: HandState, x0: int, y0: int, size: int = 140):
        """Render 3D isometric wireframe hand mesh projection."""
        cv2.rectangle(canvas, (x0, y0), (x0 + size, y0 + size), (25, 25, 25), -1)
        cv2.rectangle(canvas, (x0, y0), (x0 + size, y0 + size), (70, 70, 70), 1)
        
        cv2.putText(canvas, f"3D MESH ({hand.handedness})", (x0 + 6, y0 + 14), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 220, 255), 1, cv2.LINE_AA)

        if not hand.landmarks_3d or len(hand.landmarks_3d) < 21:
            return

        wrist = np.array(hand.landmarks_3d[0])
        pts_3d_rel = [np.array(p) - wrist for p in hand.landmarks_3d]

        cos_t, sin_t = math.cos(math.radians(35)), math.sin(math.radians(35))
        cos_p, sin_p = math.cos(math.radians(25)), math.sin(math.radians(25))

        iso_pts = []
        cx_box = x0 + size // 2
        cy_box = y0 + size // 2 + 10
        scale = size / 26.0

        for p in pts_3d_rel:
            x, y, z = p[0], p[1], p[2]
            x_rot = x * cos_t - y * sin_t
            y_rot = (x * sin_t + y * cos_t) * sin_p + z * cos_p
            
            u = int(cx_box + x_rot * scale)
            v = int(cy_box + y_rot * scale)
            iso_pts.append((u, v))

        color = (0, 255, 200) if hand.handedness == "Left" else (0, 160, 255)
        for idx1, idx2 in HAND_CONNECTIONS:
            cv2.line(canvas, iso_pts[idx1], iso_pts[idx2], color, 1, cv2.LINE_AA)

        for i, pt in enumerate(iso_pts):
            node_r = 3 if i in FINGERTIP_INDICES else 2
            node_c = (0, 255, 255) if i in FINGERTIP_INDICES else (200, 200, 200)
            cv2.circle(canvas, pt, node_r, node_c, -1, cv2.LINE_AA)

    @staticmethod
    def draw_telemetry_dashboard(canvas: np.ndarray, hands: list[HandState]):
        """Render 3D depth waveforms, kinematics graphs, and interaction telemetry."""
        h, w = canvas.shape[:2]
        canvas.fill(12)
        TacticalHUDPresenter.draw_corner_brackets(canvas, color=(0, 180, 255))
        TacticalHUDPresenter.draw_panel_title(canvas, "DEPTH TELEMETRY & 3D KINEMATICS", "REAL-TIME METRICS", (0, 220, 255))

        # 1. Left vs Right Hand Distance Cards
        y_offset = 55
        for hand_label, color, border_col in [("Left", (0, 255, 200), (0, 180, 140)), 
                                              ("Right", (0, 160, 255), (0, 120, 200))]:
            hand = next((h for h in hands if h.handedness == hand_label), None)
            
            cv2.rectangle(canvas, (18, y_offset), (w // 2 - 10, y_offset + 95), (20, 20, 20), -1)
            cv2.rectangle(canvas, (18, y_offset), (w // 2 - 10, y_offset + 95), border_col, 1)
            
            header = f"{hand_label.upper()} HAND"
            cv2.putText(canvas, header, (28, y_offset + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)
            
            if hand:
                d_str = f"Z-Depth: {hand.depth_cm:.1f} cm ({hand.depth_cm/100.0:.2f} m)"
                cv2.putText(canvas, d_str, (28, y_offset + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 255, 255), 1, cv2.LINE_AA)
                
                vel_sign = "▲ RECEDING" if hand.velocity_z > 10 else ("▼ APPROACHING" if hand.velocity_z < -10 else "● STABLE")
                v_col = (0, 100, 255) if hand.velocity_z < -10 else ((0, 255, 120) if hand.velocity_z > 10 else (180, 180, 180))
                v_str = f"Speed: {abs(hand.velocity_z):.1f} cm/s {vel_sign}"
                cv2.putText(canvas, v_str, (28, y_offset + 58), cv2.FONT_HERSHEY_SIMPLEX, 0.36, v_col, 1, cv2.LINE_AA)
                
                g_str = f"Gesture: {hand.gesture_name} | Pinch: {hand.pinch_dist_3d:.1f}cm"
                cv2.putText(canvas, g_str, (28, y_offset + 76), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 220, 255), 1, cv2.LINE_AA)

                # Distance gauge bar
                bar_x1, bar_x2 = 28, w // 2 - 25
                bar_w = bar_x2 - bar_x1
                fill_ratio = np.clip(1.0 - (hand.depth_cm - 15.0) / 100.0, 0.0, 1.0)
                cv2.rectangle(canvas, (bar_x1, y_offset + 83), (bar_x2, y_offset + 88), (40, 40, 40), -1)
                cv2.rectangle(canvas, (bar_x1, y_offset + 83), (int(bar_x1 + bar_w * fill_ratio), y_offset + 88), color, -1)
            else:
                cv2.putText(canvas, "STATUS: STANDBY / NOT DETECTED", (28, y_offset + 55), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (100, 100, 100), 1, cv2.LINE_AA)

            y_offset += 105

        # 2. Dual-Hand Disparity / 3D Isometric Mesh Widget (Right side)
        right_panel_x = w // 2 + 10
        left_h = next((h for h in hands if h.handedness == "Left"), None)
        right_h = next((h for h in hands if h.handedness == "Right"), None)

        if left_h and right_h:
            cv2.rectangle(canvas, (right_panel_x, 55), (w - 18, 155), (20, 20, 20), -1)
            cv2.rectangle(canvas, (right_panel_x, 55), (w - 18, 155), (0, 180, 255), 1)
            cv2.putText(canvas, "DUAL-HAND INTERACTION MATH", (right_panel_x + 10, 75), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1, cv2.LINE_AA)

            p_l = np.array(left_h.landmarks_3d[0])
            p_r = np.array(right_h.landmarks_3d[0])
            dist_lr = float(np.linalg.norm(p_l - p_r))
            delta_z = right_h.depth_cm - left_h.depth_cm
            closer_hand = "LEFT CLOSER" if delta_z > 4 else ("RIGHT CLOSER" if delta_z < -4 else "CO-PLANAR (EQUAL)")
            
            cv2.putText(canvas, f"3D Separation: {dist_lr:.1f} cm", (right_panel_x + 10, 98), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"Depth Disparity: ΔZ = {abs(delta_z):.1f} cm", (right_panel_x + 10, 118), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(canvas, f"Alignment: {closer_hand}", (right_panel_x + 10, 138), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 200), 1, cv2.LINE_AA)
        else:
            active_h = left_h or right_h
            if active_h:
                TacticalHUDPresenter.draw_isometric_skeleton_3d(canvas, active_h, right_panel_x + 30, 55, size=100)
            else:
                cv2.rectangle(canvas, (right_panel_x, 55), (w - 18, 155), (20, 20, 20), -1)
                cv2.rectangle(canvas, (right_panel_x, 55), (w - 18, 155), (50, 50, 50), 1)
                cv2.putText(canvas, "3D SPATIAL KINEMATICS", (right_panel_x + 10, 80), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 120, 120), 1, cv2.LINE_AA)
                cv2.putText(canvas, "Awaiting hands in frame...", (right_panel_x + 10, 110), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.36, (80, 80, 80), 1, cv2.LINE_AA)

        # 3. Real-Time Depth Oscilloscope Waveform (Bottom Half)
        plot_y0 = h - 140
        plot_h = 115
        plot_w = w - 36
        plot_x0 = 18

        cv2.rectangle(canvas, (plot_x0, plot_y0), (plot_x0 + plot_w, plot_y0 + plot_h), (18, 18, 18), -1)
        cv2.rectangle(canvas, (plot_x0, plot_y0), (plot_x0 + plot_w, plot_y0 + plot_h), (60, 60, 60), 1)
        
        for step in [25, 50, 75]:
            gy = int(plot_y0 + (step / 100.0) * plot_h)
            cv2.line(canvas, (plot_x0, gy), (plot_x0 + plot_w, gy), (30, 30, 30), 1)
            cv2.putText(canvas, f"{int(120 - step)}cm", (plot_x0 + 4, gy - 2), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.28, (80, 80, 80), 1, cv2.LINE_AA)

        cv2.putText(canvas, "REAL-TIME DEPTH WAVEFORM (OSCILLOSCOPE)", (plot_x0 + 10, plot_y0 - 6), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 220, 255), 1, cv2.LINE_AA)

        for hand_label, line_color in [("Left", (0, 255, 200)), ("Right", (0, 160, 255))]:
            target_h_obj = next((h for h in hands if h.handedness == hand_label), None)
            if target_h_obj and len(target_h_obj.history_depth) > 2:
                hist = target_h_obj.history_depth
                pts = []
                for i, d in enumerate(hist):
                    px = int(plot_x0 + (i / max(1, len(hist) - 1)) * plot_w)
                    norm_d = np.clip((d - 20.0) / 100.0, 0.0, 1.0)
                    py = int(plot_y0 + (1.0 - norm_d) * (plot_h - 10) + 5)
                    pts.append((px, py))
                
                for i in range(len(pts) - 1):
                    cv2.line(canvas, pts[i], pts[i+1], line_color, 2, cv2.LINE_AA)

    @staticmethod
    def draw_thermal_colorbar(canvas: np.ndarray, colormap_name: str, x: int, y: int, width: int = 180, height: int = 12):
        """Draw calibrated thermal colorbar scale with temperature/depth legends."""
        bar = np.linspace(0, 255, width, dtype=np.uint8)
        bar = np.tile(bar, (height, 1))
        
        if "INFERNO" in colormap_name:
            bar_color = cv2.applyColorMap(bar, cv2.COLORMAP_INFERNO)
        elif "JET" in colormap_name:
            bar_color = cv2.applyColorMap(bar, cv2.COLORMAP_JET)
        elif "WHITE-HOT" in colormap_name:
            bar_color = cv2.cvtColor(bar, cv2.COLOR_GRAY2BGR)
        else: # RED-ORANGE THERMAL
            lut = TacticalHUDPresenter._get_red_orange_lut_static()
            bar_color = cv2.LUT(cv2.cvtColor(bar, cv2.COLOR_GRAY2BGR), lut)

        canvas[y:y + height, x:x + width] = bar_color
        cv2.rectangle(canvas, (x, y), (x + width, y + height), (150, 150, 150), 1)
        cv2.putText(canvas, "COOL (FAR)", (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (180, 180, 180), 1, cv2.LINE_AA)
        cv2.putText(canvas, "HOT (CLOSE)", (x + width - 65, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 200, 255), 1, cv2.LINE_AA)

    @staticmethod
    def _get_red_orange_lut_static():
        lut = np.zeros((256, 1, 3), dtype=np.uint8)
        for i in range(256):
            if i == 0:
                lut[i, 0] = [0, 0, 0]
            elif i <= 80:
                lut[i, 0] = [0, 0, int((i / 80.0) * 255)]
            elif i <= 160:
                lut[i, 0] = [0, int(((i - 80) / 80.0) * 140), 255]
            elif i <= 220:
                lut[i, 0] = [0, 140 + int(((i - 160) / 60.0) * 90), 255]
            else:
                lut[i, 0] = [int(((i - 220) / 35.0) * 200), 230 + int(((i - 220) / 35.0) * 25), 255]
        return lut


# ==============================================================================
# 6. MAIN APPLICATION PIPELINE
# ==============================================================================

def build_view_quadrants(cam_frame: np.ndarray, 
                         thermal_map: np.ndarray, 
                         ar_blended: np.ndarray, 
                         telemetry_canvas: np.ndarray, 
                         hands: list[HandState], 
                         quad_w: int, quad_h: int, 
                         colormap_name: str, 
                         bg_blend: bool) -> np.ndarray:
    """Compose the 2x2 Tactical Cyberpunk HUD."""
    tl = cam_frame.copy()
    TacticalHUDPresenter.draw_corner_brackets(tl, (0, 180, 255))
    TacticalHUDPresenter.draw_panel_title(tl, "OPTICAL RGB FEED", f"HANDS: {len(hands)} ACTIVE", (0, 220, 255))
    TacticalHUDPresenter.draw_hand_skeletons(tl, hands)

    if bg_blend:
        tr = ar_blended.copy()
    else:
        tr = thermal_map.copy()
    TacticalHUDPresenter.draw_corner_brackets(tr, (0, 140, 255))
    TacticalHUDPresenter.draw_panel_title(tr, f"THERMAL HEATMAP [{colormap_name}]", "DEPTH-MODULATED FLIR", (0, 140, 255))
    TacticalHUDPresenter.draw_thermal_colorbar(tr, colormap_name, quad_w - 200, quad_h - 22)

    bl = ar_blended.copy()
    TacticalHUDPresenter.draw_corner_brackets(bl, (0, 255, 180))
    TacticalHUDPresenter.draw_panel_title(bl, "AUGMENTED REALITY (AR) OVERLAY", "PINCH & METRIC RAYCAST", (0, 255, 180))
    TacticalHUDPresenter.draw_hand_skeletons(bl, hands)

    br = telemetry_canvas

    top_row = np.hstack([tl, tr])
    bottom_row = np.hstack([bl, br])
    quad_canvas = np.vstack([top_row, bottom_row])

    cv2.line(quad_canvas, (quad_w, 0), (quad_w, quad_h * 2), (50, 50, 50), 2)
    cv2.line(quad_canvas, (0, quad_h), (quad_w * 2, quad_h), (50, 50, 50), 2)

    return quad_canvas


def main():
    parser = argparse.ArgumentParser(description="UNMUTED 3D Hand Tracking, Depth Math & Radiative Thermal Heatmap Engine")
    parser.add_argument("--source", type=str, default="0", help="Webcam index (e.g. '0') or video file path (e.g. 'TEST.mp4')")
    parser.add_argument("--width", type=int, default=1280, help="Camera capture width (default: 1280)")
    parser.add_argument("--height", type=int, default=720, help="Camera capture height (default: 720)")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier if using video file (default: 1.0)")
    parser.add_argument("--no-mirror", action="store_true", help="Disable horizontal mirror flipping")
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 UNMUTED 3D HAND TRACKING, DEPTH MATH & THERMAL HEATMAP ENGINE")
    print("=" * 70)

    # 1. Initialize MediaPipe HandLandmarker Model
    model_path = ensure_model_exists(MODEL_FILENAME)
    print("⚡ Initializing MediaPipe HandLandmarker Tasks API (Dual-Hand 3D)...")

    base_options = python.BaseOptions(model_asset_path=model_path)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.IMAGE,
        num_hands=2,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5
    )
    detector = vision.HandLandmarker.create_from_options(options)
    print("✅ HandLandmarker Engine initialized.")

    # 2. Setup Video / Webcam Stream
    quad_w, quad_h = 960, 540
    cap_cam = None
    vid_looper = None
    is_video_file = False

    if args.source.isdigit():
        cam_idx = int(args.source)
        cap_cam = ThreadedCamera(cam_idx, target_w=args.width, target_h=args.height)
        if not cap_cam.is_opened():
            print(f"⚠️  Webcam index {cam_idx} not found. Attempting index 0...")
            cap_cam = ThreadedCamera(0, target_w=args.width, target_h=args.height)
        
        if cap_cam.is_opened():
            print(f"📷 Active Threaded Camera stream initialized at index {cam_idx}.")
        else:
            print("⚠️  No physical webcam accessible. Falling back to video file 'TEST.mp4'...")
            is_video_file = True
    else:
        is_video_file = True

    if is_video_file:
        video_src = args.source if not args.source.isdigit() else ("TEST.mp4" if os.path.exists("TEST.mp4") else "test.mp4")
        if not os.path.exists(video_src):
            print(f"❌ Video file '{video_src}' not found.")
            return
        vid_looper = VideoLooper(video_src, speed_multiplier=args.speed)
        print(f"🎬 Video stream loaded from '{video_src}' (Playback {args.speed}x).")

    # 3. Initialize Math & Thermal Engines
    depth_math_engine = HandDepthMathEngine(quad_w, quad_h, fov_deg=65.0)
    thermal_heatmap_engine = DepthThermalHeatmapAccumulator(quad_w, quad_h, internal_scale=0.5)

    # UI State
    view_modes = ["4-QUADRANT HUD", "SPLIT DUAL VIEW", "FULL THERMAL FLIR", "FULL AR OVERLAY"]
    current_view_idx = 0
    bg_blend = False
    is_fullscreen = False
    show_help = True

    win_name = "UNMUTED - 3D Hand Tracking, Depth Math & Thermal Heatmap"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 1280, 720)

    print("\n" + "=" * 70)
    print("🎮 INTERACTIVE KEYBOARD CONTROLS:")
    print("  'v'     -> Cycle View Modes (4-Quadrant, Dual Split, Full Thermal, Full AR)")
    print("  'm'     -> Cycle Thermal Colormaps (Red-Orange, Inferno, White-Hot, Jet)")
    print("  'b'     -> Toggle Heatmap Background (Black FLIR vs Live RGB Blend)")
    print("  'c'     -> Clear accumulated thermal heat signatures")
    print("  'f'     -> Toggle Fullscreen Window")
    print("  'h'     -> Toggle Help HUD overlay")
    print("  ESC/'q' -> Exit cleanly")
    print("=" * 70 + "\n")

    fps_buffer = []
    telemetry_canvas = np.zeros((quad_h, quad_w, 3), dtype=np.uint8)

    try:
        while True:
            t_start = time.time()

            # --- A. Acquire Frame ---
            raw_frame = None
            if cap_cam is not None and cap_cam.is_opened():
                ret, raw_frame = cap_cam.read()
            elif vid_looper is not None and vid_looper.is_opened():
                ret, raw_frame = vid_looper.get_frame()

            if raw_frame is None:
                raw_frame = np.zeros((quad_h, quad_w, 3), dtype=np.uint8)
                cv2.putText(raw_frame, "STREAM OFFLINE", (quad_w // 2 - 120, quad_h // 2), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            else:
                raw_frame = cv2.resize(raw_frame, (quad_w, quad_h), interpolation=cv2.INTER_LINEAR)

            # Mirror flip for natural user interaction unless disabled
            if not args.no_mirror:
                cam_frame = cv2.flip(raw_frame, 1)
            else:
                cam_frame = raw_frame

            # --- B. MediaPipe 3D Hand Landmark Inference ---
            rgb_frame = cv2.cvtColor(cam_frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            detection_result = detector.detect(mp_image)

            # --- C. Depth Math & Kinematics Processing ---
            hands = []
            if detection_result.hand_landmarks and detection_result.handedness:
                corrected_handedness = []
                for h_cat in detection_result.handedness:
                    orig_label = h_cat[0].category_name
                    # Swap Left <-> Right if mirror flipped
                    if not args.no_mirror:
                        flipped_label = "Right" if orig_label == "Left" else "Left"
                    else:
                        flipped_label = orig_label
                    corrected_cat = python.components.containers.Category(
                        index=h_cat[0].index,
                        score=h_cat[0].score,
                        display_name=flipped_label,
                        category_name=flipped_label
                    )
                    corrected_handedness.append([corrected_cat])

                hands = depth_math_engine.process_landmarks(
                    detection_result.hand_landmarks,
                    corrected_handedness,
                    timestamp=t_start
                )

            # --- D. Radiative Thermal Heatmap Simulation ---
            thermal_heatmap_engine.inject_hand_thermal_energy(hands)
            thermal_image = thermal_heatmap_engine.render_thermal_image(quad_w, quad_h)
            ar_blended = thermal_heatmap_engine.blend_ar_overlay(cam_frame, alpha_boost=0.80)

            # --- E. Render Telemetry Dashboard ---
            TacticalHUDPresenter.draw_telemetry_dashboard(telemetry_canvas, hands)

            # --- F. Render Selected View Layout ---
            colormap_name = thermal_heatmap_engine.colormap_names[thermal_heatmap_engine.current_colormap_idx]
            current_mode = view_modes[current_view_idx]

            if current_mode == "4-QUADRANT HUD":
                final_canvas = build_view_quadrants(
                    cam_frame, thermal_image, ar_blended, telemetry_canvas,
                    hands, quad_w, quad_h, colormap_name, bg_blend
                )
            elif current_mode == "SPLIT DUAL VIEW":
                left_view = cam_frame.copy()
                TacticalHUDPresenter.draw_hand_skeletons(left_view, hands)
                TacticalHUDPresenter.draw_panel_title(left_view, "OPTICAL RGB FEED", f"HANDS: {len(hands)}", (0, 220, 255))
                
                right_view = ar_blended.copy() if bg_blend else thermal_image.copy()
                TacticalHUDPresenter.draw_panel_title(right_view, f"THERMAL RADIATIVE HEATMAP [{colormap_name}]", "DEPTH PHYSICS", (0, 140, 255))
                TacticalHUDPresenter.draw_thermal_colorbar(right_view, colormap_name, quad_w - 200, quad_h - 22)
                
                final_canvas = np.hstack([left_view, right_view])
                cv2.line(final_canvas, (quad_w, 0), (quad_w, quad_h), (50, 50, 50), 2)
            elif current_mode == "FULL THERMAL FLIR":
                final_canvas = cv2.resize(thermal_image if not bg_blend else ar_blended, (quad_w * 2, quad_h * 2))
                TacticalHUDPresenter.draw_panel_title(final_canvas, f"UNMUTED THERMAL FLIR [{colormap_name}]", "HIGH SENSITIVITY", (0, 140, 255))
                TacticalHUDPresenter.draw_thermal_colorbar(final_canvas, colormap_name, (quad_w * 2) - 240, (quad_h * 2) - 36, width=220, height=16)
            else: # FULL AR OVERLAY
                final_canvas = cv2.resize(ar_blended, (quad_w * 2, quad_h * 2))
                TacticalHUDPresenter.draw_hand_skeletons(final_canvas, hands)
                TacticalHUDPresenter.draw_panel_title(final_canvas, "UNMUTED AUGMENTED REALITY (AR) HUD", "REAL-TIME DEPTH KINEMATICS", (0, 255, 180))

            # --- G. Global Cyberpunk Header & FPS Telemetry Badge ---
            elapsed = time.time() - t_start
            fps_buffer.append(elapsed)
            if len(fps_buffer) > 30:
                fps_buffer.pop(0)
            fps = 1.0 / (sum(fps_buffer) / len(fps_buffer) + 1e-9)

            c_w = final_canvas.shape[1]
            header_str = f"UNMUTED DEPTH MATH & THERMAL HUD | VIEW: {current_mode} | {fps:.1f} FPS"
            cv2.rectangle(final_canvas, (c_w // 2 - 270, 0), (c_w // 2 + 270, 28), (15, 15, 15), -1)
            cv2.rectangle(final_canvas, (c_w // 2 - 270, 0), (c_w // 2 + 270, 28), (0, 180, 255), 1)
            cv2.putText(final_canvas, header_str, (c_w // 2 - 255, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 240, 255), 1, cv2.LINE_AA)

            if show_help:
                help_str = "[V] View Mode  |  [M] Colormap  |  [B] Background  |  [C] Clear Heat  |  [F] Fullscreen  |  [H] Hide Help  |  [Q/ESC] Quit"
                cv2.rectangle(final_canvas, (10, final_canvas.shape[0] - 26), (len(help_str)*8 + 25, final_canvas.shape[0] - 4), (15, 15, 15), -1)
                cv2.rectangle(final_canvas, (10, final_canvas.shape[0] - 26), (len(help_str)*8 + 25, final_canvas.shape[0] - 4), (60, 60, 60), 1)
                cv2.putText(final_canvas, help_str, (18, final_canvas.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1, cv2.LINE_AA)

            # --- H. Display Canvas ---
            cv2.imshow(win_name, final_canvas)

            # --- I. Keyboard Interaction ---
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                break
            elif key == ord('v'):
                current_view_idx = (current_view_idx + 1) % len(view_modes)
                print(f"🔄 View Mode switched to: {view_modes[current_view_idx]}")
            elif key == ord('m'):
                new_cmap = thermal_heatmap_engine.cycle_colormap()
                print(f"🎨 Thermal Colormap switched to: {new_cmap}")
            elif key == ord('b'):
                bg_blend = not bg_blend
                print(f"🎭 Heatmap Background: {'RGB Live Feed Blend' if bg_blend else 'Black FLIR Screen'}")
            elif key == ord('c'):
                thermal_heatmap_engine.clear()
                print("🧹 Thermal Heat signatures cleared.")
            elif key == ord('h'):
                show_help = not show_help
            elif key == ord('f'):
                is_fullscreen = not is_fullscreen
                if is_fullscreen:
                    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                else:
                    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)

    finally:
        if cap_cam is not None:
            cap_cam.release()
        if vid_looper is not None:
            vid_looper.release()
        cv2.destroyAllWindows()
        print("🛑 Streams and window resources released. Program exited cleanly.")


if __name__ == "__main__":
    main()
