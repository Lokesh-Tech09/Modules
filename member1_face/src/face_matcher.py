"""Face Matcher Module.

This module is responsible for:
- Computing Cosine Similarity between two face embeddings.
- Comparing face pairs against a configurable similarity threshold.
- Categorizing match confidence.
- Creating side-by-side visual comparison banners for presentation and reporting.

THRESHOLD CALIBRATION NOTES:
- Cosine similarity measures the angle between two 512-dimensional feature vectors.
- Theoretical range: [-1.0, 1.0]. In practice for normalized face embeddings:
    - Values >= 0.70 : Almost certainly the same individual under good lighting/pose.
    - Values 0.50 - 0.70 : Same individual with moderate variations in angle/lighting.
    - Values 0.40 - 0.50 : Borderline match (potential same individual under extreme pose/lighting, or lookalike).
    - Values < 0.40 : Different individuals.
- Default threshold is set to 0.50 for InsightFace 'buffalo_l' (ArcFace model).
- You can calibrate this threshold based on your application's tolerance for
  False Acceptance Rate (FAR) vs False Rejection Rate (FRR).
"""

from typing import Any, Dict, Optional, Tuple, Union
import cv2
import numpy as np


class FaceMatcher:
    """Compares face embeddings and determines identity verification using Cosine Similarity."""

    # Default similarity threshold recommended for InsightFace ArcFace / buffalo_l
    DEFAULT_THRESHOLD: float = 0.50

    @staticmethod
    def compute_cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute the cosine similarity between two face embedding vectors.

        Formula: Cosine Similarity = (A . B) / (||A||_2 * ||B||_2)

        Args:
            emb1: First face embedding (numpy array).
            emb2: Second face embedding (numpy array).

        Returns:
            float: Cosine similarity score in range [-1.0, 1.0].
        """
        if emb1 is None or emb2 is None:
            raise ValueError("Embeddings cannot be None.")

        e1 = emb1.flatten().astype(np.float64)
        e2 = emb2.flatten().astype(np.float64)

        if e1.size == 0 or e2.size == 0:
            raise ValueError("Embedding array cannot be empty.")

        norm1 = np.linalg.norm(e1)
        norm2 = np.linalg.norm(e2)

        if norm1 < 1e-7 or norm2 < 1e-7:
            return 0.0

        dot_product = np.dot(e1, e2)
        similarity = dot_product / (norm1 * norm2)

        # Clip to [-1.0, 1.0] to guard against floating-point inaccuracies
        similarity = float(np.clip(similarity, -1.0, 1.0))
        return similarity

    @classmethod
    def compare_faces(
        cls,
        emb1: np.ndarray,
        emb2: np.ndarray,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> Dict[str, Union[bool, float, str]]:
        """Compare two face embeddings against a threshold to determine identity match.

        Args:
            emb1: First face embedding array (e.g. input face).
            emb2: Second face embedding array (e.g. candidate face).
            threshold: Cosine similarity cutoff (default: 0.50).

        Returns:
            dict containing:
                - match (bool): True if similarity >= threshold, else False
                - is_match (bool): Alias for match
                - similarity (float): Raw cosine similarity score (rounded to 4 decimals)
                - percentage (float): Percentage similarity score (0.0% to 100.0%)
                - confidence (str): Categorical rating ("High", "Moderate", "Mismatch")
                - threshold (float): The threshold used for comparison
        """
        similarity = cls.compute_cosine_similarity(emb1, emb2)
        is_match = similarity >= threshold

        # Clamp negative similarities to 0 for percentage display
        percentage = max(0.0, similarity) * 100.0

        # Assign descriptive confidence rating
        if similarity >= 0.70:
            confidence = "Very High Match"
        elif similarity >= 0.55:
            confidence = "High Match"
        elif similarity >= threshold:
            confidence = "Moderate Match (Above Threshold)"
        elif similarity >= threshold - 0.10:
            confidence = "Borderline / Low Similarity"
        else:
            confidence = "Mismatch (Different Person)"

        return {
            "match": is_match,
            "is_match": is_match,
            "similarity": round(similarity, 4),
            "percentage": round(percentage, 2),
            "confidence": confidence,
            "threshold": threshold,
        }

    # Alias method for backwards compatibility
    match = compare_faces

    @staticmethod
    def create_comparison_banner(
        img_input: np.ndarray,
        img_candidate: np.ndarray,
        match_result: Dict[str, Union[bool, float, str]],
        label_input: str = "Input Face",
        label_candidate: str = "Candidate Face",
        target_height: int = 480,
    ) -> np.ndarray:
        """Create a side-by-side visual comparison banner with matching stats.

        Args:
            img_input: Annotated input face image array.
            img_candidate: Annotated candidate face image array.
            match_result: Result dictionary from FaceMatcher.compare_faces().
            label_input: Label for the left image.
            label_candidate: Label for the right image.
            target_height: Target height for uniform display.

        Returns:
            np.ndarray: Combined annotated image with header and verdict footer.
        """
        def resize_to_height(img: np.ndarray, h: int) -> np.ndarray:
            orig_h, orig_w = img.shape[:2]
            w = int(orig_w * (h / orig_h))
            return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)

        img1 = resize_to_height(img_input, target_height)
        img2 = resize_to_height(img_candidate, target_height)

        combined = np.hstack([img1, img2])
        total_w = combined.shape[1]

        is_match = match_result.get("match", False)
        banner_color = (40, 180, 50) if is_match else (40, 40, 220)  # Green vs Red (BGR)
        bg_dark = (25, 25, 30)

        # Header (Height 55px)
        header = np.full((55, total_w, 3), bg_dark, dtype=np.uint8)
        cv2.putText(
            header,
            label_input,
            (20, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            header,
            label_candidate,
            (img1.shape[1] + 20, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )

        # Footer (Height 100px)
        footer = np.full((100, total_w, 3), bg_dark, dtype=np.uint8)
        cv2.rectangle(footer, (0, 0), (total_w, 5), banner_color, -1)

        verdict_text = "MATCH CONFIRMED" if is_match else "NO MATCH"
        cv2.putText(
            footer,
            f"RESULT: {verdict_text}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            banner_color,
            2,
            cv2.LINE_AA,
        )

        stats_text = (
            f"Cosine Similarity: {match_result['similarity']:.4f} ({match_result['percentage']:.1f}%)"
            f" | Threshold: {match_result['threshold']:.2f}"
            f" | Rating: {match_result['confidence']}"
        )
        cv2.putText(
            footer,
            stats_text,
            (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 185, 195),
            1,
            cv2.LINE_AA,
        )

        return np.vstack([header, combined, footer])
