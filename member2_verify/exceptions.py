"""
Domain exceptions for Module 2: Claimed-Profile Verification (Self-Match).
"""


class VerificationError(Exception):
    """Base exception for all verification module errors."""

    pass


class ConsentRequiredError(VerificationError):
    """
    Raised when verification is initiated without explicit user consent confirmation.
    Module 2 operates strictly on a 1-to-1 consented basis.
    """

    def __init__(
        self,
        message: str = (
            "Verification aborted: Explicit user consent confirmation is required. "
            "Claimed-profile verification can only be performed for URLs the user explicitly "
            "confirms they own or have rights to verify."
        ),
    ):
        super().__init__(message)


class EmptyClaimedUrlsError(VerificationError):
    """
    Raised when claimed_urls is empty or missing.
    Module 2 structurally refuses to operate in discovery or web-search mode.
    """

    def __init__(
        self,
        message: str = (
            "No candidate URLs provided: 'claimed_urls' must be a non-empty list of URLs. "
            "This module performs 1-to-1 consented verification and does not perform open-web discovery."
        ),
    ):
        super().__init__(message)


class InvalidInputError(VerificationError):
    """Raised when input image_path or face_embedding is invalid, unreadable, or missing."""

    pass


class SSRFSecurityError(VerificationError):
    """Raised when a candidate URL attempts to access private, loopback, or cloud-internal IPs."""

    pass


class CandidateFetchError(VerificationError):
    """Raised when fetching candidate content fails critically."""

    pass


class MetadataExtractionError(VerificationError):
    """Raised when parsing or extracting metadata fails critically."""

    pass


class FaceMatchingError(VerificationError):
    """Raised when face detection or embedding comparison fails critically."""

    pass
