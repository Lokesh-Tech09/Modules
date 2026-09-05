"""
Content-hash based cache layer for Module 2: Claimed-Profile Verification (v2).
Caches detected faces and precomputed embeddings using SHA-256 hash of image bytes.
Guarantees:
- Cache keys never contain raw queries or user identity strings.
- Eliminates redundant face detection/embedding when identical images are referenced.
- In-memory by default with TTL expiration and max entries limit.
"""

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import threading
import time
from typing import List, Optional

from .models import FaceDetection


@dataclass
class CachedFaceData:
    """Entry stored in the content-hash cache."""

    content_hash: str
    detected_faces: List[FaceDetection]
    timestamp: float


class ContentHashCache:
    """
    Thread-safe in-memory cache keyed solely by SHA-256 hash of image content bytes.
    """

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._cache: OrderedDict[str, CachedFaceData] = OrderedDict()
        self._lock = threading.Lock()
        self.hits: int = 0
        self.misses: int = 0

    @staticmethod
    def hash_bytes(image_bytes: bytes) -> str:
        """Compute SHA-256 hash string for raw image bytes."""
        return hashlib.sha256(image_bytes).hexdigest()

    def get(self, content_hash: str) -> Optional[List[FaceDetection]]:
        """
        Retrieve cached face detections for a content hash.
        Returns None on cache miss or expired TTL.
        """
        with self._lock:
            if content_hash not in self._cache:
                self.misses += 1
                return None

            entry = self._cache[content_hash]
            now = time.time()

            # Check TTL
            if now - entry.timestamp > self.ttl_seconds:
                del self._cache[content_hash]
                self.misses += 1
                return None

            # Move to end for LRU order
            self._cache.move_to_end(content_hash)
            self.hits += 1
            return [f.model_copy() for f in entry.detected_faces]

    def set(self, content_hash: str, detected_faces: List[FaceDetection]) -> None:
        """Store face detections for a content hash."""
        with self._lock:
            now = time.time()
            if content_hash in self._cache:
                self._cache.move_to_end(content_hash)
            self._cache[content_hash] = CachedFaceData(
                content_hash=content_hash,
                detected_faces=[f.model_copy() for f in detected_faces],
                timestamp=now,
            )

            # Evict oldest entries if capacity exceeded
            while len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    @property
    def hit_rate(self) -> float:
        """Return cache hit rate fraction."""
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total > 0 else 0.0
