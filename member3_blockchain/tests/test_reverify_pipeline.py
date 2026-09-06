"""
Unit tests for reverify_pipeline.py (tamper detection and cryptographic integrity).
"""

import pytest
from member3_blockchain.chain_client import MockChainClient
from member3_blockchain.offchain_store import OffchainStore
from member3_blockchain.reverify_pipeline import reverify_record
from member3_blockchain.upload_pipeline import upload_verification_record


@pytest.fixture
def sample_verified_record():
    return {
        "schema_version": "2.0",
        "status": "verified",
        "match": {
            "url": "https://instagram.com/p/candidate_01",
            "image_url": "https://cdn.example.com/face.jpg",
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


def test_reverify_intact_record(sample_verified_record):
    """An unaltered record must return status 'intact' with matching hashes."""
    chain_client = MockChainClient()
    store = OffchainStore(db_path=":memory:")

    # 1. Upload original record
    upload_res = upload_verification_record(
        sample_verified_record,
        chain_client=chain_client,
        offchain_store=store,
    )
    ref_id = upload_res.reference_id

    # 2. Re-verify record stored in off-chain database
    reverify_res = reverify_record(
        reference_id=ref_id,
        chain_client=chain_client,
        offchain_store=store,
    )

    assert reverify_res.status == "intact"
    assert reverify_res.match is True
    assert reverify_res.reference_id == ref_id
    assert reverify_res.on_chain_hash == upload_res.record_hash
    assert reverify_res.recomputed_hash == upload_res.record_hash

    # Check to_dict() compliance
    d = reverify_res.to_dict()
    assert d["status"] == "intact"
    assert d["match"] is True


def test_reverify_detects_tampered_offchain_record(sample_verified_record):
    """If the off-chain record is modified, re-verification must report 'tampered'."""
    chain_client = MockChainClient()
    store = OffchainStore(db_path=":memory:")

    # 1. Upload original record
    upload_res = upload_verification_record(
        sample_verified_record,
        chain_client=chain_client,
        offchain_store=store,
    )
    ref_id = upload_res.reference_id

    # 2. Tamper with the off-chain database directly (simulate attacker modifying confidence score)
    tampered_record = store.get_record(ref_id)
    assert tampered_record is not None
    tampered_record["verification"]["calibrated_confidence"] = 0.999  # Forgery!
    # Update off-chain store with the altered record
    store.save_record(ref_id, tampered_record, "forged_hash")

    # 3. Re-verify
    reverify_res = reverify_record(
        reference_id=ref_id,
        chain_client=chain_client,
        offchain_store=store,
    )

    assert reverify_res.status == "tampered"
    assert reverify_res.match is False
    assert reverify_res.on_chain_hash == upload_res.record_hash
    assert reverify_res.recomputed_hash != upload_res.record_hash
    assert reverify_res.recomputed_hash is not None


def test_reverify_detects_tampered_candidate_input(sample_verified_record):
    """If a caller passes a modified candidate record to test, it detects tampering."""
    chain_client = MockChainClient()
    store = OffchainStore(db_path=":memory:")

    upload_res = upload_verification_record(
        sample_verified_record,
        chain_client=chain_client,
        offchain_store=store,
    )
    ref_id = upload_res.reference_id

    # Candidate with altered URL
    candidate_tampered = dict(sample_verified_record)
    candidate_tampered["match"] = dict(sample_verified_record["match"])
    candidate_tampered["match"]["url"] = "https://fraudulent-account.com/fake_profile"

    reverify_res = reverify_record(
        reference_id=ref_id,
        current_verification_result=candidate_tampered,
        chain_client=chain_client,
        offchain_store=store,
    )

    assert reverify_res.status == "tampered"
    assert reverify_res.match is False


def test_reverify_unknown_reference_id():
    """An unknown reference_id must return status 'not_found'."""
    chain_client = MockChainClient()
    store = OffchainStore(db_path=":memory:")

    reverify_res = reverify_record(
        reference_id="0xdeadbeef1234567890",
        chain_client=chain_client,
        offchain_store=store,
    )

    assert reverify_res.status == "not_found"
    assert reverify_res.match is False
    assert reverify_res.on_chain_hash is None
    assert reverify_res.recomputed_hash is None
