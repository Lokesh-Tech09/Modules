"""
Integration tests for VerificationPipeline and verify_claimed_profile (v2).
Module 2: Claimed-Profile Verification (Self-Match).
"""

from unittest.mock import AsyncMock, MagicMock
import pytest

from member2_verify import verify_claimed_profile, verify_claimed_profile_sync
from member2_verify.cache import ContentHashCache
from member2_verify.candidate_fetcher import CandidateFetcher
from member2_verify.config import VerificationConfig
from member2_verify.exceptions import (
    ConsentRequiredError,
    EmptyClaimedUrlsError,
    InvalidInputError,
)
from member2_verify.face_matcher import FaceMatcher
from member2_verify.models import (
    CandidateFetchResult,
    ConsentRecord,
    ConsentScope,
    ExtractedPostMetadata,
    FaceDetection,
    FaceMatchDetail,
    FetchStatus,
)
from member2_verify.post_extractor import PostExtractor
from member2_verify.verification_pipeline import VerificationPipeline


@pytest.fixture
def mock_v2_pipeline(tmp_path):
    fetcher = MagicMock(spec=CandidateFetcher)
    extractor = MagicMock(spec=PostExtractor)
    extractor.extract.return_value = ExtractedPostMetadata(url="https://example.com/default")
    matcher = MagicMock(spec=FaceMatcher)
    cache = ContentHashCache()
    config = VerificationConfig(SIMILARITY_THRESHOLD=0.65)

    pipeline = VerificationPipeline(
        config=config,
        fetcher=fetcher,
        extractor=extractor,
        matcher=matcher,
        cache=cache,
    )
    return pipeline, fetcher, extractor, matcher, cache


@pytest.mark.asyncio
async def test_verification_v2_success_contract(mock_v2_pipeline, tmp_path):
    """
    Test v2 successful verification contract conforming strictly to Section 11.
    """
    pipeline, fetcher, extractor, matcher, cache = mock_v2_pipeline

    dummy_img = tmp_path / "candidate.jpg"
    dummy_img.write_bytes(b"dummy_img_bytes")

    fetcher.fetch_all = AsyncMock(return_value=[
        CandidateFetchResult(
            url="https://example.com/posts/alice",
            fetch_status=FetchStatus.SUCCESS,
            content_type="image/jpeg",
            image_bytes=b"dummy_img_bytes",
            local_image_path=str(dummy_img),
            extracted_metadata=ExtractedPostMetadata(
                url="https://example.com/posts/alice",
                image_url="https://cdn.example.com/alice.jpg",
                caption="Verified summit photo",
                metadata={"network": "test"},
            ),
        )
    ])

    matcher.compare_candidate_image.return_value = (
        True,
        0.971,
        0.940,
        False,
        FaceMatchDetail(
            face_index=0,
            raw_similarity=0.971,
            calibrated_confidence=0.940,
            low_confidence_detection=False,
        ),
    )

    consent = ConsentRecord(
        consent_confirmed=True,
        consent_scope=ConsentScope.SELF_VERIFICATION,
        consent_timestamp="2026-09-05T10:00:00Z",
    )

    result = await pipeline.run(
        image_path="input.jpg",
        face_embedding=[0.1] * 512,
        claimed_urls=["https://example.com/posts/alice"],
        consent=consent,
    )

    data = result.to_dict()

    # Schema version 2.0
    assert data["schema_version"] == "2.0"
    assert data["status"] == "verified"
    assert data["input"]["image_path"] == "input.jpg"

    # Match block
    assert data["match"] is not None
    assert data["match"]["url"] == "https://example.com/posts/alice"
    assert data["match"]["image_url"] == "https://cdn.example.com/alice.jpg"
    assert data["match"]["caption"] == "Verified summit photo"

    # Verification scores
    assert data["verification"]["raw_similarity"] == 0.971
    assert data["verification"]["calibrated_confidence"] == 0.940
    assert data["verification"]["low_confidence_detection"] is False

    # Checked block
    assert data["checked"]["urls_provided"] == 1
    assert data["checked"]["urls_deduplicated"] == 1
    assert data["checked"]["urls_fetched"] == 1
    assert data["checked"]["urls_blocked"] == 0
    assert data["checked"]["urls_failed"] == 0

    # Consent block
    assert data["consent"]["consent_confirmed"] is True
    assert data["consent"]["consent_scope"] == "self_verification"


@pytest.mark.asyncio
async def test_consent_scope_third_party_validation():
    """Verify authorized_third_party requires authorization_reference."""
    # Fails without authorization_reference
    with pytest.raises(ValueError, match="Authorization reference is required"):
        ConsentRecord(
            consent_confirmed=True,
            consent_scope=ConsentScope.AUTHORIZED_THIRD_PARTY,
        )

    # Succeeds with authorization_reference
    valid_consent = ConsentRecord(
        consent_confirmed=True,
        consent_scope=ConsentScope.AUTHORIZED_THIRD_PARTY,
        authorization_reference="AUTH-LEGAL-REF-2026-001",
    )
    assert valid_consent.authorization_reference == "AUTH-LEGAL-REF-2026-001"


@pytest.mark.asyncio
async def test_consent_rejected_when_unconfirmed(mock_v2_pipeline):
    """Verify rejection when consent_confirmed is False."""
    pipeline, _, _, _, _ = mock_v2_pipeline
    with pytest.raises(ConsentRequiredError):
        await pipeline.run(
            face_embedding=[0.1] * 512,
            claimed_urls=["https://example.com/post"],
            consent=ConsentRecord(consent_confirmed=False),
        )


@pytest.mark.asyncio
async def test_empty_claimed_urls_rejected(mock_v2_pipeline):
    """Verify structural anti-discovery refusal on empty URLs."""
    pipeline, _, _, _, _ = mock_v2_pipeline
    with pytest.raises(EmptyClaimedUrlsError):
        await pipeline.run(
            face_embedding=[0.1] * 512,
            claimed_urls=[],
            consent=ConsentRecord(consent_confirmed=True),
        )


@pytest.mark.asyncio
async def test_content_hash_caching_across_duplicate_images(mock_v2_pipeline, tmp_path):
    """
    Verify that identical image content across multiple URLs
    results in a cache hit on the second URL.
    """
    pipeline, fetcher, extractor, matcher, cache = mock_v2_pipeline

    img_file = tmp_path / "shared.jpg"
    img_bytes = b"shared_identical_image_bytes"
    img_file.write_bytes(img_bytes)

    fetcher.fetch_all = AsyncMock(return_value=[
        CandidateFetchResult(
            url="https://example.com/post_1",
            fetch_status=FetchStatus.SUCCESS,
            image_bytes=img_bytes,
            local_image_path=str(img_file),
        ),
        CandidateFetchResult(
            url="https://example.com/post_2",
            fetch_status=FetchStatus.SUCCESS,
            image_bytes=img_bytes,
            local_image_path=str(img_file),
        ),
    ])

    matcher.compare_candidate_image.return_value = (
        True,
        0.95,
        0.92,
        False,
        FaceMatchDetail(face_index=0, raw_similarity=0.95, calibrated_confidence=0.92),
    )
    matcher.detect_and_embed.return_value = [
        FaceDetection(embedding=[0.1] * 512)
    ]

    result = await pipeline.run(
        image_path="input.jpg",
        face_embedding=[0.1] * 512,
        claimed_urls=["https://example.com/post_1", "https://example.com/post_2"],
        consent=ConsentRecord(consent_confirmed=True),
    )

    data = result.to_dict()
    assert data["checked"]["urls_fetched"] == 2
    assert data["checked"]["cache_hits"] == 1


def test_synchronous_wrapper_api(tmp_path):
    """Verify synchronous verify_claimed_profile_sync wrapper works."""
    with pytest.raises(EmptyClaimedUrlsError):
        verify_claimed_profile_sync(
            face_embedding=[0.1] * 512,
            claimed_urls=[],
            consent={"consent_confirmed": True, "consent_scope": "self_verification"},
        )
