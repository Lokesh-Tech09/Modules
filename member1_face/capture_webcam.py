"""
VeriFace — Module 1 Live Webcam Input
======================================
Captures real-time camera feed, detects face, crops/saves to input folder,
and optionally triggers the end-to-end VeriFace verification pipeline.

Usage:
    python member1_face/capture_webcam.py
    python member1_face/capture_webcam.py --run-pipeline
    python member1_face/capture_webcam.py --countdown 3 --output my_face.jpg
    python member1_face/capture_webcam.py --mock  # Headless / simulation mode
"""

import argparse
import os
import sys
import time
from typing import Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "member1_face", "data", "input")
DEFAULT_OUTPUT_PATH = os.path.join(DEFAULT_OUTPUT_DIR, "live_capture.jpg")


def capture_from_camera(
    camera_index: int = 0,
    output_path: str = DEFAULT_OUTPUT_PATH,
    countdown: int = 0,
    mirror: bool = True,
) -> Optional[str]:
    """
    Open webcam, display live feed with face detection bounding box,
    and save the frame when SPACE is pressed or countdown completes.
    """
    try:
        import cv2
    except ImportError:
        print("[ERROR] opencv-python is not installed. Please install via: pip install opencv-python")
        return None

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Initialize Haar Cascade for fast real-time preview bounding box
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[ERROR] Could not access camera index {camera_index}.")
        print("        Ensure camera permissions are enabled, or use --mock for simulated input.")
        return None

    # Set camera resolution (720p preferred)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("\n" + "=" * 60)
    print("  VERIFACE — WEBCAM LIVE CAPTURE")
    print("=" * 60)
    print("  Controls:")
    print("    [SPACE]   — Capture image")
    print("    [C]       — Start 3-second countdown capture")
    print("    [Q / ESC] — Quit without saving")
    print("=" * 60 + "\n")

    captured_frame = None
    countdown_start = None

    if countdown > 0:
        countdown_start = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to read frame from webcam.")
            break

        if mirror:
            frame = cv2.flip(frame, 1)

        display_frame = frame.copy()
        h, w = display_frame.shape[:2]

        # Convert to grayscale for quick Haar detector
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
        )

        face_count = len(faces)
        color = (0, 255, 0) if face_count == 1 else (0, 165, 255)

        for (x, y, fw, fh) in faces:
            # Draw targeting corner brackets
            cv2.rectangle(display_frame, (x, y), (x + fw, y + fh), color, 2)
            cv2.putText(
                display_frame,
                f"Face ({fw}x{fh})",
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )

        # Status overlay top bar
        cv2.rectangle(display_frame, (0, 0), (w, 45), (20, 20, 20), -1)
        status_text = f"Faces detected: {face_count} | Press [SPACE] to capture | [Q] to quit"
        cv2.putText(
            display_frame,
            status_text,
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )

        # Handle countdown
        if countdown_start is not None:
            remaining = countdown - int(time.time() - countdown_start)
            if remaining > 0:
                cv2.putText(
                    display_frame,
                    str(remaining),
                    (w // 2 - 30, h // 2 + 30),
                    cv2.FONT_HERSHEY_DUPLEX,
                    3.0,
                    (0, 255, 255),
                    4,
                )
            else:
                captured_frame = frame
                break

        cv2.imshow("VeriFace — Live Identity Capture", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):  # Q or ESC
            print("[INFO] Capture cancelled by user.")
            break
        elif key == ord(' '):  # SPACE
            captured_frame = frame
            break
        elif key in (ord('c'), ord('C')):  # Start 3s countdown
            countdown_start = time.time()
            countdown = 3

    cap.release()
    cv2.destroyAllWindows()

    if captured_frame is not None:
        cv2.imwrite(output_path, captured_frame)
        print(f"[SUCCESS] Saved live capture to: {output_path}")
        return output_path

    return None


def mock_capture(output_path: str = DEFAULT_OUTPUT_PATH) -> str:
    """Simulate webcam capture by copying or generating a test image."""
    import shutil
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sample_candidate = os.path.join(PROJECT_ROOT, "member1_face", "data", "candidates", "test_img1.jpg")
    if os.path.exists(sample_candidate):
        shutil.copyfile(sample_candidate, output_path)
    else:
        # Generate simple synthetic image with PIL
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (640, 480), color=(73, 109, 137))
        d = ImageDraw.Draw(img)
        d.ellipse([240, 160, 400, 320], fill=(255, 200, 150))
        img.save(output_path)
    print(f"[MOCK CAPTURE] Simulated camera capture saved to: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="VeriFace Live Webcam Capture")
    parser.add_argument("--camera", type=int, default=0, help="Camera device index (default: 0)")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT_PATH, help="Output image file path")
    parser.add_argument("--countdown", "-c", type=int, default=0, help="Countdown seconds before capture")
    parser.add_argument("--mock", action="store_true", help="Simulate webcam capture without hardware")
    parser.add_argument("--run-pipeline", action="store_true", help="Automatically trigger full VeriFace pipeline on capture")
    parser.add_argument("--tamper-test", action="store_true", help="Run tamper test after pipeline")
    parser.add_argument("--demo-anchor", action="store_true", help="Simulate verified anchoring on captured image")
    args = parser.parse_args()

    saved_path = None
    if args.mock:
        saved_path = mock_capture(args.output)
    else:
        saved_path = capture_from_camera(
            camera_index=args.camera,
            output_path=args.output,
            countdown=args.countdown,
        )
        if saved_path is None:
            print("[INFO] Falling back to simulated capture...")
            saved_path = mock_capture(args.output)

    if saved_path and args.run_pipeline:
        print(f"\n[INFO] Triggering VeriFace pipeline for captured image: {saved_path}")
        import subprocess
        cmd = [
            sys.executable,
            os.path.join(PROJECT_ROOT, "main.py"),
            "--image", saved_path,
        ]
        if args.tamper_test:
            cmd.append("--tamper-test")
        if args.demo_anchor:
            cmd.append("--demo-anchor")
        subprocess.run(cmd)


if __name__ == "__main__":
    main()
