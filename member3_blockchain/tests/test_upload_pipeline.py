"""
Unit tests for upload_pipeline.py (orchestration, validation, and data minimization).
"""

import pytest
from member3_blockchain.chain_client import MockChainClient
from member3_blockchain.exceptions import (
    ChainConnectionError,
    UnverifiedRecordError,
)
from member3_blockchain.models import BlockchainConfig
from member3_blockchain.offchain_store import OffchainStore
from member3_blockchain.upload_pipeline import upload_verification_record


@pytest.fixture
def valid_verified_record():
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


def test_upload_verified_record_success(valid_verified_record):
    """Test full upload pipeline happy path for verified record."""
    chain_client = MockChainClient(network="sepolia-testnet")
    store = OffchainStore(db_path=":memory:")
    config = BlockchainConfig(network="sepolia-testnet")

    result = upload_verification_record(
        valid_verified_record,
        config=config,
        chain_client=chain_client,
        offchain_store=store,
    )

    # Validate output contract
    assert result.status == "uploaded"
    assert result.reference_id.startswith("0x")
    assert len(result.record_hash) == 64
    assert result.chain.confirmed is True
    assert result.chain.network == "sepolia-testnet"
    assert result.chain.block_number > 0

    # Validate to_dict() contract
    res_dict = result.to_dict()
    assert res_dict["status"] == "uploaded"
    assert res_dict["reference_id"] == result.reference_id
    assert res_dict["chain"]["confirmed"] is True

    # Validate off-chain store holds the full record
    stored = store.get_record(result.reference_id)
    assert stored is not None
    assert stored["match"]["url"] == "https://instagram.com/p/candidate_01"


def test_upload_unverified_record_rejected():
    """Records with status != 'verified' must be refused immediately."""
    chain_client = MockChainClient()
    store = OffchainStore(db_path=":memory:")

    unverified_records = [
        {"status": "not_verified", "schema_version": "2.0"},
        {"status": "search_failed", "schema_version": "2.0"},
        {"status": "rejected", "schema_version": "2.0"},
        {"status": "", "schema_version": "2.0"},
        {},
    ]

    for rec in unverified_records:
        with pytest.raises(UnverifiedRecordError) as exc_info:
            upload_verification_record(
                rec,
                chain_client=chain_client,
                offchain_store=store,
            )
        assert "Only 'verified' records are permitted" in str(exc_info.value)


def test_upload_atomicity_on_chain_failure(valid_verified_record):
    """If the chain write fails, no orphan record should be left in off-chain storage."""
    chain_client = MockChainClient()
    chain_client.simulate_timeout = True  # Inject failure
    store = OffchainStore(db_path=":memory:")

    with pytest.raises(ChainConnectionError):
        upload_verification_record(
            valid_verified_record,
            chain_client=chain_client,
            offchain_store=store,
        )

    # Store must remain empty
    assert len(store.list_records()) == 0


def test_on_chain_data_minimization_verification(valid_verified_record):
    """Verify that what is stored on the chain client has NO PII or raw face data."""
    chain_client = MockChainClient()
    store = OffchainStore(db_path=":memory:")

    result = upload_verification_record(
        valid_verified_record,
        chain_client=chain_client,
        offchain_store=store,
    )

    onchain_data = chain_client.read_record(result.reference_id)
    
    # Assert allowed on-chain fields only
    allowed_keys = {"reference_id", "record_hash", "timestamp", "schema_version", "block_number", "network"}
    assert set(onchain_data.keys()).issubset(allowed_keys)

    # Explicitly check prohibited items are NOT in on-chain data
    prohibited_items = ["url", "image_url", "local_image_path", "caption", "face_embedding", "Alice", "instagram"]
    for key in prohibited_items:
        assert key not in onchain_data
        for val in onchain_data.values():
            assert key not in str(val)
