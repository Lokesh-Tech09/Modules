"""
Tests for ContentHashCache.
Module 2: Claimed-Profile Verification (v2).
"""

import time
import pytest

from member2_verify.cache import ContentHashCache
from member2_verify.models import FaceDetection


def test_hash_bytes_deterministic():
    """Verify SHA-256 hash calculation is deterministic."""
    data1 = b"fake_jpeg_bytes_12345"
    data2 = b"fake_jpeg_bytes_12345"
    data3 = b"different_bytes"

    h1 = ContentHashCache.hash_bytes(data1)
    h2 = ContentHashCache.hash_bytes(data2)
    h3 = ContentHashCache.hash_bytes(data3)

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_cache_set_and_get():
    """Verify caching face detections and retrieving them."""
    cache = ContentHashCache(ttl_seconds=60, max_entries=10)
    img_hash = "abc123hash"
    detections = [
        FaceDetection(bounding_box=[10, 10, 50, 50], embedding=[0.5] * 512, confidence=0.95)
    ]

    cache.set(img_hash, detections)
    cached = cache.get(img_hash)

    assert cached is not None
    assert len(cached) == 1
    assert cached[0].confidence == 0.95
    assert cached[0].embedding == [0.5] * 512
    assert cache.hits == 1
    assert cache.misses == 0
    assert cache.hit_rate == 1.0


def test_cache_miss():
    """Verify cache miss behavior."""
    cache = ContentHashCache(ttl_seconds=60)
    result = cache.get("nonexistent_hash")

    assert result is None
    assert cache.misses == 1
    assert cache.hits == 0
    assert cache.hit_rate == 0.0


def test_cache_ttl_expiration():
    """Verify entries expire after TTL."""
    cache = ContentHashCache(ttl_seconds=0.1)  # 100ms TTL
    img_hash = "expire_me"
    detections = [FaceDetection(embedding=[0.1] * 512)]

    cache.set(img_hash, detections)
    assert cache.get(img_hash) is not None

    time.sleep(0.15)  # Wait for TTL to expire
    assert cache.get(img_hash) is None


def test_cache_max_entries_eviction():
    """Verify LRU capacity eviction when max_entries is exceeded."""
    cache = ContentHashCache(ttl_seconds=60, max_entries=2)

    cache.set("hash1", [FaceDetection(embedding=[1.0])])
    cache.set("hash2", [FaceDetection(embedding=[2.0])])
    cache.set("hash3", [FaceDetection(embedding=[3.0])])  # Should evict hash1

    assert cache.get("hash1") is None
    assert cache.get("hash2") is not None
    assert cache.get("hash3") is not None
