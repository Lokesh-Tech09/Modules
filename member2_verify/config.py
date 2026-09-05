"""
Configuration settings for Module 2: Claimed-Profile Verification (v2).
Provides environment-variable overrides and runtime validation for all operational limits.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class VerificationConfig:
    """
    Validated configuration parameters for profile verification pipeline (v2).
    Can be instantiated directly or loaded from environment variables.
    """

    # Schema version
    SCHEMA_VERSION: str = "2.0"

    # Face matching & calibration
    SIMILARITY_THRESHOLD: float = float(os.getenv("VERIFY_SIMILARITY_THRESHOLD", "0.65"))
    CALIBRATION_STEEPNESS: float = float(os.getenv("VERIFY_CALIBRATION_STEEPNESS", "12.0"))
    CALIBRATION_MIDPOINT: float = float(os.getenv("VERIFY_CALIBRATION_MIDPOINT", "0.65"))
    LOW_CONFIDENCE_DETECTION_THRESHOLD: float = float(os.getenv("VERIFY_LOW_CONF_THRESHOLD", "0.70"))

    # Network fetch limits & concurrency
    REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("VERIFY_TIMEOUT_SECONDS", "10"))
    MAX_IMAGE_SIZE_BYTES: int = int(os.getenv("VERIFY_MAX_IMAGE_SIZE_BYTES", str(10 * 1024 * 1024)))
    MAX_REDIRECTS: int = int(os.getenv("VERIFY_MAX_REDIRECTS", "5"))
    MAX_CONCURRENT_FETCHES: int = int(os.getenv("VERIFY_MAX_CONCURRENT_FETCHES", "5"))

    # Resilience: Retries and Circuit Breaker
    MAX_RETRIES: int = int(os.getenv("VERIFY_MAX_RETRIES", "3"))
    RETRY_BACKOFF_FACTOR: float = float(os.getenv("VERIFY_RETRY_BACKOFF", "0.5"))
    CIRCUIT_BREAKER_THRESHOLD: int = int(os.getenv("VERIFY_CIRCUIT_BREAKER_THRESHOLD", "3"))
    CIRCUIT_BREAKER_RESET_TIMEOUT: int = int(os.getenv("VERIFY_CIRCUIT_BREAKER_RESET_TIMEOUT", "30"))

    # Caching
    CACHE_ENABLED: bool = os.getenv("VERIFY_CACHE_ENABLED", "true").lower() in ("true", "1", "yes")
    CACHE_TTL_SECONDS: int = int(os.getenv("VERIFY_CACHE_TTL_SECONDS", "3600"))
    CACHE_MAX_ENTRIES: int = int(os.getenv("VERIFY_CACHE_MAX_ENTRIES", "1000"))

    # Domain policy & security
    DOMAIN_ALLOWLIST: Optional[List[str]] = field(
        default_factory=lambda: (
            [d.strip() for d in os.getenv("VERIFY_DOMAIN_ALLOWLIST", "").split(",") if d.strip()]
            if os.getenv("VERIFY_DOMAIN_ALLOWLIST")
            else None
        )
    )
    DOMAIN_DENYLIST: Optional[List[str]] = field(
        default_factory=lambda: (
            [d.strip() for d in os.getenv("VERIFY_DOMAIN_DENYLIST", "").split(",") if d.strip()]
            if os.getenv("VERIFY_DOMAIN_DENYLIST")
            else None
        )
    )
    ENFORCE_HTTPS_ONLY: bool = os.getenv("VERIFY_ENFORCE_HTTPS", "false").lower() in ("true", "1", "yes")
    ENABLE_SSRF_PROTECTION: bool = os.getenv("VERIFY_ENABLE_SSRF_PROTECTION", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    RESPECT_ROBOTS_TXT: bool = os.getenv("VERIFY_RESPECT_ROBOTS_TXT", "true").lower() in (
        "true",
        "1",
        "yes",
    )

    # Observability
    ENABLE_STRUCTURED_LOGGING: bool = os.getenv("VERIFY_STRUCTURED_LOGGING", "true").lower() in (
        "true",
        "1",
        "yes",
    )

    # Allowed MIME types for images
    ALLOWED_IMAGE_MIME_TYPES: Tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
    )

    # HTTP User-Agent header
    USER_AGENT: str = os.getenv(
        "VERIFY_USER_AGENT",
        "Mozilla/5.0 (compatible; ClaimedProfileVerifier/2.0; +https://github.com/project/member2_verify; Consented Verification)",
    )

    # Storage & models
    TEMP_DIR: str = os.getenv("VERIFY_TEMP_DIR", os.path.join(os.path.dirname(__file__), "temp"))
    DEFAULT_EMBEDDING_DIM: int = int(os.getenv("VERIFY_EMBEDDING_DIM", "512"))

    def __post_init__(self):
        Path(self.TEMP_DIR).mkdir(parents=True, exist_ok=True)


default_config = VerificationConfig()
