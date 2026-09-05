# Module 2 (v2) — Claimed-Profile Verification (Self-Match) — Enhanced Spec

> **Task 3: Face Identification & Blockchain Verification Pipeline**
> 
> *Consented 1-to-1 Profile Verification: Verifies whether a scanned face matches images present at explicitly provided public URLs.*
> 
> **Schema Version:** `2.0`

---

## 1. Overview & Architectural Role

The overall project pipeline connects 3 collaborating modules:

```
[Module 1] Face Scan & Embedding
       │ (image_path, face_embedding, claimed_urls, ConsentRecord)
       ▼
[Module 2] Claimed-Profile Verification (v2 — THIS MODULE)
       │ (schema_version: "2.0", status, match, raw_similarity, calibrated_confidence, stats, consent)
       ▼
[Module 3] Blockchain Upload, Hashing & Re-Verification
```

### Key Differences from Open-Web Identity Search
Module 2 **never searches, crawls, or discovers people on the internet**. It performs **1-to-1 consented verification**:
- The user provides their own face and explicitly says *"This is my own post at this exact URL; confirm it is me"*.
- The module fetches only those specific URLs.
- It detects and embeds faces in those images and checks against the user's scan.
- No discovery mode or reverse-image indexing exists.

---

## 2. Enhancements in Version 2.0

| Feature | v1 | v2 (Enhanced) |
|---|---|---|
| **Execution** | Synchronous, sequential | Asynchronous concurrent fetch with bounded `asyncio.Semaphore` |
| **Resilience** | Basic try/except | Exponential backoff retries + per-domain Circuit Breakers |
| **Caching** | None | SHA-256 byte-level content-hash cache for face detections & embeddings |
| **Score Calibration** | Raw cosine similarity | Monotonic logistic calibration mapping raw similarity to probability confidence |
| **Uncertainty Flag** | None | `low_confidence_detection: bool` flag for low-quality / small faces |
| **Security** | Basic checks | Multi-layer SSRF Guard (IPv4/IPv6 private/metadata CIDRs), Domain Policy, Secret Scanner |
| **Observability** | Standard logs | Structured JSON logging with payload redaction + in-memory MetricsCollector |
| **Consent Model** | Single boolean | Structured `ConsentRecord` with scope (`self_verification`, `authorized_third_party`) & timestamp |
| **Schema Versioning** | None | Semantic `schema_version: "2.0"` output contracts |

---

## 3. Package Architecture

```
member2_verify/
│
├── __init__.py               # Package exports (async & sync APIs)
├── candidate_fetcher.py      # Async fetcher, retries, bounded concurrency, robots.txt, circuit breaker
├── post_extractor.py         # OpenGraph, Twitter Cards, JSON-LD Schema.org, HTML meta fallback chain
├── face_matcher.py           # Face detection, 512-d feature embeddings, score calibration, uncertainty flags
├── verification_pipeline.py  # 14-step async pipeline orchestration, v2 contract serialization
├── cache.py                  # In-memory TTL cache keyed solely by SHA-256(image_bytes)
├── security.py               # SSRFGuard, DomainPolicy (allow/denylist), URLSanitizer, SecretScanner
├── observability.py          # Structured JSON logger, data redaction, PipelineMetrics collector
├── models.py                 # Pydantic v2 schemas: ConsentRecord, VerificationOutput, CheckedSummary
├── config.py                 # Validated configuration with environment-variable overrides
├── utils.py                  # Cosine similarity, image validation, temp file managers
├── exceptions.py             # Custom domain exception hierarchy
├── requirements.txt          # Production dependencies
└── README.md                 # Complete system documentation
```

---

## 4. Input & Output Contracts (v2)

### Input Contract:
```python
from member2_verify import ConsentRecord, ConsentScope, verify_claimed_profile

result = await verify_claimed_profile(
    image_path="input.jpg",
    face_embedding=[0.123, ...],  # 512-d vector from Module 1
    claimed_urls=[
        "https://instagram.com/p/xyz",
        "https://twitter.com/handle/status/123"
    ],
    consent=ConsentRecord(
        consent_confirmed=True,
        consent_scope=ConsentScope.SELF_VERIFICATION,
        consent_timestamp="2026-09-05T10:00:00Z"
    )
)
```

### Output Contract (Module 3 Handoff):
```json
{
  "schema_version": "2.0",
  "status": "verified",
  "input": {
    "image_path": "input.jpg"
  },
  "match": {
    "url": "https://instagram.com/p/my_consented_post",
    "image_url": "https://cdn.instagram.com/v/photo_123.jpg",
    "local_image_path": "member2_verify/temp/candidate_v2_demo.jpg",
    "caption": "Verified selfie photo at the conference #AI",
    "metadata": {
      "platform": "instagram"
    }
  },
  "verification": {
    "raw_similarity": 0.971,
    "calibrated_confidence": 0.94,
    "low_confidence_detection": false
  },
  "checked": {
    "urls_provided": 2,
    "urls_deduplicated": 2,
    "urls_fetched": 2,
    "urls_blocked": 0,
    "urls_failed": 0,
    "cache_hits": 1
  },
  "consent": {
    "consent_scope": "self_verification",
    "consent_confirmed": true
  }
}
```

### Status Values:
- `verified`: At least one URL was successfully matched above the threshold.
- `not_verified`: URLs fetched, but no face matched above threshold.
- `rejected_invalid_input`: Input image/embedding missing or invalid.
- `rejected_consent`: Consent missing, unconfirmed (`consent_confirmed: false`), or out-of-scope.
- `partial_failure`: Some URLs failed or were blocked, but others were evaluated.
- `search_failed`: Systemic fetch failure across all candidate URLs (0 URLs fetched).

---

## 5. Security, Privacy & Configuration Deep Dive

### 5.1 Consent Scope Enforcement
- **Upstream Enforcement:** The frontend / Module 1 must prompt the user with clear terms and confirm explicit consent before invoking Module 2.
- **Scope Verification:** Module 2 validates `consent_scope`.
  - `self_verification`: User verifies content they assert is their own.
  - `authorized_third_party`: User verifies content on behalf of someone else (e.g. legal guardian or verified representative). Requires non-empty `authorization_reference`.
- Missing or `consent_confirmed=False` raises `ConsentRequiredError`.

### 5.2 SSRF Guard & Domain Policy
- **SSRFGuard** resolves candidate URLs to their underlying IPs before any HTTP connection is initiated:
  - Blocks IPv4 Loopback (`127.0.0.0/8`), RFC 1918 Private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), Link-local metadata (`169.254.0.0/16`), Carrier-grade NAT (`100.64.0.0/10`), and IPv6 Loopback/Local (`::1`, `fc00::/7`, `fe80::/10`).
- **Domain Policy:** Optional `VERIFY_DOMAIN_ALLOWLIST` and `VERIFY_DOMAIN_DENYLIST` to restrict verification to approved platforms.

### 5.3 Content-Hash Caching
- **Key Generation:** Keys are strictly `SHA-256(image_bytes)`. No user queries, names, or URLs are ever used as cache keys.
- **What is cached:** Detected face bounding boxes, normalized feature embeddings, and detection confidence scores.
- **What is never cached or persisted:** The user's input face image from Module 1 is never stored in the cache. Candidate temporary files are deleted immediately after verification (retaining only the matched image for Module 3).
- **TTL:** Configurable via `VERIFY_CACHE_TTL_SECONDS` (default 3600s) and `VERIFY_CACHE_MAX_ENTRIES` (default 1000).

### 5.4 Score Calibration Methodology & Limitations
- Raw cosine similarity $s \in [0.0, 1.0]$ between 512-d embeddings is transformed into a calibrated confidence probability $C(s) \in [0.0, 1.0]$ via a logistic sigmoid:
  $$C(s) = \frac{1}{1 + e^{-k(s - s_0)}}$$
  Where $s_0 = 0.65$ (midpoint threshold) and $k = 12.0$ (steepness).
- **Important Disclaimer:** *Calibrated confidence is a mathematical similarity transformation to aid downstream thresholding in Module 3. It is NOT a legally certified or biometric identity-proofing score under regulatory frameworks (e.g., NIST FRVT / eIDAS).*

---

## 6. Observability & Secret Scanning

- **Structured JSON Logging:** Logs single-line JSON records formatted for CloudWatch/Datadog/ELK without external libraries.
- **Redaction:** Embeddings are replaced with `<vector_dim_512>` and bytes with `<bytes_len_X_sha256_Y>`. Zero sensitive payloads exist in log files.
- **CI Secret Scanner:** Includes `SecretScanner.scan_directory(...)` tested in pytest, verifying zero API keys or private keys exist in the repository.

---

## 7. Running Tests

Execute the 38 unit & integration tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

All 38 tests pass covering:
- Async bounded fetching and retry backoff
- Circuit breaker tripping and recovery
- Content-hash cache hits and TTL eviction
- SSRF guard and domain policy allow/denylists
- Score calibration and uncertainty estimation
- Consent record validation
- Structured JSON logging & secret scanning
- Section 11 v2.0 output schema compliance
