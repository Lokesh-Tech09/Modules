"""
Integration tests: Module 1 → Module 2 → Module 3 full pipeline.
Tests without requiring real InsightFace models (mocked where needed).
"""

import asyncio
import copy
import json
import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "member1_face"))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

MOCK_VERIFICATION_RESULT = {
    "schema_version": "2.0",
    "status": "verified",
    "input": {"image_path": "test_face.jpg"},
    "match": {
        "url": "https://example.com/post/test123",
        "image_url": "https://example.com/images/test.jpg",
        "local_image_path": None,
        "caption": "Test post for integration testing",
        "metadata": {"source": "test"},
    },
    "verification": {
        "raw_similarity": 0.85,
        "calibrated_confidence": 0.88,
        "low_confidence_detection": False,
    },
    "checked": {
        "urls_provided": 1,
        "urls_deduplicated": 1,
        "urls_fetched": 1,
        "urls_blocked": 0,
        "urls_failed": 0,
        "cache_hits": 0,
    },
    "consent": {
        "consent_scope": "self_verification",
        "consent_confirmed": True,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Module 3 tests (fully self-contained — no network, no InsightFace needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestModule3Hasher:
    """SHA-256 hashing and canonicalization tests."""

    def test_hash_is_deterministic(self):
        from member3_blockchain.hasher import hash_verification_record
        result1 = hash_verification_record(MOCK_VERIFICATION_RESULT)
        result2 = hash_verification_record(MOCK_VERIFICATION_RESULT)
        assert result1.record_hash == result2.record_hash, (
            "Hashing must be deterministic — same input must always produce same hash."
        )

    def test_hash_is_sha256(self):
        from member3_blockchain.hasher import hash_verification_record
        result = hash_verification_record(MOCK_VERIFICATION_RESULT)
        assert len(result.record_hash) == 64, "SHA-256 hex digest must be 64 characters."
        assert all(c in "0123456789abcdef" for c in result.record_hash)

    def test_modified_data_changes_hash(self):
        from member3_blockchain.hasher import hash_verification_record
        original = hash_verification_record(MOCK_VERIFICATION_RESULT)
        tampered = copy.deepcopy(MOCK_VERIFICATION_RESULT)
        tampered["match"]["caption"] = "ATTACKER_INJECTED_CAPTION"
        tampered_result = hash_verification_record(tampered)
        assert original.record_hash != tampered_result.record_hash, (
            "Tampered data must produce a different hash."
        )

    def test_canonical_json_has_sorted_keys(self):
        from member3_blockchain.hasher import canonicalize_verification_record
        canonical = canonicalize_verification_record(MOCK_VERIFICATION_RESULT)
        parsed = json.loads(canonical)
        keys = list(parsed.keys())
        assert keys == sorted(keys), "Canonical JSON must have sorted keys."

    def test_excludes_ephemeral_fields(self):
        from member3_blockchain.hasher import canonicalize_verification_record
        data_with_local = copy.deepcopy(MOCK_VERIFICATION_RESULT)
        # Add local fields that should be excluded
        data_with_local["match"]["local_image_path"] = "/tmp/some/local/path.jpg"
        data_with_local["face_embedding"] = [0.1] * 512
        canonical = canonicalize_verification_record(data_with_local)
        assert "local_image_path" not in canonical
        assert "face_embedding" not in canonical


class TestMockChainClient:
    """MockChainClient write/read tests."""

    def setup_method(self):
        from member3_blockchain import MockChainClient
        self.client = MockChainClient(network="sepolia-testnet")

    def test_write_and_read_roundtrip(self):
        record_hash = "a" * 64
        metadata = {"schema_version": "2.0", "timestamp": "2026-09-06T00:00:00Z"}
        ref_id = self.client.write_record(record_hash, metadata)
        assert ref_id, "write_record must return a non-empty reference_id."
        record = self.client.read_record(ref_id)
        assert record.get("record_hash") == record_hash
        assert record.get("network") == "sepolia-testnet"

    def test_data_minimization_blocks_pii(self):
        from member3_blockchain.exceptions import ChainClientError
        with pytest.raises(ChainClientError):
            self.client.write_record(
                "b" * 64,
                {"url": "https://bad.example.com", "schema_version": "2.0"},
            )

    def test_unknown_reference_returns_empty(self):
        result = self.client.read_record("nonexistent-ref-id-xyz")
        assert result == {}, "Unknown reference_id must return empty dict."

    def test_block_number_increments(self):
        r1 = self.client.write_record("c" * 64, {"schema_version": "2.0"})
        r2 = self.client.write_record("d" * 64, {"schema_version": "2.0"})
        rec1 = self.client.read_record(r1)
        rec2 = self.client.read_record(r2)
        assert rec2["block_number"] > rec1["block_number"]


class TestUploadPipeline:
    """UploadPipeline integration test."""

    def test_upload_verified_record(self):
        from member3_blockchain import MockChainClient, OffchainStore
        from member3_blockchain.upload_pipeline import UploadPipeline

        client = MockChainClient()
        store  = OffchainStore(":memory:")
        pipeline = UploadPipeline(chain_client=client, offchain_store=store)
        result = pipeline.process(MOCK_VERIFICATION_RESULT)

        assert result.status == "uploaded"
        assert result.record_hash, "record_hash must be non-empty"
        assert result.reference_id, "reference_id must be non-empty"
        assert len(result.record_hash) == 64

    def test_upload_rejects_unverified_record(self):
        from member3_blockchain import MockChainClient, OffchainStore
        from member3_blockchain.upload_pipeline import UploadPipeline
        from member3_blockchain.exceptions import UnverifiedRecordError

        client = MockChainClient()
        store  = OffchainStore(":memory:")
        pipeline = UploadPipeline(chain_client=client, offchain_store=store)

        unverified = copy.deepcopy(MOCK_VERIFICATION_RESULT)
        unverified["status"] = "not_verified"

        with pytest.raises(UnverifiedRecordError):
            pipeline.process(unverified)


class TestReverifyPipeline:
    """End-to-end upload + reverify tamper detection."""

    def _upload(self, data):
        from member3_blockchain import MockChainClient, OffchainStore
        from member3_blockchain.upload_pipeline import UploadPipeline
        from member3_blockchain.reverify_pipeline import ReverificationPipeline
        client   = MockChainClient()
        store    = OffchainStore(":memory:")
        uploader = UploadPipeline(chain_client=client, offchain_store=store)
        reverifier = ReverificationPipeline(chain_client=client, offchain_store=store)
        return uploader, reverifier, client, store

    def test_intact_data_is_verified(self):
        from member3_blockchain import MockChainClient, OffchainStore
        from member3_blockchain.upload_pipeline import UploadPipeline
        from member3_blockchain.reverify_pipeline import ReverificationPipeline

        client   = MockChainClient()
        store    = OffchainStore(":memory:")
        uploader = UploadPipeline(chain_client=client, offchain_store=store)
        reverifier = ReverificationPipeline(chain_client=client, offchain_store=store)

        upload_result = uploader.process(MOCK_VERIFICATION_RESULT)
        reverif = reverifier.process(
            reference_id=upload_result.reference_id,
            current_verification_result=MOCK_VERIFICATION_RESULT,
        )
        assert reverif.match is True, "Unchanged data must produce VERIFIED status."
        assert reverif.status == "intact"

    def test_tampered_data_is_detected(self):
        from member3_blockchain import MockChainClient, OffchainStore
        from member3_blockchain.upload_pipeline import UploadPipeline
        from member3_blockchain.reverify_pipeline import ReverificationPipeline

        client   = MockChainClient()
        store    = OffchainStore(":memory:")
        uploader = UploadPipeline(chain_client=client, offchain_store=store)
        reverifier = ReverificationPipeline(chain_client=client, offchain_store=store)

        upload_result = uploader.process(MOCK_VERIFICATION_RESULT)

        tampered = copy.deepcopy(MOCK_VERIFICATION_RESULT)
        tampered["match"]["caption"] = "INJECTED BY ATTACKER"
        tampered["match"]["url"]     = "https://evil.com/fake"

        reverif = reverifier.process(
            reference_id=upload_result.reference_id,
            current_verification_result=tampered,
        )
        assert reverif.match is False, "Tampered data must produce TAMPERED status."
        assert reverif.status == "tampered"
        assert reverif.on_chain_hash != reverif.recomputed_hash


class TestSearchAdapter:
    """Search adapter unit tests (no actual network calls)."""

    def test_empty_candidate_name_returns_empty(self):
        from shared.search_adapter import discover_social_posts
        result = discover_social_posts(candidate_name="")
        assert result == []

    def test_none_candidate_name_returns_empty(self):
        from shared.search_adapter import discover_social_posts
        result = discover_social_posts(candidate_name=None)
        assert result == []

    def test_adapter_factory_returns_adapter(self):
        from shared.search_adapter import get_search_adapter, SearchAdapter
        adapter = get_search_adapter()
        assert isinstance(adapter, SearchAdapter)


class TestModule1Adapter:
    """Module 1 adapter unit tests (no InsightFace model needed for error paths)."""

    def test_missing_image_returns_error_result(self):
        from member1_face.adapter import run_face_identification
        result = run_face_identification(image_path="/nonexistent/path/face.jpg")
        assert result.face_detected is False
        assert result.status in ("ERROR_INVALID_IMAGE", "ERROR_IMPORT", "ERROR_PIPELINE")

    def test_result_to_dict_structure(self):
        from member1_face.adapter import M1Result
        r = M1Result(
            face_detected=True,
            candidate="candidate1.jpg",
            candidate_path="/path/candidate1.jpg",
            similarity=0.82,
            match=True,
            status="MATCH",
            face_embedding=[0.1] * 512,
        )
        d = r.to_dict()
        assert "face_detected"  in d
        assert "candidate"      in d
        assert "similarity"     in d
        assert "match"          in d
        assert "status"         in d
        assert "face_embedding" in d
        assert len(d["face_embedding"]) == 512


class TestSocialScraper:
    """Social media scraper unit tests."""

    def test_platform_detection(self):
        from member2_verify import SocialScraper
        scraper = SocialScraper()
        assert scraper.detect_platform("https://www.instagram.com/p/C123xyz/") == "instagram"
        assert scraper.detect_platform("https://www.linkedin.com/posts/activity-12345") == "linkedin"
        assert scraper.detect_platform("https://x.com/user/status/123456") == "twitter"
        assert scraper.detect_platform("https://twitter.com/user/status/123456") == "twitter"
        assert scraper.detect_platform("https://facebook.com/post/123") == "facebook"
        assert scraper.detect_platform("https://example.com/blog/article") == "web"

    def test_fallback_social_post_structure(self):
        from member2_verify import SocialScraper
        scraper = SocialScraper()
        post = scraper._fallback_social_post("https://instagram.com/p/test", "instagram")
        assert post.platform == "instagram"
        assert post.post_url == "https://instagram.com/p/test"
        assert post.image_url is None
        d = post.to_dict()
        assert d["platform"] == "instagram"
        assert "url" in d
        assert "caption" in d

    def test_extract_social_posts_convenience(self):
        from member2_verify import extract_social_posts
        results = extract_social_posts(["https://unknown-site-12345.org/test"])
        assert len(results) == 1
        assert results[0]["platform"] == "web"


class TestWebcamMock:
    """Webcam capture mock mode tests."""

    def test_mock_capture_creates_file(self, tmp_path):
        from member1_face.capture_webcam import mock_capture
        test_out = str(tmp_path / "mock_face.jpg")
        result = mock_capture(output_path=test_out)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0


class TestContractDeploymentDryRun:
    """Solidity contract deployment dry-run test."""

    def test_deploy_contract_dry_run(self):
        from member3_blockchain.deploy_contract import deploy_contract
        addr = deploy_contract(
            rpc_url="https://mock.rpc",
            private_key="",
            dry_run=True,
        )
        assert addr.startswith("0x")
        assert len(addr) == 42

