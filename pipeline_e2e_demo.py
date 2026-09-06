"""
End-to-End Demonstration: VeriFace Pipeline
============================================
Connects Module 1 (Face Identification), Module 2 (Post Verification),
and Module 3 (Blockchain Anchoring) end-to-end.

Original pipeline_e2e_demo.py has been updated to:
- Replace the synthetic/fake Module 1 embedding with the real adapter
- Replace the hardcoded Instagram URL with a genuine DuckDuckGo search
- All existing Module 2 and Module 3 code is preserved and unchanged

Run:
    python pipeline_e2e_demo.py --image member1_face/data/input/input.jpg
Or use main.py for full-featured CLI:
    python main.py --image member1_face/data/input/input.jpg --tamper-test
"""

import asyncio
import json
import os
import sys
import copy
from typing import Any, Dict, Optional

# Ensure project root + member1_face/src are importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODULE1_DIR  = os.path.join(PROJECT_ROOT, "member1_face")
for _p in [PROJECT_ROOT, MODULE1_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# =====================================================================
# MODULE 1: Real Face Scan & Identification (via adapter)
# =====================================================================
def run_module_1(image_path: str, candidates_dir: Optional[str] = None):
    """
    Run the real Module 1 face identification pipeline.
    Uses InsightFace detector + encoder + CandidateMatcher (unchanged from original).
    Falls back gracefully with clear error messages if insightface is unavailable.
    """
    print("\n--- [STEP 1: MODULE 1 — FACE SCAN & IDENTIFICATION] ---")

    from member1_face.adapter import run_face_identification

    if candidates_dir is None:
        candidates_dir = os.path.join(MODULE1_DIR, "data", "candidates")

    print(f"1. Loading input image: {image_path}")
    result = run_face_identification(
        image_path=image_path,
        candidates_dir=candidates_dir,
    )

    if not result.face_detected:
        print(f"[ERROR] Face detection failed: {result.status}")
        if result.error:
            print(f"        {result.error}")
        return None

    print(f"2. Face detected: YES  (embedding_dim={len(result.face_embedding)})")
    print(f"3. Best candidate match: {result.candidate}")
    print(f"   Similarity: {result.similarity:.4f}  |  Match: {result.match}  |  Status: {result.status}")

    # Build handoff payload for Module 2
    candidate_name = os.path.splitext(result.candidate or "unknown")[0]
    candidate_name = candidate_name.replace("_", " ").replace("-", " ").strip()

    module1_payload = {
        "image_path": image_path,
        "face_embedding": result.face_embedding,   # real 512-d normalized embedding
        "candidate_name": candidate_name,           # for web search
        "candidate_filename": result.candidate,
        "candidate_path": result.candidate_path,
        "similarity": result.similarity,
        "match": result.match,
        "status": result.status,
        "all_matches": result.all_matches,
    }
    print(f"Handoff payload ready (embedding_dim={len(result.face_embedding)}, candidate='{candidate_name}')")
    return module1_payload


# =====================================================================
# GENUINE WEB/SOCIAL SEARCH (replaces hardcoded URL)
# =====================================================================
def run_genuine_search(module1_data: dict, max_results: int = 5) -> list:
    """
    Perform a GENUINE DuckDuckGo search to discover social/web posts.
    This is NOT a hardcoded or pre-selected URL.
    """
    print("\n--- [STEP 2: GENUINE WEB/SOCIAL DISCOVERY] ---")

    candidate_name = module1_data.get("candidate_name", "")
    if not candidate_name:
        print("[WARNING] No candidate name — skipping search, returning empty URL list.")
        return []

    print(f"1. Search query: '{candidate_name} social media profile'")
    print("2. Running DuckDuckGo search (real-time, no hardcoded results)...")

    from shared.search_adapter import discover_social_posts
    urls = discover_social_posts(
        candidate_name=candidate_name,
        extra_keywords="social media profile photo",
        max_results=max_results,
    )

    if urls:
        print(f"3. Search complete — {len(urls)} URL(s) discovered:")
        for i, url in enumerate(urls, 1):
            print(f"   [{i}] {url}")
    else:
        print("3. Search returned 0 results.")
        print("   Note: No result was fabricated. Genuine search found nothing for this candidate.")
        print("   Tip: Use a real public figure's photo for a genuine web match.")

    return urls


# =====================================================================
# MODULE 2: Post Verification (unchanged — existing implementation)
# =====================================================================
async def run_module_2(module1_data: dict, claimed_urls: list) -> dict:
    print("\n--- [STEP 3: MODULE 2 — POST VERIFICATION] ---")

    if not claimed_urls:
        print("[WARNING] No URLs to verify — returning not_verified result.")
        return {
            "schema_version": "2.0",
            "status": "not_verified",
            "input": {"image_path": module1_data.get("image_path")},
            "match": None,
            "verification": None,
            "checked": {
                "urls_provided": 0, "urls_deduplicated": 0, "urls_fetched": 0,
            },
            "consent": {"consent_scope": "self_verification", "consent_confirmed": True},
        }

    from member2_verify import (
        ConsentRecord,
        ConsentScope,
        VerificationPipeline,
    )

    face_embedding = module1_data.get("face_embedding")
    image_path     = module1_data.get("image_path")

    print(f"1. Validating consent scope: 'self_verification'")
    print(f"2. Fetching {len(claimed_urls)} URL(s)...")

    consent = ConsentRecord(
        consent_confirmed=True,
        consent_scope=ConsentScope.SELF_VERIFICATION,
        consent_timestamp="2026-09-06T00:00:00Z",
    )

    pipeline = VerificationPipeline()
    try:
        output = await pipeline.run(
            image_path=image_path,
            face_embedding=face_embedding,
            claimed_urls=claimed_urls,
            consent=consent,
            schema_version="2.0",
        )
    except Exception as exc:
        print(f"[ERROR] Module 2 pipeline error: {exc}")
        return {
            "schema_version": "2.0",
            "status": "not_verified",
            "input": {"image_path": image_path},
            "match": None, "verification": None,
            "checked": {"urls_provided": len(claimed_urls), "urls_deduplicated": len(claimed_urls), "urls_fetched": 0},
            "consent": {"consent_scope": "self_verification", "consent_confirmed": True},
        }

    result = output.to_dict()
    status = result.get("status", "unknown")
    match  = result.get("match")

    print(f"3. Verification status: {status.upper()}")
    if match:
        print(f"   Matched URL: {match.get('url')}")
        print(f"   Caption: {match.get('caption', 'N/A')}")
        verif = result.get("verification") or {}
        print(f"   Similarity: {verif.get('raw_similarity', 0):.4f}")
        print(f"   Confidence: {verif.get('calibrated_confidence', 0):.4f}")
    return result


# =====================================================================
# MODULE 3: Blockchain (unchanged — existing implementation)
# =====================================================================
def run_module_3(module2_result: dict):
    """Use shared chain_client + offchain_store for in-process mock continuity."""
    print("\n--- [STEP 4: MODULE 3 — BLOCKCHAIN ANCHORING] ---")

    from member3_blockchain import MockChainClient, OffchainStore
    from member3_blockchain.upload_pipeline import UploadPipeline
    from member3_blockchain.config import load_config_from_env

    config = load_config_from_env()
    chain_client   = MockChainClient(network=config.network)
    offchain_store = OffchainStore(config.offchain_store_path)

    pipeline = UploadPipeline(
        chain_client=chain_client,
        offchain_store=offchain_store,
    )

    print("1. Generating SHA-256 fingerprint from verified record...")
    try:
        upload_result = pipeline.process(module2_result)
    except Exception as exc:
        print(f"[ERROR] Module 3 upload error: {exc}")
        return None, None, None

    result_dict = upload_result.to_dict()
    record_hash = result_dict["record_hash"]
    reference_id = result_dict["reference_id"]

    print(f"2. Record Hash: {record_hash}")
    print(f"3. Network:     {config.network}  [MOCK — development mode]")
    print(f"4. Transaction ID: {reference_id}")
    print(f"5. Status: ANCHORED")

    return result_dict, chain_client, offchain_store


def run_reverify(module2_result: dict, upload_result: dict, chain_client, offchain_store):
    print("\n--- [STEP 5: RE-VERIFICATION] ---")

    from member3_blockchain.reverify_pipeline import ReverificationPipeline

    pipeline = ReverificationPipeline(
        chain_client=chain_client,
        offchain_store=offchain_store,
    )

    reference_id = upload_result["reference_id"]
    reverif = pipeline.process(
        reference_id=reference_id,
        current_verification_result=module2_result,
    )

    result = reverif.to_dict()
    print(f"1. Stored hash:   {result.get('on_chain_hash')}")
    print(f"2. Current hash:  {result.get('recomputed_hash')}")
    print(f"3. Hash match:    {'YES' if result.get('match') else 'NO'}")
    print(f"4. Status:        {result.get('status', '').upper()}")
    return result


def run_tamper_test(module2_result: dict, upload_result: dict, chain_client, offchain_store):
    print("\n" + "=" * 60)
    print("TAMPER TEST")
    print("=" * 60)

    from member3_blockchain.reverify_pipeline import ReverificationPipeline

    pipeline = ReverificationPipeline(
        chain_client=chain_client,
        offchain_store=offchain_store,
    )

    tampered = copy.deepcopy(module2_result)
    if tampered.get("match"):
        tampered["match"]["caption"] = "ATTACKER_INJECTED_CONTENT"
        tampered["match"]["url"]     = "https://attacker.evil.com/fake_post"
    if tampered.get("verification"):
        tampered["verification"]["raw_similarity"] = 0.99

    print("Original data → should be VERIFIED")
    reverif_orig = pipeline.process(
        reference_id=upload_result["reference_id"],
        current_verification_result=module2_result,
    )
    print(f"  Hash match: {'YES' if reverif_orig.match else 'NO'} → {'✅ VERIFIED' if reverif_orig.match else '❌ TAMPERED'}")

    print("\nModified data → should be TAMPERED")
    reverif_tampered = pipeline.process(
        reference_id=upload_result["reference_id"],
        current_verification_result=tampered,
    )
    orig_h   = reverif_tampered.on_chain_hash or ""
    tamper_h = reverif_tampered.recomputed_hash or ""
    print(f"  Stored Hash:  {orig_h[:32]}...")
    print(f"  Current Hash: {tamper_h[:32]}...")
    print(f"  Hash match: {'YES' if reverif_tampered.match else 'NO'} → {'✅ VERIFIED' if reverif_tampered.match else '❌ TAMPERED'}")


# =====================================================================
# MAIN
# =====================================================================
async def _main():
    import argparse
    parser = argparse.ArgumentParser(description="VeriFace E2E Demo")
    parser.add_argument("--image",      "-i", default=os.path.join(MODULE1_DIR, "data", "input", "input.jpg"))
    parser.add_argument("--candidates", "-c", default=os.path.join(MODULE1_DIR, "data", "candidates"))
    parser.add_argument("--url",        nargs="*", default=[], help="Manual URLs (bypasses search)")
    parser.add_argument("--max-search", type=int, default=5)
    parser.add_argument("--tamper-test", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("VERIFACE — End-to-End Pipeline Demo")
    print("=" * 60)

    # Step 1+2: Module 1
    m1_data = run_module_1(args.image, args.candidates)
    if m1_data is None:
        print("\n[ABORT] Module 1 failed.")
        return

    # Step 3: Genuine Search or Manual URLs
    if args.url:
        print("\n--- [STEP 2: MANUAL URLS PROVIDED — search bypassed] ---")
        discovered_urls = args.url
    else:
        discovered_urls = run_genuine_search(m1_data, max_results=args.max_search)

    # Step 4: Module 2
    m2_result = await run_module_2(m1_data, discovered_urls)

    # For Module 3 we need status == 'verified'.
    # If search found nothing or M2 failed, we run M3 in demo mode with explicit label.
    if m2_result.get("status") != "verified":
        print("\n[INFO] Module 2 returned non-verified status.")
        print("       Proceeding with Module 3 in DEMO MODE (unverified record).")
        print("       In production, only verified records would be anchored.")

    # Step 5: Module 3 upload
    m3_upload, chain_client, offchain_store = run_module_3(m2_result)
    if m3_upload is None:
        print("\n[ABORT] Module 3 upload failed.")
        return

    # Step 6: Re-verification
    reverif = run_reverify(m2_result, m3_upload, chain_client, offchain_store)

    # Final result
    print("\n" + "=" * 60)
    if reverif.get("match"):
        print("FINAL RESULT: ✅ VERIFIED")
    else:
        print("FINAL RESULT: ❌ NOT VERIFIED / TAMPERED")
    print("=" * 60)

    # Optional tamper test
    if args.tamper_test:
        run_tamper_test(m2_result, m3_upload, chain_client, offchain_store)


if __name__ == "__main__":
    asyncio.run(_main())
