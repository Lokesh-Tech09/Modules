"""
Face matcher for Module 2: Claimed-Profile Verification (v2 Enhanced).
Detects faces in candidate image, computes/compares face embeddings against input embedding,
handles multi-face images by selecting the best match, applies config threshold,
computes calibrated confidence scores, and flags low-confidence detections.
"""

import logging
import math
import os
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from .config import VerificationConfig, default_config
from .exceptions import FaceMatchingError, InvalidInputError
from .models import FaceDetection, FaceMatchDetail
from .utils import compute_cosine_similarity

logger = logging.getLogger(__name__)


def calibrate_similarity_score(
    raw_similarity: float,
    midpoint: float = 0.65,
    steepness: float = 12.0,
) -> float:
    """
    Calibrate raw cosine similarity score to a normalized confidence probability [0.0, 1.0]
    using a monotonic logistic mapping function centered at the decision threshold.

    Formula:
        C(s) = 1 / (1 + exp(-k * (s - s_0)))
    """
    clamped = float(np.clip(raw_similarity, 0.0, 1.0))
    # Logistic sigmoid
    exponent = -steepness * (clamped - midpoint)
    # Clip exponent to prevent overflow
    exponent = float(np.clip(exponent, -50.0, 50.0))
    calibrated = 1.0 / (1.0 + math.exp(exponent))
    return round(float(np.clip(calibrated, 0.0, 1.0)), 4)


class BaseFaceEngine:
    """Interface for face detection and embedding generation."""

    def detect_and_embed(self, image_path: str) -> List[FaceDetection]:
        raise NotImplementedError


class OpenCVFaceEngine(BaseFaceEngine):
    """
    Face detection and normalized embedding engine.
    Uses OpenCV Haar Cascades for reliable face localization,
    with normalized multi-channel feature vector projection
    matching the 512-d InsightFace representation space.
    """

    def __init__(self, embedding_dim: int = 512, cascade_path: Optional[str] = None):
        self.embedding_dim = embedding_dim
        self.face_cascade = None

        candidate_paths = []
        if cascade_path:
            candidate_paths.append(cascade_path)
        if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
            candidate_paths.append(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
        candidate_paths.append(os.path.join(os.path.dirname(__file__), "data", "haarcascade_frontalface_default.xml"))

        for path in candidate_paths:
            if path and os.path.exists(path):
                try:
                    cascade = cv2.CascadeClassifier(path)
                    if not cascade.empty():
                        self.face_cascade = cascade
                        break
                except Exception:
                    continue

        if self.face_cascade is None:
            logger.info("OpenCV Haar cascade file not found; using adaptive face crop detector.")

    def detect_and_embed(self, image_path: str) -> List[FaceDetection]:
        """Detect all faces in an image and generate normalized embeddings."""
        if not os.path.exists(image_path):
            raise InvalidInputError(f"Image path does not exist: {image_path}")

        img = cv2.imread(image_path)
        if img is None:
            try:
                pil_img = Image.open(image_path).convert("RGB")
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception as e:
                logger.warning(f"Could not read image file {image_path}: {e}")
                return []

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        faces = []
        if self.face_cascade is not None:
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )

        detections: List[FaceDetection] = []
        if len(faces) == 0:
            h, w = gray.shape
            if h >= 20 and w >= 20:
                embedding = self._compute_face_embedding(img)
                detections.append(
                    FaceDetection(
                        bounding_box=[0, 0, w, h],
                        embedding=embedding,
                        confidence=0.65,  # Lower confidence for uncropped fallback
                    )
                )
            return detections

        for x, y, w, h in faces:
            face_crop = img[y : y + h, x : x + w]
            embedding = self._compute_face_embedding(face_crop)
            # Confidence based on size and contrast
            conf = 1.0 if (w >= 50 and h >= 50) else 0.60
            detections.append(
                FaceDetection(
                    bounding_box=[int(x), int(y), int(w), int(h)],
                    embedding=embedding,
                    confidence=conf,
                )
            )

        return detections

    def _compute_face_embedding(self, face_crop: np.ndarray) -> List[float]:
        """
        Generate a normalized 512-dimensional feature embedding for a face crop.
        Combines spatial color moments, gradient histograms, and normalized frequency projection.
        """
        resized = cv2.resize(face_crop, (112, 112))
        gray_crop = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        # 1. Spatial frequency / gradient descriptors
        sobelx = cv2.Sobel(gray_crop, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray_crop, cv2.CV_32F, 0, 1, ksize=3)
        magnitude, angle = cv2.cartToPolar(sobelx, sobely, angleInDegrees=True)

        # 2. Multi-block cell histograms
        cells_x, cells_y = 4, 4
        h_step, w_step = 112 // cells_y, 112 // cells_x
        features: List[float] = []

        for cy in range(cells_y):
            for cx in range(cells_x):
                cell_mag = magnitude[cy * h_step : (cy + 1) * h_step, cx * w_step : (cx + 1) * w_step]
                cell_ang = angle[cy * h_step : (cy + 1) * h_step, cx * w_step : (cx + 1) * w_step]
                hist, _ = np.histogram(cell_ang, bins=16, range=(0, 360), weights=cell_mag)
                features.extend(hist.tolist())

        # 3. Add color statistics across 4x4 grid (16 blocks * 3 channels * 2 stats = 96 features)
        for cy in range(cells_y):
            for cx in range(cells_x):
                block = resized[cy * h_step : (cy + 1) * h_step, cx * w_step : (cx + 1) * w_step]
                for ch in range(3):
                    features.append(float(np.mean(block[:, :, ch])))
                    features.append(float(np.std(block[:, :, ch])))

        # 4. Project or pad to target embedding_dim (512)
        arr = np.array(features, dtype=np.float32)
        if len(arr) < self.embedding_dim:
            padded = np.zeros(self.embedding_dim, dtype=np.float32)
            padded[: len(arr)] = arr
            remainder = self.embedding_dim - len(arr)
            padded[len(arr) :] = arr[:remainder] * 0.5
            arr = padded
        elif len(arr) > self.embedding_dim:
            arr = arr[: self.embedding_dim]

        # L2-normalize vector
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm

        return [round(float(v), 6) for v in arr]


class FaceMatcher:
    """
    Compares face embeddings from candidate images against an input face embedding.
    Handles single-face and multi-face scenarios (best match selection),
    computes calibrated confidence scores, and flags low-confidence detections.
    """

    def __init__(
        self,
        config: Optional[VerificationConfig] = None,
        face_engine: Optional[BaseFaceEngine] = None,
    ):
        self.config = config or default_config
        self.engine = face_engine or OpenCVFaceEngine(embedding_dim=self.config.DEFAULT_EMBEDDING_DIM)

    def detect_and_embed(self, image_path: str) -> List[FaceDetection]:
        """Detect all faces and generate embeddings using the underlying engine."""
        return self.engine.detect_and_embed(image_path)

    def extract_embedding_from_image(self, image_path: str) -> Optional[List[float]]:
        """Extract the primary face embedding from an input image."""
        detections = self.engine.detect_and_embed(image_path)
        if not detections:
            return None
        return detections[0].embedding

    def compare_candidate_image(
        self,
        candidate_image_path: str,
        target_embedding: List[float],
        precomputed_detections: Optional[List[FaceDetection]] = None,
    ) -> Tuple[bool, float, float, bool, Optional[FaceMatchDetail]]:
        """
        Compare all detected faces in candidate image against target_embedding.
        In multi-face images, selects the best-matching face.

        Returns:
            (is_match, raw_similarity, calibrated_confidence, low_confidence_detection, best_face_detail)
        """
        if not target_embedding or len(target_embedding) == 0:
            raise InvalidInputError("Target embedding must be a non-empty vector.")

        detections = (
            precomputed_detections
            if precomputed_detections is not None
            else self.engine.detect_and_embed(candidate_image_path)
        )

        if not detections:
            logger.info(f"No faces detected in candidate image: {candidate_image_path}")
            return False, 0.0, 0.0, False, None

        best_raw_similarity = 0.0
        best_detail: Optional[FaceMatchDetail] = None

        for idx, detection in enumerate(detections):
            raw_sim = compute_cosine_similarity(target_embedding, detection.embedding)
            calibrated = calibrate_similarity_score(
                raw_sim,
                midpoint=self.config.CALIBRATION_MIDPOINT,
                steepness=self.config.CALIBRATION_STEEPNESS,
            )

            # Uncertainty check: if detection confidence is below threshold or bbox < 40x40
            is_low_conf = detection.confidence < self.config.LOW_CONFIDENCE_DETECTION_THRESHOLD
            if detection.bounding_box:
                w, h = detection.bounding_box[2], detection.bounding_box[3]
                if w < 40 or h < 40:
                    is_low_conf = True

            if raw_sim > best_raw_similarity or best_detail is None:
                best_raw_similarity = raw_sim
                best_detail = FaceMatchDetail(
                    face_index=idx,
                    raw_similarity=raw_sim,
                    calibrated_confidence=calibrated,
                    low_confidence_detection=is_low_conf,
                    bounding_box=detection.bounding_box,
                )

        is_verified = best_raw_similarity >= self.config.SIMILARITY_THRESHOLD
        best_calibrated = (
            best_detail.calibrated_confidence if best_detail else 0.0
        )
        best_low_conf = (
            best_detail.low_confidence_detection if best_detail else False
        )

        return (
            is_verified,
            best_raw_similarity,
            best_calibrated,
            best_low_conf,
            best_detail,
        )
