"""
Cryptographic, canonicalization, and security utilities for Module 3.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Set


def get_utc_timestamp() -> str:
    """Return current UTC time in ISO 8601 format with 'Z' suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_obj(obj: Any, exclude_keys: Set[str]) -> Any:
    """
    Recursively normalize objects for canonical hashing:
    - Excludes non-hashable / ephemeral keys.
    - Normalizes floating-point values to 6 decimal places to prevent representation drift.
    - Sorts dictionary keys.
    """
    if isinstance(obj, dict):
        return {
            k: _normalize_obj(v, exclude_keys)
            for k, v in sorted(obj.items())
            if k not in exclude_keys
        }
    elif isinstance(obj, list):
        return [_normalize_obj(item, exclude_keys) for item in obj]
    elif isinstance(obj, float):
        # Prevent floating-point representation drift (e.g. 0.9710000000000001 -> 0.971)
        rounded = round(obj, 6)
        # Avoid -0.0
        return 0.0 if rounded == 0.0 else rounded
    return obj


def canonicalize_json(data: Any, exclude_keys: Set[str] | None = None) -> str:
    """
    Produce a canonical, deterministic JSON string representation:
    - Sorted dictionary keys.
    - Compact separators without whitespace (',', ':').
    - ASCII-encoded.
    - Normalized floats.
    - Excluded fields removed.
    """
    excludes = exclude_keys if exclude_keys is not None else set()
    normalized = _normalize_obj(data, excludes)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_sha256(content: str | bytes) -> str:
    """Compute standard SHA-256 hex digest of string or bytes."""
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content
    return hashlib.sha256(content_bytes).hexdigest()


def generate_reference_id(record_hash: str, network: str = "sepolia", nonce: int = 0) -> str:
    """
    Generate a deterministic or pseudo-random 0x-prefixed 64-char reference ID
    resembling a blockchain transaction hash.
    """
    seed = f"{network}:{record_hash}:{nonce}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    return f"0x{digest}"


def secure_file_permissions(file_path: Path | str) -> None:
    """
    Apply private access permissions (0600 on POSIX) to protect off-chain stores.
    Gracefully handles Windows environments.
    """
    try:
        path = Path(file_path)
        if path.exists() and os.name != "nt":
            path.chmod(0o600)
    except Exception:
        # Best effort on non-POSIX / restricted environments
        pass
