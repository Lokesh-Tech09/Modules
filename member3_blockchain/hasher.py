"""
Canonicalization and cryptographic hashing for Module 2 verification records.
"""

from typing import Any, Dict, Set
from member3_blockchain.exceptions import CanonicalizationError
from member3_blockchain.models import CanonicalHashResult
from member3_blockchain.utils import canonicalize_json, compute_sha256, get_utc_timestamp

# Ephemeral, local, or heavy binary fields excluded from deterministic hash
DEFAULT_EXCLUDED_FIELDS: Set[str] = {
    "local_image_path",
    "image_bytes",
    "face_embedding",
    "embedding",
    "raw_image",
}


def canonicalize_verification_record(
    verification_result: Dict[str, Any],
    exclude_fields: Set[str] | None = None,
) -> str:
    """
    Produce a deterministic, canonical JSON representation of the verification record:
    - Excludes ephemeral local paths (e.g. local_image_path) and heavy embeddings.
    - Normalizes floating-point precision (similarity and confidence scores).
    - Sorts all keys deterministically.
    - Uses compact ASCII separators.

    Raises:
        CanonicalizationError: If the input cannot be parsed or canonicalized.
    """
    if not isinstance(verification_result, dict):
        raise CanonicalizationError(
            f"Expected verification_result to be a dict, got {type(verification_result).__name__}"
        )

    excludes = set(DEFAULT_EXCLUDED_FIELDS)
    if exclude_fields:
        excludes.update(exclude_fields)

    try:
        return canonicalize_json(verification_result, exclude_keys=excludes)
    except Exception as e:
        raise CanonicalizationError(f"Failed to canonicalize verification record: {e}") from e


def hash_verification_record(
    verification_result: Dict[str, Any],
    exclude_fields: Set[str] | None = None,
) -> CanonicalHashResult:
    """
    Compute a SHA-256 cryptographic fingerprint over the canonical verification record.

    Returns:
        CanonicalHashResult containing the 64-char SHA-256 hash, the exact canonical string,
        algorithm used, and timestamp.

    Raises:
        CanonicalizationError: If canonicalization fails.
    """
    canonical_str = canonicalize_verification_record(verification_result, exclude_fields=exclude_fields)
    record_hash = compute_sha256(canonical_str)
    timestamp = get_utc_timestamp()

    return CanonicalHashResult(
        record_hash=record_hash,
        canonical_json=canonical_str,
        algorithm="sha256",
        timestamp=timestamp,
    )
