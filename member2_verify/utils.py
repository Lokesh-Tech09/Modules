"""
Utility functions for Module 2: Claimed-Profile Verification (Self-Match).
Includes URL validation, SSRF protection, image format validation, and similarity computation.
"""

import hashlib
import ipaddress
import os
from pathlib import Path
import socket
from typing import List, Optional, Tuple, Union
from urllib.parse import urlparse
import uuid

import numpy as np
from PIL import Image
import io

from .exceptions import SSRFSecurityError


def is_private_or_restricted_ip(ip_str: str) -> bool:
    """Check if an IP string is loopback, private, link-local, or otherwise reserved."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return True


def validate_candidate_url(url: str, enable_ssrf_protection: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Validate a candidate URL:
    - Must have http or https scheme.
    - Must have valid netloc.
    - If SSRF protection is enabled, resolved IPs must not be private/loopback/cloud metadata.
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported URL scheme: '{parsed.scheme}'. Only HTTP and HTTPS are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL missing valid hostname."

    if enable_ssrf_protection:
        # Check literal IP in hostname
        if is_private_or_restricted_ip(hostname):
            return False, f"SSRF Protection: Access to restricted/internal address '{hostname}' is blocked."

        # Block localhost aliases
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            return False, f"SSRF Protection: Access to localhost/internal address '{hostname}' is blocked."

        # Resolve hostname to check resulting IPs
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                resolved_ip = item[4][0]
                if is_private_or_restricted_ip(resolved_ip):
                    return False, f"SSRF Protection: Host '{hostname}' resolved to restricted IP '{resolved_ip}'."
        except socket.gaierror:
            return False, f"DNS resolution failed for host: '{hostname}'"
        except Exception as e:
            return False, f"Security check error during DNS resolution: {e}"

    return True, None


def validate_image_data(
    image_bytes: bytes, allowed_mimes: Tuple[str, ...]
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate image bytes using Pillow:
    - Verifies byte structure and image format.
    - Returns (is_valid, mime_type, error_message).
    """
    if not image_bytes or len(image_bytes) == 0:
        return False, None, "Empty image data."

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.verify()
            fmt = (img.format or "").upper()
            mime_map = {
                "JPEG": "image/jpeg",
                "PNG": "image/png",
                "WEBP": "image/webp",
                "BMP": "image/bmp",
            }
            mime_type = mime_map.get(fmt, f"image/{fmt.lower()}")

            if mime_type not in allowed_mimes:
                return False, mime_type, f"Unsupported image format '{fmt}' ({mime_type}). Allowed: {allowed_mimes}"

            return True, mime_type, None
    except Exception as e:
        return False, None, f"Invalid image file data: {e}"


def compute_cosine_similarity(
    vec1: Union[List[float], np.ndarray], vec2: Union[List[float], np.ndarray]
) -> float:
    """
    Compute cosine similarity between two embedding vectors.
    Returns normalized float in range [0.0, 1.0].
    """
    arr1 = np.asarray(vec1, dtype=np.float32).ravel()
    arr2 = np.asarray(vec2, dtype=np.float32).ravel()

    if arr1.size == 0 or arr2.size == 0 or arr1.shape != arr2.shape:
        return 0.0

    norm1 = np.linalg.norm(arr1)
    norm2 = np.linalg.norm(arr2)

    if norm1 == 0 or norm2 == 0 or np.isnan(norm1) or np.isnan(norm2):
        return 0.0

    dot = np.dot(arr1, arr2)
    cosine_sim = dot / (norm1 * norm2)

    # Convert [-1.0, 1.0] to [0.0, 1.0] or clamp [0.0, 1.0]
    # For face embeddings, typical cosine similarity >= 0
    clamped_sim = float(np.clip(cosine_sim, 0.0, 1.0))
    return round(clamped_sim, 4)


def save_temp_image(image_bytes: bytes, temp_dir: str, prefix: str = "candidate_") -> str:
    """Safely write image bytes to a temp file and return absolute path."""
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    ext = ".jpg"
    # Inspect first few bytes for simple extension detection
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:16]:
        ext = ".webp"

    filename = f"{prefix}{uuid.uuid4().hex[:8]}{ext}"
    target_path = os.path.join(temp_dir, filename)

    with open(target_path, "wb") as f:
        f.write(image_bytes)

    return target_path


def cleanup_file_safely(file_path: Optional[str]) -> None:
    """Safely delete a temporary file if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
