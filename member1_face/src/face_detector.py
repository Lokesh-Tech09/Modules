"""Face Detector Module using InsightFace.

This module is responsible for:
- Initializing the InsightFace detection model (buffalo_l).
- Detecting all human faces in an input image.
- Selecting the primary (best) face based on the largest bounding box area.
- Extracting bounding boxes, facial landmarks, and detection confidence scores.
- Drawing stylish, high-contrast bounding boxes and labels on images.
- Saving and displaying annotated images.
- Handling edge cases (no faces detected, corrupted images, multiple faces).
"""

import os
from typing import Any, List, Optional, Tuple, Union
import cv2
import numpy as np
from insightface.app import FaceAnalysis


class FaceDetector:
    """Detects human faces in images using InsightFace's FaceAnalysis."""

    def __init__(
        self,
        model_name: str = "buffalo_l",
        det_size: Tuple[int, int] = (640, 640),
        ctx_id: int = -1,  # -1 for CPU, >=0 for GPU
        providers: Optional[List[str]] = None,
    ):
        """Initialize InsightFace FaceAnalysis detector.

        Args:
            model_name: Name of the InsightFace model pack (default: 'buffalo_l').
            det_size: Input resolution tuple (width, height) for detector.
            ctx_id: -1 for CPU execution, 0+ for GPU device ID.
            providers: ONNX execution providers list. Defaults to CPUExecutionProvider.
        """
        if providers is None:
            # Default to CPUExecutionProvider for maximum cross-platform reliability
            providers = ["CPUExecutionProvider"]

        print(f"[FaceDetector] Initializing InsightFace model '{model_name}' on CPU...")
        try:
            self.app = FaceAnalysis(name=model_name, providers=providers)
            self.app.prepare(ctx_id=ctx_id, det_size=det_size)
            self.det_size = det_size
            print("[FaceDetector] Model initialized successfully.")
        except Exception as e:
            print(f"[FaceDetector] Error initializing FaceAnalysis model: {e}")
            raise RuntimeError(f"Failed to initialize FaceAnalysis with model '{model_name}': {e}")

    def load_image(self, image_input: Union[str, np.ndarray]) -> np.ndarray:
        """Load an image from a filepath or validate an existing numpy image array.

        Args:
            image_input: Filepath string or existing numpy BGR image array.

        Returns:
            np.ndarray: Valid BGR image array.

        Raises:
            FileNotFoundError: If the image file does not exist.
            ValueError: If the image file cannot be read or is empty/corrupt.
            TypeError: If image_input is neither a string nor a numpy ndarray.
        """
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Image not found at path: '{image_input}'")
            image = cv2.imread(image_input)
            if image is None or image.size == 0:
                raise ValueError(f"Failed to read image at '{image_input}'. File may be corrupted or invalid.")
            return image
        elif isinstance(image_input, np.ndarray):
            if image_input.size == 0:
                raise ValueError("Provided image numpy array is empty.")
            return image_input
        else:
            raise TypeError(f"image_input must be a file path string or numpy.ndarray, got {type(image_input)}.")

    def detect_faces(self, image_input: Union[str, np.ndarray]) -> List[Any]:
        """Detect all faces in the provided image.

        Args:
            image_input: Image file path or BGR image numpy array.

        Returns:
            List of detected face objects with attributes (bbox, kps, det_score, embedding).
            Returns an empty list if no faces are detected.
        """
        image = self.load_image(image_input)
        faces = self.app.get(image)
        return faces if faces is not None else []

    def get_primary_face(self, faces: List[Any]) -> Optional[Any]:
        """Select the primary (best) face based on largest bounding box area.

        If multiple faces are detected, the most prominent / foreground face
        is selected by computing bounding box area (width * height).

        Args:
            faces: List of detected InsightFace face objects.

        Returns:
            The face object with the largest bounding box area, or None if list is empty.
        """
        if not faces:
            return None

        def bbox_area(face: Any) -> float:
            bbox = face.bbox
            width = max(0.0, float(bbox[2] - bbox[0]))
            height = max(0.0, float(bbox[3] - bbox[1]))
            return width * height

        # Sort descending by bounding box area
        sorted_faces = sorted(faces, key=bbox_area, reverse=True)
        return sorted_faces[0]

    def draw_bounding_boxes(
        self,
        image_input: Union[str, np.ndarray],
        faces: List[Any],
        box_color: Tuple[int, int, int] = (0, 230, 115),  # Vibrant emerald green in BGR
        show_score: bool = True,
        show_landmarks: bool = True,
        highlight_primary: bool = True,
    ) -> np.ndarray:
        """Draw bounding boxes, confidence tags, and landmarks on detected faces.

        Args:
            image_input: Original image (path or array).
            faces: List of detected face objects.
            box_color: BGR color tuple for the bounding box.
            show_score: Whether to display detection confidence score.
            show_landmarks: Whether to draw facial landmarks.
            highlight_primary: Highlight the largest face with a distinct primary tag.

        Returns:
            Annotated BGR image as numpy array.
        """
        image = self.load_image(image_input).copy()
        if not faces:
            return image

        primary_face = self.get_primary_face(faces) if highlight_primary else None

        for idx, face in enumerate(faces):
            is_primary = (face is primary_face)
            bbox = face.bbox.astype(int)
            x1, y1, x2, y2 = bbox

            # Ensure coordinates are within image bounds
            h, w = image.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)

            color = (0, 230, 115) if is_primary else (230, 180, 0)  # Green for primary, Cyan/Blue for others

            # Draw main bounding box
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

            # Draw corner accent lines for high-tech aesthetic
            corner_len = min(20, max(6, (x2 - x1) // 5), max(6, (y2 - y1) // 5))
            thick = 3
            # Top-left
            cv2.line(image, (x1, y1), (x1 + corner_len, y1), color, thick)
            cv2.line(image, (x1, y1), (x1, y1 + corner_len), color, thick)
            # Top-right
            cv2.line(image, (x2, y1), (x2 - corner_len, y1), color, thick)
            cv2.line(image, (x2, y1), (x2, y1 + corner_len), color, thick)
            # Bottom-left
            cv2.line(image, (x1, y2), (x1 + corner_len, y2), color, thick)
            cv2.line(image, (x1, y2), (x1, y2 - corner_len), color, thick)
            # Bottom-right
            cv2.line(image, (x2, y2), (x2 - corner_len, y2), color, thick)
            cv2.line(image, (x2, y2), (x2, y2 - corner_len), color, thick)

            # Draw 5 facial landmarks (eyes, nose, mouth corners)
            if show_landmarks and hasattr(face, "kps") and face.kps is not None:
                for kp in face.kps:
                    kx, ky = int(kp[0]), int(kp[1])
                    cv2.circle(image, (kx, ky), 3, (0, 215, 255), -1, cv2.LINE_AA)
                    cv2.circle(image, (kx, ky), 4, (0, 0, 0), 1, cv2.LINE_AA)

            # Build label
            score = getattr(face, "det_score", 0.0)
            tag_prefix = "PRIMARY FACE" if is_primary else f"Face #{idx + 1}"
            if show_score:
                label = f"{tag_prefix} ({score * 100:.1f}%)"
            else:
                label = tag_prefix

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.50
            font_thickness = 1
            (text_w, text_h), _ = cv2.getTextSize(label, font, font_scale, font_thickness)

            tag_y1 = max(0, y1 - text_h - 8)
            tag_y2 = y1
            tag_x2 = min(w, x1 + text_w + 10)

            # Background rectangle for text
            cv2.rectangle(image, (x1, tag_y1), (tag_x2, tag_y2), color, -1)
            # High-contrast dark text
            cv2.putText(
                image,
                label,
                (x1 + 4, y1 - 4),
                font,
                font_scale,
                (0, 0, 0),
                font_thickness,
                cv2.LINE_AA,
            )

        return image

    def save_annotated_image(self, image: np.ndarray, output_path: str) -> str:
        """Save the annotated image to disk.

        Args:
            image: Annotated image array.
            output_path: Destination file path.

        Returns:
            The resolved saved file path.
        """
        abs_output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)
        success = cv2.imwrite(abs_output_path, image)
        if not success:
            raise IOError(f"Failed to write image to '{abs_output_path}'.")
        print(f"[FaceDetector] Saved annotated image to: {abs_output_path}")
        return abs_output_path

    def display_bounding_box(
        self,
        image: np.ndarray,
        window_title: str = "Detected Face",
        wait_ms: int = 0,
    ) -> None:
        """Display an annotated image in an OpenCV GUI window.

        Args:
            image: Image numpy array.
            window_title: Window title.
            wait_ms: Milliseconds to wait for key press (0 = wait indefinitely).
        """
        try:
            cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
            cv2.imshow(window_title, image)
            cv2.waitKey(wait_ms)
            cv2.destroyWindow(window_title)
        except Exception as e:
            print(f"[FaceDetector] Notice: OpenCV GUI display skipped ({e}).")
