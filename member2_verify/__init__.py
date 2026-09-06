"""
Module 2: Claimed-Profile Verification (Self-Match) — v2 Enhanced
Part of Face Identification & Blockchain Verification Pipeline.

Production-ready, async-first, resilient 1-to-1 profile verification
with strict anti-discovery safeguards, content-hash caching, score calibration,
SSRF defense, and structured observability.
"""

from .cache import ContentHashCache
from .candidate_fetcher import CandidateFetcher, DomainCircuitBreaker, RobotsTxtCache
from .config import VerificationConfig, default_config
from .exceptions import (
    CandidateFetchError,
    ConsentRequiredError,
    EmptyClaimedUrlsError,
    FaceMatchingError,
    InvalidInputError,
    MetadataExtractionError,
    SSRFSecurityError,
    VerificationError,
)
from .face_matcher import (
    BaseFaceEngine,
    FaceMatcher,
    OpenCVFaceEngine,
    calibrate_similarity_score,
)
from .models import (
    CandidateFetchResult,
    CandidateMatchResult,
    CheckedSummary,
    ConsentRecord,
    ConsentScope,
    ConsentSummary,
    ExtractedPostMetadata,
    FaceDetection,
    FaceMatchDetail,
    FetchStatus,
    InputSummary,
    MatchDetails,
    VerificationOutput,
    VerificationScores,
    VerificationStatus,
)
from .observability import PipelineMetrics, StructuredLogger
from .post_extractor import PostExtractor
from .scrapers import SocialPost, SocialScraper, extract_social_posts
from .security import DomainPolicy, SSRFGuard, SecretScanner, URLSanitizer
from .verification_pipeline import (
    VerificationPipeline,
    verify_claimed_profile,
    verify_claimed_profile_sync,
)

__all__ = [
    # Top-level interfaces
    "verify_claimed_profile",
    "verify_claimed_profile_sync",
    "VerificationPipeline",
    "VerificationConfig",
    "default_config",
    # Core components
    "CandidateFetcher",
    "PostExtractor",
    "FaceMatcher",
    "SocialScraper",
    "SocialPost",
    "extract_social_posts",
    "BaseFaceEngine",
    "OpenCVFaceEngine",
    "ContentHashCache",
    # Security & Observability
    "SSRFGuard",
    "DomainPolicy",
    "URLSanitizer",
    "SecretScanner",
    "StructuredLogger",
    "PipelineMetrics",
    "DomainCircuitBreaker",
    "RobotsTxtCache",
    "calibrate_similarity_score",
    # Models
    "ConsentRecord",
    "ConsentScope",
    "ConsentSummary",
    "CandidateFetchResult",
    "CandidateMatchResult",
    "CheckedSummary",
    "ExtractedPostMetadata",
    "FaceDetection",
    "FaceMatchDetail",
    "FetchStatus",
    "VerificationStatus",
    "InputSummary",
    "MatchDetails",
    "VerificationOutput",
    "VerificationScores",
    # Exceptions
    "VerificationError",
    "ConsentRequiredError",
    "EmptyClaimedUrlsError",
    "InvalidInputError",
    "SSRFSecurityError",
    "CandidateFetchError",
    "MetadataExtractionError",
    "FaceMatchingError",
]
