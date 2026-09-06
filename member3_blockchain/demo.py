"""
Standalone demonstration script for Module 3: Blockchain Upload & Re-verification.
Can be executed independently of Module 1 and Module 2.
"""

import json
from pathlib import Path
import sys

# Ensure project root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from member3_blockchain import (
    BlockchainConfig,
    OffchainStore,
    MockChainClient,
    reverify_record,
    upload_verification_record,
)


def run_demo():
    print("=" * 80)
    print("MODULE 3 — BLOCKCHAIN UPLOAD & RE-VERIFICATION DEMO")
    print("=" * 80)

    # 1. Mocked input received from Module 2
    mock_module2_output = {
        "schema_version": "2.0",
        "status": "verified",
        "match": {
            "url": "https://instagram.com/p/candidate_01",
            "image_url": "https://cdn.instagram.com/v/photo_123.jpg",
            "local_image_path": "temp/candidate_01.jpg",
            "caption": "Summit selfie at Goa Hackathon! #ConsentedVerification",
            "metadata": {"platform": "instagram"},
        },
        "verification": {
            "raw_similarity": 0.971,
            "calibrated_confidence": 0.94,
            "low_confidence_detection": False,
        },
        "consent": {
            "consent_scope": "self_verification",
            "consent_confirmed": True,
        },
    }

    print("\n[STEP 1] Received Verified Record from Module 2:")
    print(f"  Status: {mock_module2_output['status']}")
    print(f"  Matched URL: {mock_module2_output['match']['url']}")
    print(f"  Calibrated Confidence: {mock_module2_output['verification']['calibrated_confidence']}")

    # Configure isolated in-memory chain and storage for demo
    chain_client = MockChainClient(network="sepolia-testnet")
    store = OffchainStore(db_path=":memory:")
    config = BlockchainConfig(network="sepolia-testnet")

    # 2. Upload verification record
    print("\n[STEP 2] Canonicalizing, Hashing & Anchoring on-chain...")
    upload_result = upload_verification_record(
        mock_module2_output,
        config=config,
        chain_client=chain_client,
        offchain_store=store,
    )

    print("  -> Upload Successful!")
    print(json.dumps(upload_result.to_dict(), indent=2))

    # 3. Re-verification (Integrity Check)
    ref_id = upload_result.reference_id
    print(f"\n[STEP 3] Re-verifying Record Integrity (Reference ID: {ref_id[:16]}...):")
    intact_result = reverify_record(
        reference_id=ref_id,
        chain_client=chain_client,
        offchain_store=store,
    )
    print("  -> Result of Untampered Record:")
    print(json.dumps(intact_result.to_dict(), indent=2))
    assert intact_result.match is True

    # 4. Tamper Detection Demonstration
    print("\n[STEP 4] Simulating Data Tampering Attack in Off-chain Storage...")
    stored_rec = store.get_record(ref_id)
    stored_rec["verification"]["calibrated_confidence"] = 0.999  # Forged score
    store.save_record(ref_id, stored_rec, "forged_hash")
    print("  -> Tampered score saved in off-chain store (0.940 -> 0.999)")

    print("  -> Running Re-verification on Tampered Record:")
    tampered_result = reverify_record(
        reference_id=ref_id,
        chain_client=chain_client,
        offchain_store=store,
    )
    print(json.dumps(tampered_result.to_dict(), indent=2))
    assert tampered_result.match is False
    assert tampered_result.status == "tampered"
    print("  -> SUCCESS: Tamper was immediately caught and flagged!")

    # 5. Non-existent record demonstration
    print("\n[STEP 5] Querying Unknown Reference ID:")
    not_found_result = reverify_record(
        reference_id="0xnonexistent123456",
        chain_client=chain_client,
        offchain_store=store,
    )
    print(json.dumps(not_found_result.to_dict(), indent=2))
    assert not_found_result.status == "not_found"

    print("\n" + "=" * 80)
    print("DEMONSTRATION COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
