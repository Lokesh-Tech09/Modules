"""Main Command-Line Application for Face Identification Module.

Supports two workflows:
1. 1-to-1 Direct Face Verification:
   Compare two specific images (--input img1.jpg --reference img2.jpg)

2. 1-to-Many Gallery Candidate Matching:
   Compare an input face against all images in a folder (--input img1.jpg --candidates data/candidates/)
"""

import argparse
import os
import sys
from typing import Optional
import cv2

from src.candidate_matcher import CandidateMatcher
from src.face_detector import FaceDetector
from src.face_encoder import FaceEncoder
from src.face_matcher import FaceMatcher


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Modular Face Identification & Verification Pipeline using InsightFace, OpenCV, and NumPy."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help="Path to input face image (defaults to data/input/input.jpg or first image in data/input/).",
    )
    parser.add_argument(
        "--reference",
        "-r",
        type=str,
        default=None,
        help="Path to a single reference candidate image to compare directly against (1-to-1 verification).",
    )
    parser.add_argument(
        "--candidates",
        "-c",
        type=str,
        default="data/candidates",
        help="Directory containing candidate images to match against (default: 'data/candidates').",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.50,
        help="Cosine similarity threshold for matching (default: 0.50).",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="output",
        help="Base output directory (default: 'output').",
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="buffalo_l",
        help="InsightFace model pack name (default: 'buffalo_l').",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable interactive OpenCV pop-up preview windows.",
    )
    return parser.parse_args()


def find_default_input_image(input_dir: str = "data/input") -> Optional[str]:
    """Find input.jpg or the first valid image inside data/input directory."""
    preferred = os.path.join(input_dir, "input.jpg")
    if os.path.exists(preferred):
        return preferred

    if not os.path.exists(input_dir):
        return None

    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    for fname in sorted(os.listdir(input_dir)):
        if os.path.splitext(fname)[1].lower() in valid_exts:
            return os.path.join(input_dir, fname)
    return None


def print_step_header(step_num: int, title: str):
    """Print clean step header."""
    print(f"\n[STEP {step_num}] {title}")
    print("-" * 50)


def run_single_reference_comparison(detector: FaceDetector, input_path: str, ref_path: str, args: argparse.Namespace):
    """Execute 1-to-1 direct face comparison between input and reference image."""
    output_detected_dir = os.path.join(args.output_dir, "detected")
    output_embeddings_dir = os.path.join(args.output_dir, "embeddings")
    output_results_dir = os.path.join(args.output_dir, "results")

    print_step_header(1, f"Loading & Detecting Faces in Input: {input_path}")
    input_img = detector.load_image(input_path)
    input_faces = detector.detect_faces(input_img)
    if not input_faces:
        print(f"[ERROR] No face detected in input image: '{input_path}'")
        sys.exit(1)

    primary_input = detector.get_primary_face(input_faces)
    annotated_input = detector.draw_bounding_boxes(input_img, input_faces, highlight_primary=True)
    detector.save_annotated_image(annotated_input, os.path.join(output_detected_dir, "input_detected.jpg"))
    input_emb = FaceEncoder.extract_embedding(primary_input, normalize=True)
    FaceEncoder.save_embedding(input_emb, os.path.join(output_embeddings_dir, "input_embedding.npy"))

    print_step_header(2, f"Loading & Detecting Faces in Reference: {ref_path}")
    ref_img = detector.load_image(ref_path)
    ref_faces = detector.detect_faces(ref_img)
    if not ref_faces:
        print(f"[ERROR] No face detected in reference image: '{ref_path}'")
        sys.exit(1)

    primary_ref = detector.get_primary_face(ref_faces)
    annotated_ref = detector.draw_bounding_boxes(ref_img, ref_faces, highlight_primary=True)
    detector.save_annotated_image(annotated_ref, os.path.join(output_detected_dir, "reference_detected.jpg"))
    ref_emb = FaceEncoder.extract_embedding(primary_ref, normalize=True)
    FaceEncoder.save_embedding(ref_emb, os.path.join(output_embeddings_dir, "reference_embedding.npy"))

    print_step_header(3, "Comparing Embeddings with Cosine Similarity")
    match_result = FaceMatcher.compare_faces(input_emb, ref_emb, threshold=args.threshold)

    is_match = match_result["match"]
    similarity = match_result["similarity"]
    result_text = "MATCH" if is_match else "NO MATCH"

    print("\n====================================")
    print("FACE IDENTIFICATION RESULT (1-to-1)")
    print("====================================\n")
    print(f"Input Image 1:\n{os.path.basename(input_path)}")
    print(f"\nReference Image 2:\n{os.path.basename(ref_path)}")
    print(f"\nSimilarity Score:\n{similarity:.2f}")
    print(f"\nConfidence Rating:\n{match_result['confidence']}")
    print(f"\nThreshold:\n{args.threshold:.2f}")
    print(f"\nResult:\n{result_text}")
    print("\n====================================\n")

    # Generate visual side-by-side graphic
    banner = FaceMatcher.create_comparison_banner(
        img_input=annotated_input,
        img_candidate=annotated_ref,
        match_result=match_result,
        label_input=f"Img 1: {os.path.basename(input_path)}",
        label_candidate=f"Img 2: {os.path.basename(ref_path)}",
    )
    banner_path = os.path.join(output_results_dir, "comparison_result.jpg")
    cv2.imwrite(banner_path, banner)
    print(f"[OK] Saved comparison visualization to: {banner_path}")

    if not args.no_display:
        detector.display_bounding_box(banner, window_title="1-to-1 Face Comparison Result", wait_ms=1500)


def main():
    args = parse_arguments()

    # Define standardized output directory paths
    output_detected_dir = os.path.join(args.output_dir, "detected")
    output_embeddings_dir = os.path.join(args.output_dir, "embeddings")
    output_results_dir = os.path.join(args.output_dir, "results")

    for directory in [output_detected_dir, output_embeddings_dir, output_results_dir]:
        os.makedirs(directory, exist_ok=True)

    print("=" * 60)
    print("      FACE IDENTIFICATION PIPELINE INITIALIZING")
    print("=" * 60)
    print(f"[*] Model Name        : {args.model}")
    print(f"[*] Similarity Cutoff : {args.threshold:.2f}")
    print(f"[*] Output Directory  : {os.path.abspath(args.output_dir)}")

    # Resolve input image path
    input_path = args.input
    if not input_path:
        input_path = find_default_input_image("data/input")

    if not input_path or not os.path.exists(input_path):
        print("\n" + "!" * 60)
        print("[ERROR] Input image not found!")
        print("Please place an image at 'data/input/input.jpg' or use '--input <path_to_image>'")
        print("!" * 60)
        sys.exit(1)

    detector = FaceDetector(model_name=args.model)

    # If --reference is provided, run 1-to-1 direct comparison
    if args.reference:
        if not os.path.exists(args.reference):
            print(f"[ERROR] Reference image not found at: '{args.reference}'")
            sys.exit(1)
        run_single_reference_comparison(detector, input_path, args.reference, args)
        return

    # -------------------------------------------------------------------------
    # 1-to-Many Gallery Mode (Default)
    # -------------------------------------------------------------------------
    print_step_header(1, "Loading Input Face Image")
    print(f"[*] Loading: {input_path}")
    try:
        input_img = detector.load_image(input_path)
        print(f"[OK] Image loaded successfully (Dimensions: {input_img.shape[1]}x{input_img.shape[0]} px).")
    except Exception as e:
        print(f"[ERROR] Failed to load image: {e}")
        sys.exit(1)

    print_step_header(2, "Detecting Faces in Input Image")
    input_faces = detector.detect_faces(input_img)

    if not input_faces:
        print("\n" + "!" * 60)
        print(f"[ERROR] No face detected in input image: '{input_path}'")
        print("Tip: Ensure the image contains a clear, visible, and well-lit human face.")
        print("!" * 60)
        sys.exit(1)

    print(f"[OK] Detected {len(input_faces)} face(s) in input image.")
    primary_face = detector.get_primary_face(input_faces)
    bbox = primary_face.bbox.astype(int)
    det_score = float(getattr(primary_face, "det_score", 1.0))
    print(f"    Primary Face Selected (Largest Area): [x1={bbox[0]}, y1={bbox[1]}, x2={bbox[2]}, y2={bbox[3]}]")
    print(f"    Detection Confidence Score : {det_score * 100:.2f}%")

    print_step_header(3, "Drawing & Saving Input Face Visualization")
    annotated_input = detector.draw_bounding_boxes(input_img, input_faces, highlight_primary=True)
    input_detected_path = os.path.join(output_detected_dir, "input_detected.jpg")
    detector.save_annotated_image(annotated_input, input_detected_path)

    if not args.no_display:
        detector.display_bounding_box(annotated_input, window_title="Step 3: Input Face Detected", wait_ms=1000)

    print_step_header(4, "Extracting & Saving 512-D Face Embedding")
    try:
        input_embedding = FaceEncoder.extract_embedding(primary_face, normalize=True)
        input_emb_path = os.path.join(output_embeddings_dir, "input_embedding.npy")
        FaceEncoder.save_embedding(input_embedding, input_emb_path)
        print(f"    Vector Shape : {input_embedding.shape} (512-D L2-Normalized)")
        print(f"    Sample Values: {input_embedding[:4]}")
    except Exception as e:
        print(f"[ERROR] Failed to extract/save embedding: {e}")
        sys.exit(1)

    print_step_header(5, f"Scanning & Processing Candidates in '{args.candidates}'")
    matcher = CandidateMatcher(detector=detector, threshold=args.threshold)

    results_json_path = os.path.join(output_results_dir, "match_results.json")

    if not os.path.exists(args.candidates):
        print(f"[!] Warning: Candidate folder '{args.candidates}' does not exist. Creating it now.")
        os.makedirs(args.candidates, exist_ok=True)

    try:
        candidate_results = matcher.match_gallery(
            input_image_path=input_path,
            candidates_dir=args.candidates,
            input_embedding=input_embedding,
            output_json_path=results_json_path,
            save_candidate_detections=True,
            detected_output_dir=output_detected_dir,
        )
    except Exception as e:
        print(f"[ERROR] Candidate processing failed: {e}")
        sys.exit(1)

    total_candidates = candidate_results["total_candidates"]
    best_candidate_info = candidate_results["best_candidate"]

    best_candidate_name = best_candidate_info["candidate"] if best_candidate_info else "None"
    best_similarity = best_candidate_info["similarity"] if best_candidate_info else 0.0
    best_match_bool = best_candidate_info["match"] if best_candidate_info else False
    result_text = "MATCH" if best_match_bool else "NO MATCH"

    print("\n====================================")
    print("FACE IDENTIFICATION RESULT")
    print("====================================\n")
    print("Input Image:")
    print(os.path.basename(input_path))
    print("\nFaces Detected:")
    print(len(input_faces))
    print("\nCandidates Processed:")
    print(total_candidates)
    print("\nBest Candidate:")
    print(best_candidate_name)
    print("\nSimilarity Score:")
    print(f"{best_similarity:.2f}")
    print("\nResult:")
    print(result_text)
    print("\n====================================\n")

    if best_candidate_info and best_candidate_info.get("status") == "SUCCESS":
        best_cand_img_path = os.path.join(args.candidates, best_candidate_name)
        if os.path.exists(best_cand_img_path):
            cand_img = detector.load_image(best_cand_img_path)
            cand_faces = detector.detect_faces(cand_img)
            annotated_cand = detector.draw_bounding_boxes(cand_img, cand_faces)

            comparison_stats = {
                "match": best_match_bool,
                "similarity": best_similarity,
                "percentage": best_similarity * 100.0,
                "confidence": "Best Candidate Match" if best_match_bool else "Best Candidate (Below Threshold)",
                "threshold": args.threshold,
            }

            banner = FaceMatcher.create_comparison_banner(
                img_input=annotated_input,
                img_candidate=annotated_cand,
                match_result=comparison_stats,
                label_input=f"Input: {os.path.basename(input_path)}",
                label_candidate=f"Best: {best_candidate_name}",
            )
            banner_path = os.path.join(output_results_dir, "best_match_comparison.jpg")
            cv2.imwrite(banner_path, banner)
            print(f"[OK] Saved visual comparison graphic to: {banner_path}")

            if not args.no_display:
                detector.display_bounding_box(banner, window_title="Best Match Comparison", wait_ms=1500)

    print(f"[OK] Full match report JSON saved to: {results_json_path}")


if __name__ == "__main__":
    main()
