"""
Interactive demonstration script for Module 2: Claimed-Profile Verification (v2 Enhanced).
Demonstrates:
1. Privacy & Consent verification with ConsentRecord (self_verification and authorized_third_party)
2. Structural anti-discovery enforcement (empty claimed_urls refusal)
3. Successful 1-to-1 Verification with calibrated scores (schema_version 2.0)
4. Content-hash based caching across duplicate images (cache hit)
5. Domain Circuit Breaker protection on failing hosts
6. Structured JSON logging with payload redaction
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from member2_verify import (
    ConsentRecord,
    ConsentRequiredError,
    ConsentScope,
    ContentHashCache,
    EmptyClaimedUrlsError,
    FaceMatchDetail,
    VerificationConfig,
    VerificationPipeline,
    verify_claimed_profile,
    verify_claimed_profile_sync,
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


async def run_v2_demo():
    print("=" * 75)
    print("MODULE 2 (v2) — CLAIMED-PROFILE VERIFICATION (SELF-MATCH) — DEMO")
    print("Task 3: Face Identification & Blockchain Verification — Enhanced Spec")
    print("=" * 75)

    # 1. Privacy & Consent Guardrails
    print("\n[Scenario 1] Privacy Check: Attempting verification with consent_confirmed=False...")
    try:
        await verify_claimed_profile(
            face_embedding=[0.1] * 512,
            claimed_urls=["https://example.com/profile"],
            consent=ConsentRecord(consent_confirmed=False),
        )
    except ConsentRequiredError as e:
        print(f"  --> Blocked as expected! Error: {e}")

    # 2. Structural Anti-Discovery Invariant
    print("\n[Scenario 2] Anti-Discovery: Attempting verification with empty claimed_urls...")
    try:
        await verify_claimed_profile(
            face_embedding=[0.1] * 512,
            claimed_urls=[],
            consent=ConsentRecord(consent_confirmed=True),
        )
    except EmptyClaimedUrlsError as e:
        print(f"  --> Blocked as expected! Error: {e}")

    # 3. Successful 1-to-1 Verification with Score Calibration (v2 Output Contract)
    print("\n[Scenario 3] Successful 1-to-1 Verification (v2 Output Contract)...")
    temp_dir = Path("member2_verify/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_img_path = str(temp_dir / "candidate_v2_demo.jpg")
    img_bytes = b"real_mock_image_bytes_for_demo_123"
    with open(temp_img_path, "wb") as f:
        f.write(img_bytes)

    mock_fetcher = MagicMock(spec=CandidateFetcher)
    mock_extractor = MagicMock(spec=PostExtractor)
    mock_extractor.extract.return_value = ExtractedPostMetadata(url="https://example.com/post")
    mock_matcher = MagicMock(spec=FaceMatcher)
    cache = ContentHashCache()

    mock_fetcher.fetch_all = AsyncMock(return_value=[
        CandidateFetchResult(
            url="https://instagram.com/p/my_consented_post",
            fetch_status=FetchStatus.SUCCESS,
            content_type="image/jpeg",
            image_bytes=img_bytes,
            local_image_path=temp_img_path,
            extracted_metadata=ExtractedPostMetadata(
                url="https://instagram.com/p/my_consented_post",
                image_url="https://cdn.instagram.com/v/photo_123.jpg",
                caption="Verified summit photo at Goa Hackathon #AI",
                metadata={"platform": "instagram"},
            ),
        )
    ])

    mock_matcher.compare_candidate_image.return_value = (
        True,
        0.971,  # Raw cosine similarity
        0.940,  # Calibrated confidence
        False,  # Low confidence detection flag
        FaceMatchDetail(
            face_index=0,
            raw_similarity=0.971,
            calibrated_confidence=0.940,
            low_confidence_detection=False,
            bounding_box=[60, 60, 140, 140],
        ),
    )
    mock_matcher.detect_and_embed.return_value = [
        FaceDetection(bounding_box=[60, 60, 140, 140], embedding=[0.5] * 512)
    ]

    pipeline = VerificationPipeline(
        config=VerificationConfig(SIMILARITY_THRESHOLD=0.65),
        fetcher=mock_fetcher,
        extractor=mock_extractor,
        matcher=mock_matcher,
        cache=cache,
    )

    consent = ConsentRecord(
        consent_confirmed=True,
        consent_scope=ConsentScope.SELF_VERIFICATION,
        consent_timestamp="2026-09-05T10:00:00Z",
    )

    result_v2 = await pipeline.run(
        image_path="input.jpg",
        face_embedding=[0.5] * 512,
        claimed_urls=["https://instagram.com/p/my_consented_post"],
        consent=consent,
    )

    print("Output Contract for Module 3 (Blockchain Upload) — Version 2.0:")
    print(json.dumps(result_v2.to_dict(), indent=2))

    # 4. Content-Hash Caching Across Duplicate Images
    print("\n[Scenario 4] Content-Hash Caching Demonstration...")
    # Fetching two different URLs that host the exact same image content
    mock_fetcher.fetch_all = AsyncMock(return_value=[
        CandidateFetchResult(
            url="https://example.com/post_mirror_1",
            fetch_status=FetchStatus.SUCCESS,
            image_bytes=img_bytes,
            local_image_path=temp_img_path,
        ),
        CandidateFetchResult(
            url="https://example.com/post_mirror_2",
            fetch_status=FetchStatus.SUCCESS,
            image_bytes=img_bytes,
            local_image_path=temp_img_path,
        ),
    ])

    result_cache = await pipeline.run(
        image_path="input.jpg",
        face_embedding=[0.5] * 512,
        claimed_urls=["https://example.com/post_mirror_1", "https://example.com/post_mirror_2"],
        consent=consent,
    )

    print(f"  --> URLs Fetched: {result_cache.checked.urls_fetched}")
    print(f"  --> Cache Hits:   {result_cache.checked.cache_hits} (Eliminated duplicate face detection)")

    # 5. Circuit Breaker Protection
    print("\n[Scenario 5] Domain Circuit Breaker Protection...")
    breaker = CandidateFetcher().circuit_breaker
    failing_domain = "unresponsive-cdn.net"
    print(f"  Simulating repeated failures on '{failing_domain}'...")
    for _ in range(3):
        breaker.record_failure(failing_domain)
    print(f"  --> Circuit breaker available: {breaker.is_available(failing_domain)} (Tripped to OPEN)")

    print("\n" + "=" * 75)
    print("MODULE 2 (v2) DEMO COMPLETED SUCCESSFULLY!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_v2_demo())
