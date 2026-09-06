"""
Unit tests for hasher.py (canonicalization and cryptographic hashing).
"""

import pytest
from member3_blockchain.exceptions import CanonicalizationError
from member3_blockchain.hasher import (
    canonicalize_verification_record,
    hash_verification_record,
)


@pytest.fixture
def sample_verified_record():
    return {
        "schema_version": "2.0",
        "status": "verified",
        "match": {
            "url": "https://instagram.com/p/candidate_01",
            "image_url": "https://cdn.instagram.com/v/photo_123.jpg",
            "local_image_path": "temp/candidate_01.jpg",
            "caption": "Verified profile selfie at the hackathon",
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


def test_hasher_returns_valid_sha256(sample_verified_record):
    """Test that hash_verification_record produces a valid 64-character hex SHA-256 hash."""
    result = hash_verification_record(sample_verified_record)
    assert len(result.record_hash) == 64
    assert all(c in "0123456789abcdef" for c in result.record_hash.lower())
    assert result.algorithm == "sha256"
    assert "schema_version" in result.canonical_json


def test_canonicalization_key_order_invariance(sample_verified_record):
    """Different key orders of the same logical record must yield identical hashes."""
    # Reverse top-level keys
    reordered_1 = {
        "consent": sample_verified_record["consent"],
        "verification": sample_verified_record["verification"],
        "match": sample_verified_record["match"],
        "status": sample_verified_record["status"],
        "schema_version": sample_verified_record["schema_version"],
    }
    # Reverse inner keys
    reordered_2 = {
        "schema_version": "2.0",
        "status": "verified",
        "consent": {
            "consent_confirmed": True,
            "consent_scope": "self_verification",
        },
        "verification": {
            "low_confidence_detection": False,
            "calibrated_confidence": 0.94,
            "raw_similarity": 0.971,
        },
        "match": {
            "metadata": {"platform": "instagram"},
            "caption": "Verified profile selfie at the hackathon",
            "local_image_path": "temp/candidate_01.jpg",
            "image_url": "https://cdn.instagram.com/v/photo_123.jpg",
            "url": "https://instagram.com/p/candidate_01",
        },
    }

    hash_original = hash_verification_record(sample_verified_record).record_hash
    hash_reordered_1 = hash_verification_record(reordered_1).record_hash
    hash_reordered_2 = hash_verification_record(reordered_2).record_hash

    assert hash_original == hash_reordered_1
    assert hash_original == hash_reordered_2


def test_floating_point_drift_stability(sample_verified_record):
    """Microscopic floating point drift should be normalized and produce identical hashes."""
    drifted_record = dict(sample_verified_record)
    drifted_record["verification"] = {
        "raw_similarity": 0.9710000000000001,  # typical float precision drift
        "calibrated_confidence": 0.9400000000000001,
        "low_confidence_detection": False,
    }

    hash_normal = hash_verification_record(sample_verified_record).record_hash
    hash_drifted = hash_verification_record(drifted_record).record_hash

    assert hash_normal == hash_drifted


def test_ephemeral_fields_excluded_from_hash(sample_verified_record):
    """Changing local_image_path should not alter hash since it is an ephemeral local path."""
    altered_path_record = dict(sample_verified_record)
    altered_path_record["match"] = dict(sample_verified_record["match"])
    altered_path_record["match"]["local_image_path"] = "temp/different_temp_path.jpg"

    hash_original = hash_verification_record(sample_verified_record).record_hash
    hash_altered_path = hash_verification_record(altered_path_record).record_hash

    assert hash_original == hash_altered_path


def test_critical_fields_alter_hash(sample_verified_record):
    """Altering any verification score, URL, or consent must produce a different hash."""
    # 1. Tamper calibrated confidence
    tampered_confidence = dict(sample_verified_record)
    tampered_confidence["verification"] = dict(sample_verified_record["verification"])
    tampered_confidence["verification"]["calibrated_confidence"] = 0.85

    # 2. Tamper matched URL
    tampered_url = dict(sample_verified_record)
    tampered_url["match"] = dict(sample_verified_record["match"])
    tampered_url["match"]["url"] = "https://instagram.com/p/fraudulent_post"

    hash_orig = hash_verification_record(sample_verified_record).record_hash
    assert hash_orig != hash_verification_record(tampered_confidence).record_hash
    assert hash_orig != hash_verification_record(tampered_url).record_hash


def test_invalid_input_raises_canonicalization_error():
    """Passing a non-dict must raise CanonicalizationError."""
    with pytest.raises(CanonicalizationError):
        canonicalize_verification_record(["not", "a", "dict"])  # type: ignore
