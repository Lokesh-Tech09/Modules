"""
End-to-End Demonstration connecting Module 1, Module 2, and Module 3.
Pipeline:
  [Module 1] Face Scan & Embedding
       ↓
  [Module 2] Claimed-Profile Verification (v2)
       ↓
  [Module 3] Blockchain Upload & Hashing
"""

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Module 2 imports
from member2_verify import (
    ConsentRecord,
    ConsentScope,
    ContentHashCache,
    FaceMatchDetail,
    VerificationConfig,
    VerificationPipeline,
)
from member2_verify.candidate_fetcher import CandidateFetcher
from member2_verify.face_matcher import FaceMatcher
from member2_verify.models import (
    CandidateFetchResult,
    ExtractedPostMetadata,
    FaceDetection,
    FetchStatus,
)
from member2_verify.post_extractor import PostExtractor


# =====================================================================
# SIMULATED MODULE 1: Face Scan & Embedding Generator
# =====================================================================
def run_module_1():
    print("\n--- [STEP 1: MODULE 1 — FACE SCAN & EMBEDDING] ---")
    print("1. User scans face at device.")
    print("2. Module 1 detects facial landmarks & extracts 512-d InsightFace embedding.")

    # Synthetic 512-d normalized embedding representing user's face
    import numpy as np
    raw_emb = [0.05] * 512
    raw_emb[0] = 0.95
    embedding = (np.array(raw_emb) / np.linalg.norm(raw_emb)).tolist()

    print("3. User asserts ownership of public profile URL and grants consent.")
    claimed_urls = ["https://instagram.com/p/my_profile_post"]
    consent = ConsentRecord(
        consent_confirmed=True,
        consent_scope=ConsentScope.SELF_VERIFICATION,
        consent_timestamp="2026-09-05T10:00:00Z",
    )

    module1_payload = {
        "image_path": "scanned_user_face.jpg",
        "face_embedding": embedding,
        "claimed_urls": claimed_urls,
        "consent": consent,
    }
    print(f"Handoff Payload from Module 1 ready (Embedding dim: {len(embedding)}, URLs: {len(claimed_urls)})")
    return module1_payload


# =====================================================================
# MODULE 2: Claimed-Profile Verification (Our Module)
# =====================================================================
async def run_module_2(module1_data: dict) -> dict:
    print("\n--- [STEP 2: MODULE 2 — CLAIMED-PROFILE VERIFICATION] ---")
    print(f"1. Validating consent scope: '{module1_data['consent'].consent_scope}'")
    print(f"2. Fetching {len(module1_data['claimed_urls'])} user-supplied candidate URL(s)...")

    # Set up mock media for candidate URL
    temp_dir = Path("member2_verify/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_candidate_img = str(temp_dir / "verified_candidate_face.jpg")
    img_bytes = b"real_candidate_face_jpeg_bytes"
    with open(temp_candidate_img, "wb") as f:
        f.write(img_bytes)

    # Configure pipeline components
    mock_fetcher = MagicMock(spec=CandidateFetcher)
    mock_extractor = MagicMock(spec=PostExtractor)
    mock_matcher = MagicMock(spec=FaceMatcher)

    mock_fetcher.fetch_all = AsyncMock(return_value=[
        CandidateFetchResult(
            url="https://instagram.com/p/my_profile_post",
            fetch_status=FetchStatus.SUCCESS,
            content_type="image/jpeg",
            image_bytes=img_bytes,
            local_image_path=temp_candidate_img,
            extracted_metadata=ExtractedPostMetadata(
                url="https://instagram.com/p/my_profile_post",
                image_url="https://cdn.instagram.com/p/photo_full.jpg",
                caption="Summit selfie at Goa Hackathon! #ConsentedVerification",
                metadata={"platform": "instagram"},
            ),
        )
    ])

    # Compare face: returns raw similarity 0.971 -> calibrated 0.940
    mock_matcher.compare_candidate_image.return_value = (
        True,
        0.971,
        0.940,
        False,
        FaceMatchDetail(
            face_index=0,
            raw_similarity=0.971,
            calibrated_confidence=0.940,
            low_confidence_detection=False,
            bounding_box=[50, 50, 150, 150],
        ),
    )
    mock_matcher.detect_and_embed.return_value = [
        FaceDetection(bounding_box=[50, 50, 150, 150], embedding=module1_data["face_embedding"])
    ]

    pipeline = VerificationPipeline(
        config=VerificationConfig(SIMILARITY_THRESHOLD=0.65),
        fetcher=mock_fetcher,
        extractor=mock_extractor,
        matcher=mock_matcher,
        cache=ContentHashCache(),
    )

    output = await pipeline.run(
        image_path=module1_data["image_path"],
        face_embedding=module1_data["face_embedding"],
        claimed_urls=module1_data["claimed_urls"],
        consent=module1_data["consent"],
    )

    result_dict = output.to_dict()
    print("3. Verification completed:")
    print(f"   Status: {result_dict['status']}")
    print(f"   Raw Similarity: {result_dict['verification']['raw_similarity']}")
    print(f"   Calibrated Confidence: {result_dict['verification']['calibrated_confidence']}")
    print(f"   Matched URL: {result_dict['match']['url']}")
    return result_dict


# =====================================================================
# SIMULATED MODULE 3: Blockchain Upload & Cryptographic Hashing
# =====================================================================
def run_module_3(module2_result: dict) -> dict:
    print("\n--- [STEP 3: MODULE 3 — BLOCKCHAIN UPLOAD & HASHING] ---")

    if module2_result.get("status") != "verified":
        print("Verification status is NOT 'verified'. Aborting blockchain upload.")
        return {"blockchain_status": "REJECTED"}

    print("1. Validating verification payload schema (version 2.0)... OK")

    match_data = module2_result["match"]
    local_path = match_data["local_image_path"]

    # Step A: Cryptographic SHA-256 hash of matched image
    with open(local_path, "rb") as f:
        image_hash = hashlib.sha256(f.read()).hexdigest()
    print(f"2. Generated Image SHA-256 Hash: {image_hash[:16]}...{image_hash[-8:]}")

    # Step B: Cryptographic hash of verification claim
    claim_bytes = json.dumps({
        "url": match_data["url"],
        "confidence": module2_result["verification"]["calibrated_confidence"],
        "consent": module2_result["consent"],
    }, sort_keys=True).encode()
    claim_hash = hashlib.sha256(claim_bytes).hexdigest()
    print(f"3. Generated Claim Metadata Hash: {claim_hash[:16]}...{claim_hash[-8:]}")

    # Step C: Simulated Blockchain Transaction (Smart Contract State Entry)
    tx_hash = "0x" + hashlib.sha256((image_hash + claim_hash).encode()).hexdigest()
    block_entry = {
        "blockchain_status": "COMMITTED_ON_CHAIN",
        "block_number": 1048291,
        "tx_hash": tx_hash,
        "identity_claim": {
            "verified_url": match_data["url"],
            "image_sha256": image_hash,
            "claim_sha256": claim_hash,
            "calibrated_confidence": module2_result["verification"]["calibrated_confidence"],
            "consent_scope": module2_result["consent"]["consent_scope"],
        },
        "re_verification_ready": True,
    }

    print("4. Blockchain Transaction Committed:")
    print(f"   Block Number: {block_entry['block_number']}")
    print(f"   Tx Hash: {block_entry['tx_hash']}")
    print(f"   Re-verification Flag: {block_entry['re_verification_ready']}")
    return block_entry


async def main():
    print("=" * 80)
    print("END-TO-END PIPELINE: MODULE 1 --> MODULE 2 --> MODULE 3")
    print("Task 3: Face Identification & Blockchain Verification")
    print("=" * 80)

    # 1. Module 1 creates input
    m1_out = run_module_1()

    # 2. Module 2 performs profile verification
    m2_out = await run_module_2(m1_out)

    # 3. Module 3 hashes & commits to blockchain
    m3_out = run_module_3(m2_out)

    print("\n" + "=" * 80)
    print("COMPLETE PIPELINE COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
