"""
Observability sub-system for Module 2: Claimed-Profile Verification (v2).
Provides:
- Structured JSON logging per pipeline stage with strict data redaction (no raw embeddings or bytes).
- In-memory metrics collector for operational reporting without external dependencies.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("member2_verify")


class JSONFormatter(logging.Formatter):
    """Formats log records as structured single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "stage"):
            log_entry["stage"] = record.stage
        if hasattr(record, "event_data"):
            log_entry["data"] = record.event_data

        return json.dumps(log_entry, default=str)


def sanitize_log_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure no raw image bytes, full face embeddings, or private tokens are logged.
    Converts embeddings to dimension counts and image bytes to lengths/hashes.
    """
    sanitized = {}
    for k, v in data.items():
        if k in ("face_embedding", "embedding", "target_embedding") and isinstance(v, (list, tuple)):
            sanitized[k] = f"<vector_dim_{len(v)}>"
        elif k in ("image_bytes", "content", "raw_bytes") and isinstance(v, bytes):
            h = hashlib.sha256(v).hexdigest()[:8]
            sanitized[k] = f"<bytes_len_{len(v)}_sha256_{h}>"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_log_data(v)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            sanitized[k] = [sanitize_log_data(item) for item in v]
        else:
            sanitized[k] = v
    return sanitized


class StructuredLogger:
    """Wrapper providing stage-aware structured JSON logging."""

    def __init__(self, name: str = "member2_verify.pipeline"):
        self.logger = logging.getLogger(name)

    def log_stage(self, stage: str, message: str, level: int = logging.INFO, **kwargs):
        """Log a pipeline stage event with sanitized context."""
        cleaned_data = sanitize_log_data(kwargs)
        self.logger.log(
            level,
            message,
            extra={"stage": stage, "event_data": cleaned_data},
        )


@dataclass
class PipelineMetrics:
    """Operational metrics tracked during verification runs."""

    urls_provided: int = 0
    urls_deduplicated: int = 0
    urls_fetched: int = 0
    urls_blocked: int = 0
    urls_failed: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    matches_found: int = 0
    retries_attempted: int = 0
    fetch_latencies_ms: List[float] = field(default_factory=list)
    matching_latencies_ms: List[float] = field(default_factory=list)
    total_duration_ms: float = 0.0

    def record_fetch(self, duration_ms: float, success: bool, blocked: bool = False):
        self.fetch_latencies_ms.append(round(duration_ms, 2))
        if blocked:
            self.urls_blocked += 1
        elif success:
            self.urls_fetched += 1
        else:
            self.urls_failed += 1

    def to_summary(self) -> Dict[str, Any]:
        """Produce clean metrics summary dict."""
        avg_fetch = (
            round(sum(self.fetch_latencies_ms) / len(self.fetch_latencies_ms), 2)
            if self.fetch_latencies_ms
            else 0.0
        )
        total_cache = self.cache_hits + self.cache_misses
        hit_rate = round(self.cache_hits / total_cache, 4) if total_cache > 0 else 0.0

        return {
            "urls_provided": self.urls_provided,
            "urls_deduplicated": self.urls_deduplicated,
            "urls_fetched": self.urls_fetched,
            "urls_blocked": self.urls_blocked,
            "urls_failed": self.urls_failed,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": hit_rate,
            "retries_attempted": self.retries_attempted,
            "matches_found": self.matches_found,
            "avg_fetch_latency_ms": avg_fetch,
            "total_duration_ms": round(self.total_duration_ms, 2),
        }
