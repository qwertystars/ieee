#!/usr/bin/env python3
"""
Thermal Imaging System – OpenCV Edition
========================================
Four methods from the "Infrared Vision Basics" course, implemented with
Python + OpenCV.  Run this file and choose a method from the menu.

Usage
-----
    python thermal_opencv.py              # interactive menu
    python thermal_opencv.py --method 1  # jump straight to Method 1
    python thermal_opencv.py --method 3 --frames path/to/frames/
    python thermal_opencv.py --method 4 --camera 0
    python thermal_opencv.py --method 2 --image path/to/gray16.png
"""
import argparse
import sys
import os
import cv2

# ---------------------------------------------------------------------------
# Make sure the package is importable regardless of CWD
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

MENU = """
╔══════════════════════════════════════════════════════════════╗
║       THERMAL IMAGING SYSTEM  –  OpenCV / Python            ║
╠══════════════════════════════════════════════════════════════╣
║  1 │ Understand Image Formats  (Gray8 vs Gray16)            ║
║  2 │ Measure from a Thermal Image  (static)                 ║
║  3 │ Measure from a Thermal Video  (image sequence)         ║
║  4 │ Measure from a Real-time Thermal Camera                ║
║  0 │ Exit                                                   ║
╚══════════════════════════════════════════════════════════════╝
"""

COLORMAPS = {
    "inferno": cv2.COLORMAP_INFERNO,
    "jet":     cv2.COLORMAP_JET,
    "hot":     cv2.COLORMAP_HOT,
    "magma":   cv2.COLORMAP_MAGMA,
    "rainbow": cv2.COLORMAP_RAINBOW,
}


def parse_args():
    p = argparse.ArgumentParser(description="Thermal Imaging System")
    p.add_argument("--method",  type=int, choices=[1, 2, 3, 4], default=None)
    p.add_argument("--image",   type=str, default=None,
                   help="Path to a Gray16 PNG/TIFF for Method 2")
    p.add_argument("--frames",  type=str, default=None,
                   help="Folder of Gray16 frames for Method 3")
    p.add_argument("--camera",  default=0,
                   help="Camera index or RTSP URL for Method 4 (default: 0)")
    p.add_argument("--colormap", type=str, default="inferno",
                   choices=list(COLORMAPS.keys()),
                   help="False-colour palette (default: inferno)")
    p.add_argument("--alert",   type=float, default=60.0,
                   help="Temp threshold (C) for Method 4 alert border")
    return p.parse_args()


def run_method(method: int, args) -> None:
    cmap = COLORMAPS.get(args.colormap, cv2.COLORMAP_INFERNO)

    if method == 1:
        from thermal_cv.method1_formats import run
        run(image_path=args.image, colormap=cmap)

    elif method == 2:
        from thermal_cv.method2_static_image import run
        run(image_path=args.image, colormap=cmap)

    elif method == 3:
        from thermal_cv.method3_video_sequence import run
        run(frames_folder=args.frames, colormap=cmap)

    elif method == 4:
        from thermal_cv.method4_live_camera import run
        cam = args.camera
        # Allow integer camera indices
        try:
            cam = int(cam)
        except (ValueError, TypeError):
            pass
        run(camera_source=cam, colormap=cmap, alert_threshold_c=args.alert)


def interactive_menu(args) -> None:
    while True:
        print(MENU)
        choice = input("Select method [0–4]: ").strip()
        if choice == "0":
            print("Bye!")
            break
        if choice in ("1", "2", "3", "4"):
            if choice == "4":
                cam_input = input(f"Enter camera index or URL [default {args.camera}]: ").strip()
                if cam_input:
                    # Update args.camera temporarily for this run
                    args.camera = cam_input
            run_method(int(choice), args)
        else:
            print("Invalid choice – try again.")


def main():
    args = parse_args()
    if args.method is not None:
        run_method(args.method, args)
    else:
        interactive_menu(args)


if __name__ == "__main__":
    main()
