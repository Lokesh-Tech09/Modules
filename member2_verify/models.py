"""
Data models for Module 2: Claimed-Profile Verification (v2 Enhanced Spec).
Supports schema version 2.0, ConsentRecord, calibrated confidence, uncertainty flags,
and operational checked statistics.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConsentScope(str, Enum):
    SELF_VERIFICATION = "self_verification"
    AUTHORIZED_THIRD_PARTY = "authorized_third_party"


class ConsentRecord(BaseModel):
    """
    Explicit consent record required for 1-to-1 profile verification.
    """

    consent_confirmed: bool = Field(..., description="Must be True to proceed.")
    consent_scope: ConsentScope = Field(
        default=ConsentScope.SELF_VERIFICATION,
        description="Must be 'self_verification' or 'authorized_third_party'.",
    )
    consent_timestamp: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp when consent was granted."
    )
    authorization_reference: Optional[str] = Field(
        default=None,
        description="Mandatory documentation ID/reference when scope is 'authorized_third_party'.",
    )

    @model_validator(mode="after")
    def validate_third_party_reference(self) -> "ConsentRecord":
        if self.consent_scope == ConsentScope.AUTHORIZED_THIRD_PARTY:
            ref = self.authorization_reference
            if not ref or not ref.strip():
                raise ValueError(
                    "Authorization reference is required when consent_scope is 'authorized_third_party'."
                )
        return self

    model_config = ConfigDict(extra="ignore")


class FetchStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"  # Access restriction, CAPTCHA, or paywall


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    REJECTED_INVALID_INPUT = "rejected_invalid_input"
    REJECTED_CONSENT = "rejected_consent"
    PARTIAL_FAILURE = "partial_failure"
    SEARCH_FAILED = "search_failed"


class ExtractedPostMetadata(BaseModel):
    """Metadata extracted from a candidate URL or post."""

    url: str
    image_url: Optional[str] = None
    caption: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    published_date: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CandidateFetchResult(BaseModel):
    """Result of attempting to fetch a candidate URL."""

    url: str
    fetch_status: FetchStatus
    content_type: Optional[str] = None
    image_bytes: Optional[bytes] = None
    local_image_path: Optional[str] = None
    html_content: Optional[str] = None
    extracted_metadata: Optional[ExtractedPostMetadata] = None
    error_message: Optional[str] = None
    retries_used: int = 0
    duration_ms: float = 0.0

    model_config = ConfigDict(arbitrary_types_allowed=True)


class FaceDetection(BaseModel):
    """A detected face with its bounding box, confidence, and embedding."""

    bounding_box: Optional[List[int]] = None  # [x, y, w, h]
    embedding: List[float]
    confidence: float = 1.0


class FaceMatchDetail(BaseModel):
    """Detailed score for a face comparison."""

    face_index: int
    raw_similarity: float
    calibrated_confidence: float
    low_confidence_detection: bool = False
    bounding_box: Optional[List[int]] = None


class CandidateMatchResult(BaseModel):
    """Consolidated verification match result for a single candidate URL."""

    url: str
    image_url: Optional[str] = None
    local_image_path: Optional[str] = None
    caption: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    raw_similarity: float = 0.0
    calibrated_confidence: float = 0.0
    low_confidence_detection: bool = False
    is_verified: bool = False
    best_face: Optional[FaceMatchDetail] = None


class InputSummary(BaseModel):
    """Echoed input information."""

    image_path: Optional[str] = None


class MatchDetails(BaseModel):
    """Contract shape for matched profile."""

    url: str
    image_url: Optional[str] = None
    local_image_path: Optional[str] = None
    caption: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VerificationScores(BaseModel):
    """Calibrated match scores and detection uncertainty indicators."""

    raw_similarity: float
    calibrated_confidence: float
    low_confidence_detection: bool = False


class CheckedSummary(BaseModel):
    """Summary counts of candidate URLs evaluated in v2."""

    urls_provided: int
    urls_deduplicated: int
    urls_fetched: int
    urls_blocked: int = 0
    urls_failed: int = 0
    cache_hits: int = 0


class ConsentSummary(BaseModel):
    """Consent summary included in Module 3 output contract."""

    consent_scope: str
    consent_confirmed: bool


class VerificationOutput(BaseModel):
    """
    Standard versioned output contract provided to Module 3 (Blockchain Upload).
    Matches Section 11 of the Module 2 v2 specification.
    """

    schema_version: str = "2.0"
    status: str  # verified, not_verified, etc.
    input: InputSummary
    match: Optional[MatchDetails] = None
    verification: Optional[VerificationScores] = None
    checked: CheckedSummary
    consent: Optional[ConsentSummary] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return clean dictionary matching the exact JSON contract shape."""
        return self.model_dump()
