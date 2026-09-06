"""
Unit tests for chain_client.py (MockChainClient, data minimization, and error handling).
"""

import pytest
from member3_blockchain.chain_client import MockChainClient, validate_on_chain_data_minimization
from member3_blockchain.config import RateLimiter
from member3_blockchain.exceptions import (
    ChainClientError,
    ChainConnectionError,
    ChainTransactionError,
    RateLimitExceededError,
)


def test_mock_chain_client_write_and_read():
    """Test successful write and subsequent read of a record hash."""
    client = MockChainClient(network="sepolia-testnet")
    record_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    metadata = {"timestamp": "2026-09-06T12:00:00Z", "schema_version": "2.0"}

    reference_id = client.write_record(record_hash, metadata)
    assert reference_id.startswith("0x")
    assert len(reference_id) == 66  # 0x + 64 hex

    # Read back
    onchain_data = client.read_record(reference_id)
    assert onchain_data["reference_id"] == reference_id
    assert onchain_data["record_hash"] == record_hash
    assert onchain_data["schema_version"] == "2.0"
    assert onchain_data["block_number"] > 0


def test_data_minimization_blocks_pii_on_chain():
    """Attempting to write personal data, URLs, or embeddings must fail immediately."""
    client = MockChainClient()
    record_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    prohibited_metadata = [
        {"url": "https://instagram.com/p/123"},
        {"image_url": "https://cdn.example.com/face.jpg"},
        {"caption": "Selfie at Hackathon"},
        {"face_embedding": [0.1, 0.2, 0.3]},
        {"name": "Alice Smith"},
        {"username": "alicesmith"},
    ]

    for meta in prohibited_metadata:
        with pytest.raises(ChainClientError) as exc_info:
            client.write_record(record_hash, meta)
        assert "Data minimization violation" in str(exc_info.value)


def test_mock_chain_simulated_timeout():
    """Verify that network timeouts are translated into ChainConnectionError."""
    client = MockChainClient()
    client.simulate_timeout = True

    with pytest.raises(ChainConnectionError):
        client.write_record("hash123", {"timestamp": "now"})

    with pytest.raises(ChainConnectionError):
        client.read_record("0x123")


def test_mock_chain_simulated_tx_failure():
    """Verify that transaction revert/out-of-gas errors raise ChainTransactionError."""
    client = MockChainClient()
    client.simulate_tx_failure = True
    client.simulate_revert_message = "Execution reverted: Out of gas"

    with pytest.raises(ChainTransactionError) as exc_info:
        client.write_record("hash123", {"timestamp": "now"})
    assert "Out of gas" in str(exc_info.value)


def test_cost_guard_rate_limiter():
    """Verify that cost-guard blocks excessive writes exceeding the per-minute threshold."""
    limiter = RateLimiter(max_per_minute=3)
    client = MockChainClient(rate_limiter=limiter)

    # 3 allowed writes
    for i in range(3):
        client.write_record(f"hash_{i}", {"timestamp": "now"})

    # 4th write must be blocked by cost guard
    with pytest.raises(RateLimitExceededError):
        client.write_record("hash_excess", {"timestamp": "now"})


def test_mock_chain_nonexistent_record():
    """Reading an unknown reference_id returns an empty dict without crashing."""
    client = MockChainClient()
    result = client.read_record("0xnonexistent")
    assert result == {}
