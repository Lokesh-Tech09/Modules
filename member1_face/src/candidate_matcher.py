"""Candidate Matcher Module.

This module is responsible for:
- Scanning an entire folder of candidate/reference face images.
- Detecting the primary face in each candidate image.
- Extracting and storing normalized face embeddings for each candidate.
- Comparing all candidates against an input face embedding using Cosine Similarity.
- Ranking candidates from highest similarity to lowest similarity.
- Exporting structured match results into a clean JSON file for integration.
- Identifying the single best-matching candidate.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from src.face_detector import FaceDetector
from src.face_encoder import FaceEncoder
from src.face_matcher import FaceMatcher


class CandidateMatcher:
    """Processes candidate galleries and ranks candidates against an input face."""

    VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    def __init__(
        self,
        detector: Optional[FaceDetector] = None,
        threshold: float = FaceMatcher.DEFAULT_THRESHOLD,
    ):
        """Initialize CandidateMatcher.

        Args:
            detector: Existing FaceDetector instance or None to instantiate a new one.
            threshold: Cosine similarity cutoff for matching (default: 0.50).
        """
        self.detector = detector if detector is not None else FaceDetector()
        self.threshold = threshold

    def get_candidate_image_paths(self, candidates_dir: str) -> List[str]:
        """Scan directory and return sorted list of valid image file paths.

        Args:
            candidates_dir: Path to directory containing candidate images.

        Returns:
            List[str]: Absolute paths to valid candidate images.
        """
        if not os.path.exists(candidates_dir):
            raise FileNotFoundError(f"Candidates folder not found at: '{candidates_dir}'")

        image_paths = []
        for entry in sorted(os.listdir(candidates_dir)):
            full_path = os.path.join(candidates_dir, entry)
            if os.path.isfile(full_path):
                ext = os.path.splitext(entry)[1].lower()
                if ext in self.VALID_EXTENSIONS:
                    image_paths.append(full_path)

        return image_paths

    def match_gallery(
        self,
        input_image_path: str,
        candidates_dir: str,
        input_embedding: Optional[np.ndarray] = None,
        output_json_path: Optional[str] = None,
        save_candidate_detections: bool = True,
        detected_output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compare an input face against all candidate images in a gallery directory.

        Args:
            input_image_path: Path to the input image.
            candidates_dir: Directory containing candidate images.
            input_embedding: Optional pre-extracted 512-D embedding for the input face.
            output_json_path: Optional file path to save JSON results.
            save_candidate_detections: Whether to save bounding-box annotated images of candidates.
            detected_output_dir: Directory where annotated candidate images are saved.

        Returns:
            dict containing:
                - input_image (str): Input image path
                - total_candidates (int): Count of candidate images scanned
                - valid_faces_detected (int): Number of candidates where a face was found
                - best_candidate (dict or None): Info for highest ranking candidate
                - matches (List[dict]): Ranked list of all candidate comparison results
        """
        # Ensure we have the input face embedding
        if input_embedding is None:
            input_img = self.detector.load_image(input_image_path)
            input_faces = self.detector.detect_faces(input_img)
            if not input_faces:
                raise ValueError(f"No face detected in input image: '{input_image_path}'")
            primary_input_face = self.detector.get_primary_face(input_faces)
            input_embedding = FaceEncoder.extract_embedding(primary_input_face)

        # Retrieve candidate filepaths
        candidate_paths = self.get_candidate_image_paths(candidates_dir)
        print(f"[CandidateMatcher] Found {len(candidate_paths)} candidate image(s) in '{candidates_dir}'.")

        matches_list = []
        valid_faces_count = 0

        for cand_path in candidate_paths:
            cand_filename = os.path.basename(cand_path)
            print(f"[CandidateMatcher] Processing candidate: {cand_filename} ...")

            try:
                cand_img = self.detector.load_image(cand_path)
                cand_faces = self.detector.detect_faces(cand_img)

                if not cand_faces:
                    print(f"  [!] Warning: No face detected in candidate image '{cand_filename}'.")
                    matches_list.append({
                        "candidate": cand_filename,
                        "similarity": 0.0,
                        "match": False,
                        "status": "NO_FACE_DETECTED",
                    })
                    continue

                primary_cand_face = self.detector.get_primary_face(cand_faces)
                cand_embedding = FaceEncoder.extract_embedding(primary_cand_face)
                valid_faces_count += 1

                # Save candidate annotated image if requested
                if save_candidate_detections and detected_output_dir:
                    annotated_cand = self.detector.draw_bounding_boxes(cand_img, cand_faces)
                    cand_annotated_path = os.path.join(detected_output_dir, f"detected_{cand_filename}")
                    self.detector.save_annotated_image(annotated_cand, cand_annotated_path)

                # Compare embeddings
                comparison = FaceMatcher.compare_faces(
                    input_embedding,
                    cand_embedding,
                    threshold=self.threshold,
                )

                matches_list.append({
                    "candidate": cand_filename,
                    "similarity": comparison["similarity"],
                    "match": comparison["match"],
                    "status": "SUCCESS",
                })

            except Exception as e:
                print(f"  [!] Error processing '{cand_filename}': {e}")
                matches_list.append({
                    "candidate": cand_filename,
                    "similarity": 0.0,
                    "match": False,
                    "status": f"ERROR: {str(e)}",
                })

        # Rank all candidates from highest similarity to lowest
        matches_list.sort(key=lambda x: x["similarity"], reverse=True)

        best_candidate = matches_list[0] if matches_list else None

        result_payload = {
            "input_image": os.path.normpath(input_image_path).replace("\\", "/"),
            "matches": matches_list,
        }

        # Save JSON output if path provided
        if output_json_path:
            abs_json_path = os.path.abspath(output_json_path)
            os.makedirs(os.path.dirname(abs_json_path), exist_ok=True)
            with open(abs_json_path, "w", encoding="utf-8") as f:
                json.dump(result_payload, f, indent=4)
            print(f"[CandidateMatcher] Saved match results to JSON: {abs_json_path}")

        return {
            "input_image": result_payload["input_image"],
            "total_candidates": len(candidate_paths),
            "valid_faces_detected": valid_faces_count,
            "best_candidate": best_candidate,
            "matches": matches_list,
        }
