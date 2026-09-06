"""
Module 1 Adapter — Integration bridge between Module 1 (Face Identification)
and the downstream pipeline (Module 2 + Module 3).

Responsibilities:
- Accept an input image path.
- Run the real InsightFace detector and encoder (unchanged from original).
- Run candidate matching against the local candidate gallery.
- Return a structured M1Result dict suitable for M2 handoff.

The core FaceDetector, FaceEncoder, FaceMatcher, and CandidateMatcher classes
are NOT modified — only wrapped here.
"""

import os
import sys
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Ensure member1_face/src is importable regardless of CWD
_MODULE1_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULE1_DIR not in sys.path:
    sys.path.insert(0, _MODULE1_DIR)


class M1Result:
    """Structured result from Module 1 face identification."""

    def __init__(
        self,
        face_detected: bool,
        candidate: Optional[str],
        candidate_path: Optional[str],
        similarity: float,
        match: bool,
        status: str,
        face_embedding: Optional[List[float]],
        all_matches: Optional[List[Dict[str, Any]]] = None,
        error: Optional[str] = None,
    ):
        self.face_detected = face_detected
        self.candidate = candidate
        self.candidate_path = candidate_path
        self.similarity = similarity
        self.match = match
        self.status = status
        self.face_embedding = face_embedding  # 512-d list[float]
        self.all_matches = all_matches or []
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face_detected": self.face_detected,
            "candidate": self.candidate,
            "candidate_path": self.candidate_path,
            "similarity": round(self.similarity, 4),
            "match": self.match,
            "status": self.status,
            "face_embedding": self.face_embedding,
            "all_matches": self.all_matches,
            "error": self.error,
        }

    def __repr__(self):
        return (
            f"M1Result(face_detected={self.face_detected}, candidate={self.candidate!r}, "
            f"similarity={self.similarity:.4f}, match={self.match}, status={self.status!r})"
        )


def run_face_identification(
    image_path: str,
    candidates_dir: Optional[str] = None,
    threshold: float = 0.50,
    model_name: str = "buffalo_l",
) -> M1Result:
    """
    Run the full Module 1 face identification pipeline on an input image.

    Steps:
    1. Validate input image exists.
    2. Initialize FaceDetector (InsightFace buffalo_l).
    3. Detect faces in the input image.
    4. Extract 512-d L2-normalized embedding from the primary face.
    5. Match embedding against all candidate images in candidates_dir.
    6. Return structured M1Result.

    Args:
        image_path: Path to the input face image.
        candidates_dir: Directory of candidate images to match against.
                        Defaults to member1_face/data/candidates/.
        threshold: Cosine similarity threshold for a positive match (default 0.50).
        model_name: InsightFace model pack name (default 'buffalo_l').

    Returns:
        M1Result with face_detected, candidate, similarity, match, face_embedding, etc.
    """
    # Default candidates directory
    if candidates_dir is None:
        candidates_dir = os.path.join(_MODULE1_DIR, "data", "candidates")

    # -------------------------------------------------------------------------
    # Step 1: Validate input
    # -------------------------------------------------------------------------
    if not os.path.isfile(image_path):
        return M1Result(
            face_detected=False,
            candidate=None,
            candidate_path=None,
            similarity=0.0,
            match=False,
            status="ERROR_INVALID_IMAGE",
            face_embedding=None,
            error=f"Input image not found: {image_path}",
        )

    if not os.path.isdir(candidates_dir):
        return M1Result(
            face_detected=False,
            candidate=None,
            candidate_path=None,
            similarity=0.0,
            match=False,
            status="ERROR_NO_CANDIDATES_DIR",
            face_embedding=None,
            error=f"Candidates directory not found: {candidates_dir}",
        )

    try:
        from src.face_detector import FaceDetector
        from src.face_encoder import FaceEncoder
        from src.candidate_matcher import CandidateMatcher
    except ImportError as e:
        return M1Result(
            face_detected=False,
            candidate=None,
            candidate_path=None,
            similarity=0.0,
            match=False,
            status="ERROR_IMPORT",
            face_embedding=None,
            error=f"Module 1 import failed: {e}. Ensure insightface + onnxruntime are installed.",
        )

    try:
        # -------------------------------------------------------------------------
        # Step 2: Initialize detector
        # -------------------------------------------------------------------------
        logger.info("[M1] Initializing FaceDetector with model '%s'...", model_name)
        detector = FaceDetector(model_name=model_name)

        # -------------------------------------------------------------------------
        # Step 3: Detect faces in input image
        # -------------------------------------------------------------------------
        logger.info("[M1] Detecting faces in: %s", image_path)
        faces = detector.detect_faces(image_path)

        if not faces:
            return M1Result(
                face_detected=False,
                candidate=None,
                candidate_path=None,
                similarity=0.0,
                match=False,
                status="NO_FACE_DETECTED",
                face_embedding=None,
                error="No face detected in the input image.",
            )

        # -------------------------------------------------------------------------
        # Step 4: Extract embedding from primary face
        # -------------------------------------------------------------------------
        primary_face = detector.get_primary_face(faces)
        embedding_np = FaceEncoder.extract_embedding(primary_face, normalize=True)
        face_embedding = embedding_np.tolist()  # convert to serialisable list[float]

        logger.info("[M1] Face detected. Embedding dim=%d", len(face_embedding))

        # -------------------------------------------------------------------------
        # Step 5: Run candidate matching
        # -------------------------------------------------------------------------
        matcher = CandidateMatcher(detector=detector, threshold=threshold)
        gallery_result = matcher.match_gallery(
            input_image_path=image_path,
            candidates_dir=candidates_dir,
            input_embedding=embedding_np,
            save_candidate_detections=False,
        )

        best = gallery_result.get("best_candidate")
        all_matches = gallery_result.get("matches", [])

        if not best:
            return M1Result(
                face_detected=True,
                candidate=None,
                candidate_path=None,
                similarity=0.0,
                match=False,
                status="NO_CANDIDATE_MATCH",
                face_embedding=face_embedding,
                all_matches=all_matches,
            )

        # Build candidate full path for downstream use
        best_name = best.get("candidate", "")
        best_path = os.path.join(candidates_dir, best_name) if best_name else None

        # -------------------------------------------------------------------------
        # Step 6: Return structured result
        # -------------------------------------------------------------------------
        return M1Result(
            face_detected=True,
            candidate=best_name,
            candidate_path=best_path,
            similarity=float(best.get("similarity", 0.0)),
            match=bool(best.get("match", False)),
            status="MATCH" if best.get("match") else "NO_MATCH",
            face_embedding=face_embedding,
            all_matches=all_matches,
        )

    except Exception as exc:
        logger.exception("[M1] Unexpected error in face identification: %s", exc)
        return M1Result(
            face_detected=False,
            candidate=None,
            candidate_path=None,
            similarity=0.0,
            match=False,
            status="ERROR_PIPELINE",
            face_embedding=None,
            error=str(exc),
        )
