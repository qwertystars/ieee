#!/usr/bin/env python3
import os
import sys
import time
import threading
import cv2
import numpy as np
import torch
from ultralytics import YOLO

class ThreadedCamera:
    """Non-blocking threaded webcam reader to eliminate I/O lag."""
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = False
        self.ret = False
        self.frame = None
        self.lock = threading.Lock()
        
        if self.cap.isOpened():
            self.ret, self.frame = self.cap.read()
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

    def is_opened(self):
        return self.cap.isOpened() and self.running

    def read(self):
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
    """Accurately paces video playback to a target speed multiplier in a continuous seamless loop."""
    def __init__(self, video_path: str, speed_multiplier: float = 0.5):
        self.cap = cv2.VideoCapture(video_path)
        self.raw_fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.raw_fps <= 0 or np.isnan(self.raw_fps):
            self.raw_fps = 30.0
        self.speed = max(0.1, min(speed_multiplier, 3.0))
        self.frame_interval = 1.0 / (self.raw_fps * self.speed)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.last_frame = None
        self.last_update_time = time.time()
        self.current_frame_idx = 0
        
        if self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.last_frame = frame
                self.current_frame_idx = 1

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
        
        # Advance frames based on real-time clock pacing and speed multiplier
        if elapsed >= self.frame_interval:
            frames_to_advance = int(elapsed / self.frame_interval)
            for _ in range(frames_to_advance):
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    # Seamlessly loop back to frame 0
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.cap.read()
                    self.current_frame_idx = 1
                else:
                    self.current_frame_idx += 1
                
                if ret and frame is not None:
                    self.last_frame = frame
            
            self.last_update_time += frames_to_advance * self.frame_interval
            
        return (self.last_frame is not None), self.last_frame

    def release(self):
        if self.cap.isOpened():
            self.cap.release()

class HeatmapAccumulator:
    """High-performance thermal accumulator optimized with multi-scale internal resolution."""
    def __init__(self, render_w: int, render_h: int, internal_scale: float = 0.5):
        self.render_w = render_w
        self.render_h = render_h
        self.scale = internal_scale
        
        # Internal grid for fast distance transform and gaussian blurs
        self.int_w = max(64, int(render_w * internal_scale))
        self.int_h = max(36, int(render_h * internal_scale))
        self.heat = np.zeros((self.int_h, self.int_w), dtype=np.float32)

    def update(self, masks: list[np.ndarray], decay: float = 0.25) -> np.ndarray:
        self.heat *= decay
        if masks:
            combined_mask = np.zeros((self.int_h, self.int_w), dtype=np.uint8)
            for mask in masks:
                combined_mask[mask > 0.5] = 255
                
            dist = cv2.distanceTransform(combined_mask, cv2.DIST_L2, 3)
            # Body width normalized for internal grid size (~15px)
            dist_norm = np.clip(dist / 15.0, 0.0, 1.0)
            self.heat += dist_norm * 4.0
            
        return self.heat

    def to_colormap(self, blurred: np.ndarray, max_heat: float = 5.0) -> np.ndarray:
        norm = np.clip(blurred / max_heat * 255, 0, 255).astype(np.uint8)
        
        # Thermal colormap (black -> red -> orange -> yellow -> white)
        lut = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            if i == 0:
                lut[i] = [0, 0, 0]
            elif i <= 80:
                lut[i] = [0, 0, int((i / 80.0) * 255)]
            elif i <= 160:
                lut[i] = [0, int(((i - 80) / 80.0) * 140), 255]
            elif i <= 220:
                lut[i] = [0, 140 + int(((i - 160) / 60.0) * 90), 255]
            else:
                lut[i] = [int(((i - 220) / 35.0) * 200), 230 + int(((i - 220) / 35.0) * 25), 255]
            
        return lut[norm]

def get_colorbar_lut():
    colorbar_lut = np.zeros((1, 256, 3), dtype=np.uint8)
    for i in range(256):
        if i == 0:
            colorbar_lut[0, i] = [0, 0, 0]
        elif i <= 80:
            colorbar_lut[0, i] = [0, 0, int((i / 80.0) * 255)]
        elif i <= 160:
            colorbar_lut[0, i] = [0, int(((i - 80) / 80.0) * 140), 255]
        elif i <= 220:
            colorbar_lut[0, i] = [0, 140 + int(((i - 160) / 60.0) * 90), 255]
        else:
            colorbar_lut[0, i] = [int(((i - 220) / 35.0) * 200), 230 + int(((i - 220) / 35.0) * 25), 255]
    return colorbar_lut

def run_batched_inference(frames: list[np.ndarray], model: YOLO, 
                          int_w: int, int_h: int, device: str,
                          cam_conf: float = 0.40, vid_conf: float = 0.20) -> list[tuple[list[np.ndarray], int]]:
    """Run GPU-batched YOLOv8-seg inference with custom sensitivity per stream."""
    # Run batch inference with imgsz=480 and base conf=0.20 to catch all persons
    results = model(frames, verbose=False, conf=min(cam_conf, vid_conf), imgsz=480, device=device)
    
    batch_outputs = []
    stream_confs = [cam_conf, vid_conf]
    
    for stream_idx, res in enumerate(results):
        min_conf = stream_confs[stream_idx] if stream_idx < len(stream_confs) else 0.30
        masks_out = []
        if res.masks is not None:
            masks_data = res.masks.data.cpu().numpy()
            for i, box in enumerate(res.boxes):
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                # Filter for Person class with stream-specific threshold
                if cls == 0 and conf >= min_conf:
                    mask = masks_data[i]
                    if mask.shape != (int_h, int_w):
                        mask = cv2.resize(mask, (int_w, int_h), interpolation=cv2.INTER_NEAREST)
                    masks_out.append(mask)
        batch_outputs.append((masks_out, len(masks_out)))
        
    return batch_outputs

def draw_hud_decorations(canvas: np.ndarray, title: str, person_count: int, 
                         show_colorbar: bool = False, colorbar_lut: np.ndarray = None,
                         border_color = (0, 140, 255)):
    """Draw corner brackets, title banner, survivor count, live indicator, and optional colorbar."""
    h, w = canvas.shape[:2]
    
    # 1. Subtle horizontal scanline effect
    grid_mask = np.zeros_like(canvas)
    grid_mask[::4, :] = [8, 8, 8]
    canvas = cv2.add(canvas, grid_mask)
    
    # 2. Corner brackets
    thickness = 2
    length = 24
    # Top-Left
    cv2.line(canvas, (12, 12), (12 + length, 12), border_color, thickness)
    cv2.line(canvas, (12, 12), (12, 12 + length), border_color, thickness)
    # Top-Right
    cv2.line(canvas, (w - 12, 12), (w - 12 - length, 12), border_color, thickness)
    cv2.line(canvas, (w - 12, 12), (w - 12, 12 + length), border_color, thickness)
    # Bottom-Left
    cv2.line(canvas, (12, h - 12), (12 + length, h - 12), border_color, thickness)
    cv2.line(canvas, (12, h - 12), (12, h - 12 - length), border_color, thickness)
    # Bottom-Right
    cv2.line(canvas, (w - 12, h - 12), (w - 12 - length, h - 12), border_color, thickness)
    cv2.line(canvas, (w - 12, h - 12), (w - 12, h - 12 - length), border_color, thickness)

    # 3. Top Title Banner
    banner_w = len(title) * 11 + 24
    cv2.rectangle(canvas, (12, 12), (12 + banner_w, 36), (20, 20, 20), -1)
    cv2.rectangle(canvas, (12, 12), (12 + banner_w, 36), border_color, 1)
    cv2.putText(canvas, title, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)

    # 4. Bottom Status (Survivor Count)
    stats = f"Survivors: {person_count}"
    cv2.rectangle(canvas, (12, h - 36), (160, h - 12), (20, 20, 20), -1)
    cv2.rectangle(canvas, (12, h - 36), (160, h - 12), border_color, 1)
    cv2.putText(canvas, stats, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.50, border_color, 1, cv2.LINE_AA)

    # 5. Flashing LIVE indicator
    if int(time.time() * 2) % 2 == 0:
        cv2.circle(canvas, (w - 25, h - 24), 5, (0, 0, 255), -1)

    # 6. Colorbar Thermal Legend
    if show_colorbar and colorbar_lut is not None:
        cb_w, cb_h = 160, 10
        cb_x0, cb_y0 = (w - cb_w) // 2, h - 28
        cb_img = cv2.resize(colorbar_lut, (cb_w, cb_h), interpolation=cv2.INTER_LINEAR)
        canvas[cb_y0:cb_y0 + cb_h, cb_x0:cb_x0 + cb_w] = cb_img
        cv2.rectangle(canvas, (cb_x0, cb_y0), (cb_x0 + cb_w, cb_y0 + cb_h), (120, 120, 120), 1)

    return canvas

def render_thermal_view(frame: np.ndarray, masks: list, heatmap: HeatmapAccumulator, 
                        person_count: int, show_webcam: bool, colorbar_lut: np.ndarray, 
                        title: str) -> np.ndarray:
    """Generate dual-layer thermal heatmap visualization with fast GPU/internal upsampling."""
    h_int, w_int = heatmap.int_h, heatmap.int_w
    h_out, w_out = heatmap.render_h, heatmap.render_w
    
    # Combined binary mask on internal grid
    body_mask = np.zeros((h_int, w_int), dtype=np.uint8)
    if masks:
        for mask in masks:
            body_mask[mask > 0.5] = 255

    # Update internal Heatmap
    heatmap.update(masks, decay=0.25)
    
    # 1. Inner Body Layer (sharper, max heat 5.0 -> hot yellow/white)
    body_heat = cv2.GaussianBlur(heatmap.heat, (0, 0), 3)
    body_color = heatmap.to_colormap(body_heat, max_heat=5.0)
    body_display = cv2.bitwise_and(body_color, body_color, mask=body_mask)
    
    # 2. Outer Radiating Glow Layer (softer, max heat 9.0 -> cooler red/orange)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    glow_mask = cv2.dilate(body_mask, kernel)
    glow_heat = cv2.GaussianBlur(heatmap.heat, (0, 0), 12)
    glow_color = heatmap.to_colormap(glow_heat, max_heat=9.0)
    glow_display = cv2.bitwise_and(glow_color, glow_color, mask=glow_mask)
    
    # Merge layers on internal resolution
    int_heatmap = cv2.max(body_display, glow_display)

    # Upscale internal heatmap to display quadrant size
    heatmap_upscaled = cv2.resize(int_heatmap, (w_out, h_out), interpolation=cv2.INTER_LINEAR)

    if show_webcam:
        glow_mask_up = cv2.resize(glow_mask, (w_out, h_out), interpolation=cv2.INTER_LINEAR)
        glow_heat_up = cv2.resize(glow_heat, (w_out, h_out), interpolation=cv2.INTER_LINEAR)
        
        display = frame.copy()
        alpha_mask = np.clip(glow_heat_up / 5.0, 0.0, 0.7)
        alpha_mask = alpha_mask * (glow_mask_up.astype(np.float32) / 255.0)
        alpha_mask = np.expand_dims(alpha_mask, axis=2)
        blended = (display.astype(np.float32) * (1.0 - alpha_mask) + 
                   heatmap_upscaled.astype(np.float32) * alpha_mask)
        display = blended.astype(np.uint8)
    else:
        display = heatmap_upscaled

    # Draw HUD decorations
    display = draw_hud_decorations(display, title, person_count, show_colorbar=True, 
                                   colorbar_lut=colorbar_lut, border_color=(0, 140, 255))
    return display

def render_rgb_view(frame: np.ndarray, person_count: int, title: str) -> np.ndarray:
    """Generate RGB feed view with HUD for a quadrant."""
    display = frame.copy()
    display = draw_hud_decorations(display, title, person_count, show_colorbar=False, 
                                   border_color=(255, 180, 0))
    return display

def main():
    # Detect hardware acceleration (Apple Silicon Metal MPS, CUDA, or CPU)
    if torch.backends.mps.is_available():
        device = "mps"
        device_name = "Apple Silicon Metal (MPS GPU)"
    elif torch.cuda.is_available():
        device = "cuda"
        device_name = f"NVIDIA GPU ({torch.cuda.get_device_name(0)})"
    else:
        device = "cpu"
        device_name = "CPU"

    print(f"🚀 Hardware Acceleration: {device_name}")
    print("⚡ Loading YOLOv8n-seg model...")
    try:
        model = YOLO("yolov8n-seg.pt")
        # Warmup GPU shaders to prevent first-frame lag
        dummy = np.zeros((480, 480, 3), dtype=np.uint8)
        _ = model([dummy, dummy], verbose=False, conf=0.20, imgsz=480, device=device)
        print("✅ Model loaded and GPU shaders warmed up.")
    except Exception as e:
        print(f"❌ Error loading YOLO model: {e}")
        return

    # 1. Open Threaded Webcam Capture
    cam = None
    for cam_idx in range(3):
        test_cam = ThreadedCamera(cam_idx)
        if test_cam.is_opened():
            cam = test_cam
            print(f"📷 Opened Threaded Webcam at index {cam_idx}")
            break
        test_cam.release()

    # 2. Open Real-Time Video Looper with 0.5x smooth playback speed
    video_path = "TEST.mp4" if os.path.exists("TEST.mp4") else ("test.mp4" if os.path.exists("test.mp4") else None)
    vid_looper = None
    video_speed = 0.5  # Slower, smoother speed for comprehensive detection
    if video_path:
        vid_looper = VideoLooper(video_path, speed_multiplier=video_speed)
        if vid_looper.is_opened():
            print(f"🎬 Opened Video file: {video_path} (Playing at {video_speed}x Speed, Looping)")
        else:
            print(f"❌ Failed to open video file: {video_path}")
    else:
        print("❌ 'TEST.mp4' / 'test.mp4' not found.")

    # Target resolution for each of the 4 quadrants (960x540 for 1920x1080 combined canvas)
    quad_w, quad_h = 960, 540

    webcam_heatmap = HeatmapAccumulator(quad_w, quad_h, internal_scale=0.5)
    video_heatmap = HeatmapAccumulator(quad_w, quad_h, internal_scale=0.5)
    
    colorbar_lut = get_colorbar_lut()
    show_blend = False
    is_fullscreen = True
    
    win_name = "RESQNET AI Thermal HUD - 4 Quadrants"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    
    print("\n" + "="*60)
    print("RESQNET 4-Quadrant HUD (Enhanced Video Detection & Looper)")
    print("  [TL] Normal Webcam        | [TR] Heatmap Webcam")
    print(f"  [BL] TEST.mp4 Video ({video_speed}x)  | [BR] Heatmap TEST.mp4 ({video_speed}x)")
    print("="*60)
    print("Controls:")
    print("  'c'     -> Clear accumulated heatmaps")
    print("  'h'     -> Toggle heatmap background blend (Black vs RGB)")
    print("  'f'     -> Toggle Fullscreen")
    print("  '-'/'[' -> Slow down video playback")
    print("  '+'/']' -> Speed up video playback")
    print("  ESC/'q' -> Exit\n")

    fps_buf = []

    try:
        while True:
            t0 = time.time()
            
            # --- A. Grab Webcam Frame (Non-blocking from background thread) ---
            cam_frame = None
            if cam is not None and cam.is_opened():
                ret_cam, raw_cam = cam.read()
                if ret_cam and raw_cam is not None:
                    cam_frame = cv2.resize(raw_cam, (quad_w, quad_h), interpolation=cv2.INTER_LINEAR)
            
            if cam_frame is None:
                cam_frame = np.zeros((quad_h, quad_w, 3), dtype=np.uint8)
                cv2.putText(cam_frame, "WEBCAM OFFLINE", (quad_w // 2 - 120, quad_h // 2), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # --- B. Grab Video Frame (Clock-synced with speed multiplier in loop) ---
            vid_frame = None
            if vid_looper is not None and vid_looper.is_opened():
                ret_vid, raw_vid = vid_looper.get_frame()
                if ret_vid and raw_vid is not None:
                    vid_frame = cv2.resize(raw_vid, (quad_w, quad_h), interpolation=cv2.INTER_LINEAR)
            
            if vid_frame is None:
                vid_frame = np.zeros((quad_h, quad_w, 3), dtype=np.uint8)
                cv2.putText(vid_frame, "TEST.MP4 UNAVAILABLE", (quad_w // 2 - 150, quad_h // 2), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # --- C. Batched GPU Inference (Higher sensitivity conf=0.20 for TEST.mp4) ---
            batch_results = run_batched_inference([cam_frame, vid_frame], model, 
                                                  webcam_heatmap.int_w, webcam_heatmap.int_h, device,
                                                  cam_conf=0.40, vid_conf=0.20)
            
            (cam_masks, cam_count), (vid_masks, vid_count) = batch_results

            # --- D. Render Quadrants ---
            # Top-Left: Normal Webcam Video
            tl_view = render_rgb_view(cam_frame, cam_count, "WEBCAM - RGB FEED")
            
            # Top-Right: Heatmap Webcam Video
            tr_view = render_thermal_view(cam_frame, cam_masks, webcam_heatmap, 
                                          cam_count, show_blend, colorbar_lut, "WEBCAM - THERMAL HEATMAP")
            
            # Bottom-Left: TEST.mp4 Video
            bl_view = render_rgb_view(vid_frame, vid_count, f"TEST.MP4 ({video_speed:.1f}x) - RGB FEED")
            
            # Bottom-Right: Heatmap of TEST.mp4
            br_view = render_thermal_view(vid_frame, vid_masks, video_heatmap, 
                                          vid_count, show_blend, colorbar_lut, f"TEST.MP4 ({video_speed:.1f}x) - THERMAL HEATMAP")

            # --- E. Assemble 2x2 Grid Canvas ---
            top_row = np.hstack([tl_view, tr_view])
            bottom_row = np.hstack([bl_view, br_view])
            full_canvas = np.vstack([top_row, bottom_row])

            # Central divider crosshair
            cv2.line(full_canvas, (quad_w, 0), (quad_w, quad_h * 2), (50, 50, 50), 2)
            cv2.line(full_canvas, (0, quad_h), (quad_w * 2, quad_h), (50, 50, 50), 2)

            # Calculate FPS and display badge
            elapsed = time.time() - t0
            fps_buf.append(elapsed)
            if len(fps_buf) > 30:
                fps_buf.pop(0)
            fps = 1.0 / (sum(fps_buf) / len(fps_buf) + 1e-9)

            fps_text = f"RESQNET HUD | {device_name} | {fps:.1f} FPS"
            cv2.rectangle(full_canvas, (quad_w - 200, 0), (quad_w + 200, 26), (15, 15, 15), -1)
            cv2.rectangle(full_canvas, (quad_w - 200, 0), (quad_w + 200, 26), (0, 140, 255), 1)
            cv2.putText(full_canvas, fps_text, (quad_w - 185, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1, cv2.LINE_AA)

            # Show fullscreen window
            cv2.imshow(win_name, full_canvas)

            # Handle Keyboard Input
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):  # ESC or q
                break
            elif key == ord('c'):
                webcam_heatmap.heat.fill(0)
                video_heatmap.heat.fill(0)
                print("🧹 All heatmaps cleared.")
            elif key == ord('h'):
                show_blend = not show_blend
                print(f"Heatmap background blend: {'ON (RGB Blend)' if show_blend else 'OFF (Black)'}")
            elif key == ord('f'):
                is_fullscreen = not is_fullscreen
                if is_fullscreen:
                    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                else:
                    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            elif key == ord('-') or key == ord('['):
                video_speed = max(0.1, round(video_speed - 0.1, 1))
                if vid_looper:
                    vid_looper.set_speed(video_speed)
                print(f"⏩ Video speed decreased to: {video_speed:.1f}x")
            elif key == ord('+') or key == ord('=') or key == ord(']'):
                video_speed = min(3.0, round(video_speed + 0.1, 1))
                if vid_looper:
                    vid_looper.set_speed(video_speed)
                print(f"⏩ Video speed increased to: {video_speed:.1f}x")

    finally:
        if cam is not None:
            cam.release()
        if vid_looper is not None:
            vid_looper.release()
        cv2.destroyAllWindows()
        print("🛑 Streams released. Windows closed.")

if __name__ == "__main__":
    main()
