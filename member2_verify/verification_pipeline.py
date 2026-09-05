"""
Verification pipeline for Module 2: Claimed-Profile Verification (v2 Enhanced).
Orchestrates the 14-step verification lifecycle:
- Validates schema version, input image/embedding, and explicit ConsentRecord.
- Sanitizes and deduplicates candidate URLs.
- Concurrently fetches candidate URLs using async bounded concurrency and circuit breaker.
- Leverages ContentHashCache to avoid reprocessing duplicate images.
- Calibrates cosine similarity to confidence scores and flags detection uncertainties.
- Formats structured v2.0 output contract for handoff to Module 3.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Union

from .cache import ContentHashCache
from .candidate_fetcher import CandidateFetcher
from .config import VerificationConfig, default_config
from .exceptions import (
    ConsentRequiredError,
    EmptyClaimedUrlsError,
    InvalidInputError,
    VerificationError,
)
from .face_matcher import FaceMatcher
from .models import (
    CandidateFetchResult,
    CandidateMatchResult,
    CheckedSummary,
    ConsentRecord,
    ConsentScope,
    ConsentSummary,
    ExtractedPostMetadata,
    FaceDetection,
    FetchStatus,
    InputSummary,
    MatchDetails,
    VerificationOutput,
    VerificationScores,
    VerificationStatus,
)
from .observability import PipelineMetrics, StructuredLogger
from .post_extractor import PostExtractor
from .security import URLSanitizer
from .utils import cleanup_file_safely

logger = logging.getLogger(__name__)


class VerificationPipeline:
    """
    14-Step Enhanced Profile Verification Pipeline (v2).
    """

    def __init__(
        self,
        config: Optional[VerificationConfig] = None,
        fetcher: Optional[CandidateFetcher] = None,
        extractor: Optional[PostExtractor] = None,
        matcher: Optional[FaceMatcher] = None,
        cache: Optional[ContentHashCache] = None,
    ):
        self.config = config or default_config
        self.fetcher = fetcher or CandidateFetcher(self.config)
        self.extractor = extractor or PostExtractor()
        self.matcher = matcher or FaceMatcher(self.config)
        self.cache = cache or (ContentHashCache(
            ttl_seconds=self.config.CACHE_TTL_SECONDS,
            max_entries=self.config.CACHE_MAX_ENTRIES,
        ) if self.config.CACHE_ENABLED else None)
        self.structured_logger = StructuredLogger()

    async def run(
        self,
        image_path: Optional[str] = None,
        face_embedding: Optional[List[float]] = None,
        claimed_urls: Optional[List[str]] = None,
        consent: Optional[Union[ConsentRecord, Dict[str, Any]]] = None,
        schema_version: str = "2.0",
    ) -> VerificationOutput:
        """
        Execute the 14-step async verification lifecycle.
        """
        start_time = time.time()
        metrics = PipelineMetrics()

        # =====================================================================
        # STEP 1: Validate schema_version, input image, and embedding
        # =====================================================================
        if face_embedding is None and not image_path:
            raise InvalidInputError("Either 'face_embedding' or a valid 'image_path' must be provided.")

        resolved_embedding = face_embedding
        if resolved_embedding is None and image_path:
            if not os.path.exists(image_path):
                raise InvalidInputError(f"Input image path does not exist: {image_path}")
            extracted = self.matcher.extract_embedding_from_image(image_path)
            if not extracted:
                raise InvalidInputError(f"No face detected in input image: {image_path}")
            resolved_embedding = extracted

        if not resolved_embedding or len(resolved_embedding) == 0:
            raise InvalidInputError("Resolved face embedding vector is empty or invalid.")

        self.structured_logger.log_stage(
            stage="input_validation",
            message="Input face embedding resolved successfully",
            embedding_dim=len(resolved_embedding),
            image_path=image_path,
        )

        # =====================================================================
        # STEP 2: Validate consent record (must be confirmed + in-scope)
        # =====================================================================
        parsed_consent: ConsentRecord
        if isinstance(consent, ConsentRecord):
            parsed_consent = consent
        elif isinstance(consent, dict):
            try:
                parsed_consent = ConsentRecord(**consent)
            except Exception as e:
                raise ConsentRequiredError(f"Invalid consent payload: {e}")
        elif consent is True:  # Backward compatibility
            parsed_consent = ConsentRecord(
                consent_confirmed=True,
                consent_scope=ConsentScope.SELF_VERIFICATION,
            )
        else:
            raise ConsentRequiredError(
                "Consent verification failed: Explicit ConsentRecord is required."
            )

        if not parsed_consent.consent_confirmed:
            raise ConsentRequiredError(
                "Consent verification failed: 'consent_confirmed' must be True."
            )

        if parsed_consent.consent_scope not in (
            ConsentScope.SELF_VERIFICATION,
            ConsentScope.AUTHORIZED_THIRD_PARTY,
        ):
            raise ConsentRequiredError(
                f"Unsupported consent scope: '{parsed_consent.consent_scope}'."
            )

        # =====================================================================
        # STEP 3 & 4: Validate, sanitize, and deduplicate claimed_urls
        # =====================================================================
        if not claimed_urls or len(claimed_urls) == 0:
            raise EmptyClaimedUrlsError(
                "No candidate URLs provided: 'claimed_urls' cannot be empty. "
                "This module structurally refuses to perform open-ended discovery."
            )

        metrics.urls_provided = len(claimed_urls)

        # Sanitize and deduplicate
        seen_urls = set()
        deduped_urls: List[str] = []
        for raw_url in claimed_urls:
            valid, clean_url, _ = URLSanitizer.sanitize(
                raw_url, enforce_https=self.config.ENFORCE_HTTPS_ONLY
            )
            target = clean_url if valid and clean_url else raw_url.strip()
            if target and target not in seen_urls:
                seen_urls.add(target)
                deduped_urls.append(target)

        if not deduped_urls:
            raise EmptyClaimedUrlsError("All candidate URLs were empty or invalid.")

        metrics.urls_deduplicated = len(deduped_urls)

        # =====================================================================
        # STEP 5: Fetch candidate URLs concurrently (bounded by semaphore)
        # =====================================================================
        self.structured_logger.log_stage(
            stage="fetch_started",
            message=f"Beginning concurrent fetch for {len(deduped_urls)} candidate URLs",
            url_count=len(deduped_urls),
        )

        fetch_results: List[CandidateFetchResult] = await self.fetcher.fetch_all(
            deduped_urls, post_extractor=self.extractor
        )

        candidate_matches: List[CandidateMatchResult] = []
        temp_files_to_cleanup: List[str] = []

        # =====================================================================
        # STEPS 6-11: Cache check, face detection, embeddings, comparison & calibration
        # =====================================================================
        for fetch_res in fetch_results:
            metrics.record_fetch(
                duration_ms=fetch_res.duration_ms,
                success=(fetch_res.fetch_status == FetchStatus.SUCCESS),
                blocked=(fetch_res.fetch_status == FetchStatus.BLOCKED),
            )
            metrics.retries_attempted += fetch_res.retries_used

            if fetch_res.fetch_status != FetchStatus.SUCCESS:
                self.structured_logger.log_stage(
                    stage="fetch_unsuccessful",
                    message=f"Candidate URL unavailable: {fetch_res.url}",
                    status=fetch_res.fetch_status.value,
                    error=fetch_res.error_message,
                )
                continue

            if fetch_res.local_image_path:
                temp_files_to_cleanup.append(fetch_res.local_image_path)

            # Metadata resolution
            post_meta: ExtractedPostMetadata
            if fetch_res.extracted_metadata:
                post_meta = fetch_res.extracted_metadata
            elif fetch_res.html_content is not None:
                post_meta = self.extractor.extract(fetch_res.html_content, base_url=fetch_res.url)
            else:
                fallback_meta = self.extractor.extract("", base_url=fetch_res.url)
                if fallback_meta and fallback_meta.image_url:
                    post_meta = fallback_meta
                else:
                    post_meta = ExtractedPostMetadata(
                        url=fetch_res.url,
                        image_url=fetch_res.url,
                    )

            if not fetch_res.local_image_path or not os.path.exists(fetch_res.local_image_path):
                continue

            # STEP 6: Check cache by image content hash before face detection
            cached_detections: Optional[List[FaceDetection]] = None
            content_hash = None
            if self.cache and fetch_res.image_bytes:
                content_hash = self.cache.hash_bytes(fetch_res.image_bytes)
                cached_detections = self.cache.get(content_hash)
                if cached_detections is not None:
                    metrics.cache_hits += 1
                    self.structured_logger.log_stage(
                        stage="cache_hit",
                        message="Reusing cached face detections for image",
                        content_hash=content_hash[:12],
                    )
                else:
                    metrics.cache_misses += 1

            # STEPS 8, 9, 10, 11: Detect, embed, compare, calibrate, uncertainty flag
            match_start = time.time()
            (
                is_match,
                raw_sim,
                calibrated_conf,
                low_conf,
                best_face,
            ) = self.matcher.compare_candidate_image(
                candidate_image_path=fetch_res.local_image_path,
                target_embedding=resolved_embedding,
                precomputed_detections=cached_detections,
            )
            metrics.matching_latencies_ms.append(round((time.time() - match_start) * 1000, 2))

            # Populate cache on miss
            if self.cache and content_hash and cached_detections is None:
                # Cache fresh detections
                fresh_detections = self.matcher.detect_and_embed(fetch_res.local_image_path)
                self.cache.set(content_hash, fresh_detections)

            self.structured_logger.log_stage(
                stage="face_matched",
                message=f"Evaluation complete for {fetch_res.url}",
                url=fetch_res.url,
                raw_similarity=raw_sim,
                calibrated_confidence=calibrated_conf,
                is_match=is_match,
                low_confidence_detection=low_conf,
            )

            candidate_matches.append(
                CandidateMatchResult(
                    url=fetch_res.url,
                    image_url=post_meta.image_url or fetch_res.url,
                    local_image_path=fetch_res.local_image_path,
                    caption=post_meta.caption,
                    metadata=post_meta.metadata,
                    raw_similarity=raw_sim,
                    calibrated_confidence=calibrated_conf,
                    low_confidence_detection=low_conf,
                    is_verified=is_match,
                    best_face=best_face,
                )
            )

        # =====================================================================
        # STEP 12: Aggregate best match across the finite URL set
        # =====================================================================
        verified_candidates = [m for m in candidate_matches if m.is_verified]
        best_match: Optional[CandidateMatchResult] = None
        if verified_candidates:
            # Sort by raw similarity descending
            verified_candidates.sort(key=lambda x: x.raw_similarity, reverse=True)
            best_match = verified_candidates[0]
            metrics.matches_found = len(verified_candidates)

        # Clean non-matched local temp files
        if best_match and best_match.local_image_path in temp_files_to_cleanup:
            temp_files_to_cleanup.remove(best_match.local_image_path)

        for temp_file in temp_files_to_cleanup:
            cleanup_file_safely(temp_file)

        # Determine overall status value
        metrics.total_duration_ms = (time.time() - start_time) * 1000
        status_value: str
        if best_match and best_match.is_verified:
            status_value = VerificationStatus.VERIFIED.value
        elif metrics.urls_fetched == 0:
            status_value = VerificationStatus.SEARCH_FAILED.value
        elif metrics.urls_failed > 0 or metrics.urls_blocked > 0:
            status_value = (
                VerificationStatus.PARTIAL_FAILURE.value
                if candidate_matches
                else VerificationStatus.SEARCH_FAILED.value
            )
        else:
            status_value = VerificationStatus.NOT_VERIFIED.value

        # Build output models
        input_summary = InputSummary(image_path=image_path)
        checked_summary = CheckedSummary(
            urls_provided=metrics.urls_provided,
            urls_deduplicated=metrics.urls_deduplicated,
            urls_fetched=metrics.urls_fetched,
            urls_blocked=metrics.urls_blocked,
            urls_failed=metrics.urls_failed,
            cache_hits=metrics.cache_hits,
        )
        consent_summary = ConsentSummary(
            consent_scope=parsed_consent.consent_scope.value,
            consent_confirmed=parsed_consent.consent_confirmed,
        )

        match_details: Optional[MatchDetails] = None
        verification_scores: Optional[VerificationScores] = None

        if best_match and best_match.is_verified:
            match_details = MatchDetails(
                url=best_match.url,
                image_url=best_match.image_url,
                local_image_path=best_match.local_image_path,
                caption=best_match.caption,
                metadata=best_match.metadata,
            )
            verification_scores = VerificationScores(
                raw_similarity=best_match.raw_similarity,
                calibrated_confidence=best_match.calibrated_confidence,
                low_confidence_detection=best_match.low_confidence_detection,
            )

        # =====================================================================
        # STEP 13 & 14: Log structured trace and return versioned result
        # =====================================================================
        self.structured_logger.log_stage(
            stage="pipeline_finished",
            message=f"Verification completed with status '{status_value}'",
            status=status_value,
            total_duration_ms=round(metrics.total_duration_ms, 2),
            urls_provided=metrics.urls_provided,
            urls_fetched=metrics.urls_fetched,
            matches_found=metrics.matches_found,
        )

        return VerificationOutput(
            schema_version="2.0",
            status=status_value,
            input=input_summary,
            match=match_details,
            verification=verification_scores,
            checked=checked_summary,
            consent=consent_summary,
        )

    def run_sync(
        self,
        image_path: Optional[str] = None,
        face_embedding: Optional[List[float]] = None,
        claimed_urls: Optional[List[str]] = None,
        consent: Optional[Union[ConsentRecord, Dict[str, Any]]] = None,
        schema_version: str = "2.0",
    ) -> VerificationOutput:
        """Synchronous wrapper for run()."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If already in an active event loop (e.g. Jupyter or nested loop)
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(
                self.run(
                    image_path=image_path,
                    face_embedding=face_embedding,
                    claimed_urls=claimed_urls,
                    consent=consent,
                    schema_version=schema_version,
                )
            )
        else:
            return loop.run_until_complete(
                self.run(
                    image_path=image_path,
                    face_embedding=face_embedding,
                    claimed_urls=claimed_urls,
                    consent=consent,
                    schema_version=schema_version,
                )
            )


async def verify_claimed_profile(
    image_path: Optional[str] = None,
    face_embedding: Optional[List[float]] = None,
    claimed_urls: Optional[List[str]] = None,
    consent: Optional[Union[ConsentRecord, Dict[str, Any], bool]] = None,
    *,
    config: Optional[VerificationConfig] = None,
) -> Dict[str, Any]:
    """
    Asynchronous top-level interface conforming to Module 2 (v2) specification.
    """
    pipeline = VerificationPipeline(config=config)
    output = await pipeline.run(
        image_path=image_path,
        face_embedding=face_embedding,
        claimed_urls=claimed_urls,
        consent=consent,
    )
    return output.to_dict()


def verify_claimed_profile_sync(
    image_path: Optional[str] = None,
    face_embedding: Optional[List[float]] = None,
    claimed_urls: Optional[List[str]] = None,
    consent: Optional[Union[ConsentRecord, Dict[str, Any], bool]] = None,
    *,
    config: Optional[VerificationConfig] = None,
) -> Dict[str, Any]:
    """
    Synchronous top-level interface for Module 2 (v2).
    """
    pipeline = VerificationPipeline(config=config)
    output = pipeline.run_sync(
        image_path=image_path,
        face_embedding=face_embedding,
        claimed_urls=claimed_urls,
        consent=consent,
    )
    return output.to_dict()
