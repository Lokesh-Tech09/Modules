# Integration Guide: Connecting Module 1, Module 2, and Module 3

> **Face Identification & Blockchain Verification Pipeline**
> 
> ```
> [Module 1: Face Scan]  ──>  [Module 2: Profile Verify]  ──>  [Module 3: Blockchain Upload]
> ```

---

## 1. Upstream Integration: Module 1 ➔ Module 2

### What Module 1 Must Provide
Module 1 handles face scanning, face detection, and embedding generation (e.g. using InsightFace 512-d). When handoff occurs, Module 1 provides:
1. `image_path`: Path to the scanned face image.
2. `face_embedding`: 512-d float array (`list[float]`).
3. `claimed_urls`: List of URLs provided by the user asserting ownership.
4. `consent`: Explicit user consent record.

### Code Example for Member 1:
```python
from member2_verify import (
    verify_claimed_profile,        # Async interface
    verify_claimed_profile_sync,   # Sync interface
    ConsentRecord,
    ConsentScope,
)

# 1. Prepare user consent collected from frontend
consent = ConsentRecord(
    consent_confirmed=True,
    consent_scope=ConsentScope.SELF_VERIFICATION,
    consent_timestamp="2026-09-05T10:00:00Z",
)

# 2. Call Module 2 (Async version)
verification_result = await verify_claimed_profile(
    image_path="path/to/scanned_face.jpg",
    face_embedding=module1_face_embedding,  # e.g., 512 floats
    claimed_urls=[
        "https://instagram.com/p/candidate_post",
        "https://x.com/user/status/123456"
    ],
    consent=consent,
)

# Or Synchronous version:
# verification_result = verify_claimed_profile_sync(
#     image_path="path/to/scanned_face.jpg",
#     face_embedding=module1_face_embedding,
#     claimed_urls=[...],
#     consent=consent,
# )
```

---

## 2. Downstream Integration: Module 2 ➔ Module 3

### What Module 2 Provides to Module 3
Module 2 returns a JSON-serializable dictionary with `schema_version: "2.0"`.

#### Example Payload Handed to Module 3:
```json
{
  "schema_version": "2.0",
  "status": "verified",
  "input": {
    "image_path": "path/to/scanned_face.jpg"
  },
  "match": {
    "url": "https://instagram.com/p/candidate_post",
    "image_url": "https://cdn.instagram.com/v/photo_123.jpg",
    "local_image_path": "member2_verify/temp/candidate_abc123.jpg",
    "caption": "Verified profile selfie at the hackathon",
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
    "cache_hits": 0
  },
  "consent": {
    "consent_scope": "self_verification",
    "consent_confirmed": true
  }
}
```

### Code Example for Member 3 (Blockchain Upload & Hashing):
```python
import hashlib
import json

def process_for_blockchain(verification_result: dict) -> dict:
    """
    Module 3 processor:
    1. Validates status == 'verified'
    2. Hashes matched image and verification payload
    3. Simulates blockchain transaction upload
    """
    if verification_result.get("status") != "verified":
        return {
            "blockchain_status": "REJECTED",
            "reason": f"Profile not verified (status: {verification_result.get('status')})"
        }

    match_info = verification_result["match"]
    local_img_path = match_info["local_image_path"]

    # 1. Cryptographic hashing of verified image
    with open(local_img_path, "rb") as f:
        image_sha256 = hashlib.sha256(f.read()).hexdigest()

    # 2. Cryptographic hashing of verification record
    record_str = json.dumps(verification_result, sort_keys=True)
    record_sha256 = hashlib.sha256(record_str.encode("utf-8")).hexdigest()

    # 3. Payload stored on-chain or IPFS + Smart Contract
    blockchain_tx = {
        "blockchain_status": "COMMITTED",
        "tx_hash": f"0x{hashlib.sha256((image_sha256 + record_sha256).encode()).hexdigest()[:64]}",
        "verified_url": match_info["url"],
        "image_hash": image_sha256,
        "record_hash": record_sha256,
        "calibrated_confidence": verification_result["verification"]["calibrated_confidence"],
        "timestamp": "2026-09-05T10:05:00Z"
    }
    return blockchain_tx
```

---

## 3. Handling Edge Cases Across Modules

| Scenario | Module 2 Status | Module 3 Action |
|---|---|---|
| Face matches URL candidate | `"status": "verified"` | Commit hash + metadata to blockchain |
| Low similarity score | `"status": "not_verified"` | Reject upload; alert user |
| Candidate URLs unreachable / 404 | `"status": "search_failed"` | Abort upload; prompt user for valid URL |
| User did not check consent | `ConsentRequiredError` | Block pipeline execution; request consent |
| Empty URL list | `EmptyClaimedUrlsError` | Block pipeline execution; no discovery allowed |
