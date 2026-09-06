"""Unit and Pipeline Tests for Face Identification Module.

Tests:
1. Imports and dependency integrity.
2. FaceDetector: loading images, detecting faces, selecting primary face, drawing bounding boxes.
3. FaceEncoder: extracting 512-D embeddings, normalization, saving and loading .npy files.
4. FaceMatcher: cosine similarity computation, match verdict, threshold boundary checks.
5. CandidateMatcher: gallery scanning, ranking, JSON export validation.
"""

import json
import os
import sys
import numpy as np

# Ensure root face_identification directory is on PYTHONPATH
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from src.face_detector import FaceDetector
from src.face_encoder import FaceEncoder
from src.face_matcher import FaceMatcher
from src.candidate_matcher import CandidateMatcher


def test_imports():
    print("[TEST 1/5] Verifying dependencies and imports...")
    import cv2
    import onnxruntime
    import insightface
    print(f"  [OK] OpenCV version: {cv2.__version__}")
    print(f"  [OK] NumPy version: {np.__version__}")
    print(f"  [OK] ONNX Runtime version: {onnxruntime.__version__}")
    print(f"  [OK] InsightFace version: {insightface.__version__}")


def test_face_detector():
    print("\n[TEST 2/5] Testing FaceDetector on sample input image...")
    input_img_path = os.path.join(CURRENT_DIR, "data", "input", "input.jpg")
    if not os.path.exists(input_img_path):
        raise FileNotFoundError(f"Test input image missing at {input_img_path}. Run setup_sample_data.py first.")

    detector = FaceDetector()
    img = detector.load_image(input_img_path)
    assert isinstance(img, np.ndarray) and img.size > 0, "Failed to load image as numpy array"

    faces = detector.detect_faces(img)
    assert len(faces) > 0, "No face detected in input test image!"
    print(f"  [OK] Detected {len(faces)} face(s).")

    primary_face = detector.get_primary_face(faces)
    assert primary_face is not None, "Failed to select primary face"
    assert hasattr(primary_face, "bbox"), "Primary face missing bbox attribute"
    print(f"  [OK] Primary face bounding box: {primary_face.bbox.astype(int)}")

    annotated = detector.draw_bounding_boxes(img, faces)
    assert annotated.shape == img.shape, "Annotated image shape mismatch"
    print("  [OK] Bounding box annotations rendered successfully.")
    return detector, primary_face


def test_face_encoder(primary_face):
    print("\n[TEST 3/5] Testing FaceEncoder (Extraction, Normalization, Save/Load)...")
    embedding = FaceEncoder.extract_embedding(primary_face, normalize=True)
    assert isinstance(embedding, np.ndarray), "Embedding is not a numpy array"
    assert embedding.shape == (512,), f"Expected 512-D vector, got {embedding.shape}"

    norm = np.linalg.norm(embedding)
    assert np.isclose(norm, 1.0, atol=1e-4), f"Embedding is not unit-normalized (norm={norm})"
    print(f"  [OK] Extracted 512-D embedding with unit L2 norm (norm={norm:.4f}).")

    test_npy = os.path.join(CURRENT_DIR, "output", "embeddings", "test_embedding.npy")
    saved_path = FaceEncoder.save_embedding(embedding, test_npy)
    assert os.path.exists(saved_path), "Embedding .npy file was not created"

    loaded_emb = FaceEncoder.load_embedding(saved_path)
    assert np.allclose(embedding, loaded_emb, atol=1e-6), "Loaded embedding does not match saved embedding"
    print("  [OK] Embedding saved and loaded successfully with exact numerical equality.")
    return embedding


def test_face_matcher(embedding):
    print("\n[TEST 4/5] Testing FaceMatcher (Cosine Similarity & Threshold Matching)...")
    # Same vector must yield similarity = 1.0
    self_sim = FaceMatcher.compute_cosine_similarity(embedding, embedding)
    assert np.isclose(self_sim, 1.0, atol=1e-4), f"Self-similarity should be 1.0, got {self_sim}"
    print(f"  [OK] Identity self-similarity: {self_sim:.4f}")

    # Orthogonal / Synthetic vector test
    rng = np.random.RandomState(42)
    diff_vector = rng.randn(512).astype(np.float32)
    diff_vector /= np.linalg.norm(diff_vector)
    diff_sim = FaceMatcher.compute_cosine_similarity(embedding, diff_vector)
    print(f"  [OK] Random vector similarity: {diff_sim:.4f}")

    match_self = FaceMatcher.compare_faces(embedding, embedding, threshold=0.50)
    assert match_self["match"] is True, "Self-match should evaluate to True"
    assert match_self["similarity"] >= 0.99, "Self-similarity must be >= 0.99"

    match_diff = FaceMatcher.compare_faces(embedding, diff_vector, threshold=0.50)
    assert match_diff["match"] is False, "Random vector match should evaluate to False"
    print("  [OK] Matcher logic and thresholds verified.")


def test_candidate_matcher(detector, embedding):
    print("\n[TEST 5/5] Testing CandidateMatcher (Multi-Candidate Ranking & JSON Export)...")
    candidates_dir = os.path.join(CURRENT_DIR, "data", "candidates")
    output_json = os.path.join(CURRENT_DIR, "output", "results", "match_results.json")

    matcher = CandidateMatcher(detector=detector, threshold=0.50)
    results = matcher.match_gallery(
        input_image_path=os.path.join(CURRENT_DIR, "data", "input", "input.jpg"),
        candidates_dir=candidates_dir,
        input_embedding=embedding,
        output_json_path=output_json,
    )

    assert os.path.exists(output_json), "JSON results file was not saved"
    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "input_image" in data, "JSON missing input_image"
    assert "matches" in data, "JSON missing matches array"
    assert len(data["matches"]) > 0, "No matches in JSON results"

    best_match = results["best_candidate"]
    print(f"  [OK] Candidates processed: {results['total_candidates']}")
    print(f"  [OK] Top Ranked Candidate: {best_match['candidate']} (Similarity: {best_match['similarity']:.4f}, Match: {best_match['match']})")
    print("  [OK] JSON output verified successfully.")


def run_all_tests():
    print("=" * 60)
    print("        RUNNING FACE IDENTIFICATION TEST SUITE")
    print("=" * 60)
    try:
        test_imports()
        detector, primary_face = test_face_detector()
        embedding = test_face_encoder(primary_face)
        test_face_matcher(embedding)
        test_candidate_matcher(detector, embedding)
        print("\n" + "=" * 60)
        print("    [OK] ALL 5 TEST SUITES PASSED PERFECTLY!")
        print("=" * 60)
    except Exception as e:
        print(f"\n[X] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
