"""
Tests for observability (JSONFormatter, log data redaction, PipelineMetrics).
Module 2: Claimed-Profile Verification (v2).
"""

import json
import logging

from member2_verify.observability import (
    JSONFormatter,
    PipelineMetrics,
    sanitize_log_data,
)


def test_sanitize_log_data_redacts_embeddings_and_bytes():
    """Verify raw embeddings and image bytes are never leaked in logs."""
    raw_payload = {
        "user_id": "alice",
        "face_embedding": [0.123] * 512,
        "image_bytes": b"super_secret_image_bytes_here",
        "nested": {
            "target_embedding": [0.9] * 512,
            "other_info": "safe_text",
        },
    }

    sanitized = sanitize_log_data(raw_payload)

    assert sanitized["user_id"] == "alice"
    assert sanitized["face_embedding"] == "<vector_dim_512>"
    assert "<bytes_len_" in sanitized["image_bytes"]
    assert sanitized["nested"]["target_embedding"] == "<vector_dim_512>"
    assert sanitized["nested"]["other_info"] == "safe_text"

    # Verify no floats from embedding exist in output
    dumped = json.dumps(sanitized)
    assert "0.123" not in dumped


def test_json_formatter_valid_json():
    """Verify JSONFormatter creates parseable JSON with stage and data."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Candidate URL fetched",
        args=(),
        exc_info=None,
    )
    record.stage = "fetch_result"
    record.event_data = {"url": "https://example.com/p/1", "status": "success"}

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Candidate URL fetched"
    assert parsed["stage"] == "fetch_result"
    assert parsed["data"]["url"] == "https://example.com/p/1"
    assert "timestamp" in parsed


def test_pipeline_metrics_summary():
    """Verify PipelineMetrics records latencies, counters, and averages."""
    metrics = PipelineMetrics()
    metrics.urls_provided = 3
    metrics.urls_deduplicated = 3
    metrics.record_fetch(duration_ms=100.0, success=True)
    metrics.record_fetch(duration_ms=200.0, success=True)
    metrics.record_fetch(duration_ms=50.0, success=False, blocked=True)

    metrics.cache_hits = 2
    metrics.cache_misses = 2
    metrics.matches_found = 1
    metrics.total_duration_ms = 450.0

    summary = metrics.to_summary()

    assert summary["urls_provided"] == 3
    assert summary["urls_fetched"] == 2
    assert summary["urls_blocked"] == 1
    assert summary["urls_failed"] == 0
    assert summary["cache_hit_rate"] == 0.5
    assert summary["avg_fetch_latency_ms"] == 116.67  # (100+200+50)/3
    assert summary["matches_found"] == 1
    assert summary["total_duration_ms"] == 450.0
