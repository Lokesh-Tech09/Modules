"""
Unit tests for offchain_store.py (SQLite local repository and access controls).
"""

import pytest
from member3_blockchain.exceptions import OffchainStoreError
from member3_blockchain.offchain_store import OffchainStore


@pytest.fixture
def memory_store():
    """Fixture providing an in-memory SQLite store for isolated unit tests."""
    store = OffchainStore(db_path=":memory:")
    yield store
    store.close()


def test_save_and_retrieve_record(memory_store):
    """Test saving a full verification record and retrieving it intact."""
    ref_id = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    record_hash = "11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff"
    record_data = {
        "schema_version": "2.0",
        "status": "verified",
        "match": {
            "url": "https://instagram.com/p/candidate_01",
            "image_url": "https://cdn.example.com/face.jpg",
            "caption": "A test caption",
        },
        "verification": {"calibrated_confidence": 0.94},
    }

    # Save record
    memory_store.save_record(ref_id, record_data, record_hash)

    # Check existence
    assert memory_store.record_exists(ref_id) is True

    # Retrieve and verify payload
    retrieved = memory_store.get_record(ref_id)
    assert retrieved is not None
    assert retrieved["status"] == "verified"
    assert retrieved["match"]["url"] == "https://instagram.com/p/candidate_01"
    assert retrieved["verification"]["calibrated_confidence"] == 0.94


def test_retrieve_nonexistent_record(memory_store):
    """Retrieving a record that does not exist returns None."""
    assert memory_store.record_exists("0xunknown") is False
    assert memory_store.get_record("0xunknown") is None


def test_list_records(memory_store):
    """Test listing record summaries."""
    for i in range(3):
        memory_store.save_record(
            reference_id=f"0x{i}abc",
            record={"index": i, "status": "verified"},
            record_hash=f"hash_{i}",
        )

    records = memory_store.list_records()
    assert len(records) == 3
    ref_ids = {r["reference_id"] for r in records}
    assert ref_ids == {"0x0abc", "0x1abc", "0x2abc"}


def test_delete_record(memory_store):
    """Test deleting an existing record."""
    ref_id = "0xdeleteme"
    memory_store.save_record(ref_id, {"status": "verified"}, "hash_del")
    assert memory_store.record_exists(ref_id) is True

    deleted = memory_store.delete_record(ref_id)
    assert deleted is True
    assert memory_store.record_exists(ref_id) is False

    # Deleting again returns False
    assert memory_store.delete_record(ref_id) is False


def test_empty_reference_id_raises_error(memory_store):
    """Saving with empty reference_id raises OffchainStoreError."""
    with pytest.raises(OffchainStoreError):
        memory_store.save_record("", {"status": "verified"}, "hash")
