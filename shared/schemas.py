"""
Shared schemas and models across Module 1, Module 2, and Module 3.
Ensures strict contract agreement between the three team members.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MatchData(BaseModel):
    """Details of the matched profile/candidate URL from Module 2."""
    url: str
    image_url: Optional[str] = None
    local_image_path: Optional[str] = None
    caption: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VerificationScores(BaseModel):
    """Similarity and confidence scores computed during face verification."""
    raw_similarity: float
    calibrated_confidence: float
    low_confidence_detection: bool = False


class ConsentData(BaseModel):
    """Consent record indicating user-authorized verification."""
    consent_scope: str = "self_verification"
    consent_confirmed: bool = True
    consent_timestamp: Optional[str] = None


class VerificationResultPayload(BaseModel):
    """
    Standard handoff schema from Module 2 to Module 3.
    Schema Version: 2.0
    """
    schema_version: str = "2.0"
    status: str  # "verified" | "not_verified" | "search_failed" | "error"
    match: Optional[MatchData] = None
    verification: Optional[VerificationScores] = None
    consent: Optional[ConsentData] = None
    input: Optional[Dict[str, Any]] = None
    checked: Optional[Dict[str, Any]] = None
