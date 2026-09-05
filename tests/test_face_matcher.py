"""
Tests for FaceMatcher and Score Calibration (Module 2: Claimed-Profile Verification v2).
"""

from unittest.mock import MagicMock
import numpy as np
import pytest

from member2_verify.config import VerificationConfig
from member2_verify.exceptions import InvalidInputError
from member2_verify.face_matcher import (
    BaseFaceEngine,
    FaceMatcher,
    calibrate_similarity_score,
)
from member2_verify.models import FaceDetection
from member2_verify.utils import compute_cosine_similarity


class MockFaceEngine(BaseFaceEngine):
    """Mock engine allowing arbitrary face detections to be returned."""

    def __init__(self, detections: list):
        self.detections = detections

    def detect_and_embed(self, image_path: str):
        return self.detections


def test_score_calibration_monotonic_mapping():
    """Verify calibrated confidence mapping behavior."""
    # At midpoint (0.65), calibrated score is exactly 0.50
    cal_mid = calibrate_similarity_score(0.65, midpoint=0.65, steepness=12.0)
    assert abs(cal_mid - 0.50) < 0.01

    # High similarity (> 0.95) maps to very high confidence (> 0.95)
    cal_high = calibrate_similarity_score(0.95, midpoint=0.65, steepness=12.0)
    assert cal_high > 0.95

    # Low similarity (< 0.30) maps to very low confidence (< 0.05)
    cal_low = calibrate_similarity_score(0.30, midpoint=0.65, steepness=12.0)
    assert cal_low < 0.05

    # Monotonicity check
    scores = [0.1, 0.4, 0.65, 0.8, 0.98]
    calibrated = [calibrate_similarity_score(s) for s in scores]
    assert calibrated == sorted(calibrated)


def test_single_face_match_with_calibration():
    """Verify comparison returns both raw similarity and calibrated confidence."""
    target_vec = [1.0] + [0.0] * 511
    cand_vec = [0.99] + [0.01] * 511
    cand_vec = (np.array(cand_vec) / np.linalg.norm(cand_vec)).tolist()

    mock_engine = MockFaceEngine([
        FaceDetection(bounding_box=[10, 10, 60, 60], embedding=cand_vec, confidence=0.95)
    ])

    config = VerificationConfig(SIMILARITY_THRESHOLD=0.65)
    matcher = FaceMatcher(config=config, face_engine=mock_engine)

    is_match, raw_sim, cal_conf, low_conf, best_face = matcher.compare_candidate_image(
        candidate_image_path="dummy.jpg",
        target_embedding=target_vec,
    )

    assert is_match is True
    assert raw_sim >= 0.65
    assert cal_conf > 0.90
    assert low_conf is False
    assert best_face is not None


def test_low_confidence_detection_flag():
    """Verify that low detection confidence or small face size triggers low_confidence_detection."""
    target_vec = [1.0] + [0.0] * 511
    cand_vec = [1.0] + [0.0] * 511

    # Small bounding box (20x20) or low confidence (0.5)
    mock_engine = MockFaceEngine([
        FaceDetection(bounding_box=[10, 10, 25, 25], embedding=cand_vec, confidence=0.50)
    ])

    config = VerificationConfig(SIMILARITY_THRESHOLD=0.65, LOW_CONFIDENCE_DETECTION_THRESHOLD=0.70)
    matcher = FaceMatcher(config=config, face_engine=mock_engine)

    is_match, raw_sim, cal_conf, low_conf, best_face = matcher.compare_candidate_image(
        candidate_image_path="small_face.jpg",
        target_embedding=target_vec,
    )

    assert is_match is True
    assert low_conf is True


def test_multiple_faces_selects_best_match_v2():
    """Verify multi-face selection picks highest similarity."""
    target_vec = [1.0] + [0.0] * 511

    face1_vec = [0.2] + [0.5] * 511
    face1_vec = (np.array(face1_vec) / np.linalg.norm(face1_vec)).tolist()

    face2_vec = [0.98] + [0.01] * 511
    face2_vec = (np.array(face2_vec) / np.linalg.norm(face2_vec)).tolist()

    mock_engine = MockFaceEngine([
        FaceDetection(bounding_box=[0, 0, 50, 50], embedding=face1_vec, confidence=0.9),
        FaceDetection(bounding_box=[100, 100, 50, 50], embedding=face2_vec, confidence=0.9),
    ])

    matcher = FaceMatcher(face_engine=mock_engine)
    is_match, raw_sim, cal_conf, low_conf, best_face = matcher.compare_candidate_image(
        candidate_image_path="group.jpg",
        target_embedding=target_vec,
    )

    assert is_match is True
    assert best_face.face_index == 1
    assert raw_sim > 0.90
