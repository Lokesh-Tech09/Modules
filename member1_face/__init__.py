"""
Module 1: Face Identification
Provides face detection, embedding extraction, and candidate matching.
Original implementation by Mayur (mayur-8631/face_recognition_match).
"""

from .adapter import M1Result, run_face_identification
from .capture_webcam import capture_from_camera, mock_capture

__all__ = [
    "run_face_identification",
    "M1Result",
    "capture_from_camera",
    "mock_capture",
]
