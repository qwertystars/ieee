"""
Synthetic Gray16 frame generator.

Used as a stand-in when no real thermal camera / Gray16 files exist.
Produces animated frames that look like a genuine Gray16 stream.
"""
import cv2
import numpy as np


HEIGHT, WIDTH = 480, 640


def _gaussian(cx: float, cy: float, sigma: float,
              amp: float, h: int = HEIGHT, w: int = WIDTH) -> np.ndarray:
    xs = np.linspace(0, w - 1, w)
    ys = np.linspace(0, h - 1, h)
    X, Y = np.meshgrid(xs, ys)
    return amp * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * sigma ** 2))


def make_gray16_frame(frame_index: int = 0,
                      noise_level: float = 120.0) -> np.ndarray:
    """
    Return a synthetic uint16 Gray16 frame with animated heat sources.

    Range: 0–65535, mapped to -20°C – 150°C by the temperature module.
    """
    t = frame_index * 0.05          # time factor

    # Background ~20 °C  → pixel ≈ (20 - (-20)) / 170 * 65535 ≈ 15420
    # Hot spot   ~80 °C  → pixel ≈ (80 + 20) / 170 * 65535 ≈ 38550
    # Very hot   ~120 °C → pixel ≈ (120 + 20) / 170 * 65535 ≈ 54000

    base = np.full((HEIGHT, WIDTH), 15420.0, dtype=np.float64)

    # Three animated heat blobs
    cx1 = WIDTH  * (0.3 + 0.15 * np.sin(t))
    cy1 = HEIGHT * (0.4 + 0.12 * np.cos(t * 0.7))
    base += _gaussian(cx1, cy1, sigma=60, amp=22000)

    cx2 = WIDTH  * (0.65 + 0.10 * np.cos(t * 1.3))
    cy2 = HEIGHT * (0.55 + 0.10 * np.sin(t * 0.9))
    base += _gaussian(cx2, cy2, sigma=40, amp=14000)

    cx3 = WIDTH  * 0.5
    cy3 = HEIGHT * (0.2 + 0.08 * np.sin(t * 2.1))
    base += _gaussian(cx3, cy3, sigma=25, amp=8000)

    # Mild sensor noise
    noise = np.random.normal(0, noise_level, (HEIGHT, WIDTH))
    base += noise

    frame = np.clip(base, 0, 65535).astype(np.uint16)
    return frame


def generate_sequence(folder: str, n_frames: int = 30) -> None:
    """Save n_frames synthetic Gray16 PNGs into *folder*."""
    import os
    os.makedirs(folder, exist_ok=True)
    for i in range(n_frames):
        frame = make_gray16_frame(i)
        path = os.path.join(folder, f"frame_{i:04d}.png")
        cv2.imwrite(path, frame)
    print(f"[synthetic] Saved {n_frames} Gray16 frames → {folder}")
