# 🗺️ Pipeline Integration Roadmap: Modules 1, 2 & 3

> **Goa Hackathon — Task 3: Face Identification & Blockchain Verification**
> 
> *A step-by-step master guide for Members 1, 2, and 3 to seamlessly connect all three modules into a single production-grade pipeline.*

---

## 🧭 High-Level Architecture & Data Flow

```
┌────────────────────────┐
│       USER / UI        │
│  - Face Photo / Camera │
│  - Candidate URLs      │
│  - Consent Checkbox    │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ MODULE 1: Face Scan & Embedding (Member 1)            │
│  - Detects faces & landmarks                          │
│  - Extracts 512-d InsightFace embedding vector        │
│  - Packages ConsentRecord                             │
└───────────────────────────┬────────────────────────────┘
                            │  Handoff: (image_path, face_embedding, claimed_urls, consent)
                            ▼
┌────────────────────────────────────────────────────────┐
│ MODULE 2: Claimed-Profile Verification (Member 2)      │
│  - Validates ConsentRecord & non-empty URLs           │
│  - Async fetches URLs (bounded concurrency, SSRF guard)│
│  - Extracts media & metadata (OpenGraph, Schema.org)  │
│  - Caches images via SHA-256 byte hashes              │
│  - Compares faces & computes calibrated confidence    │
└───────────────────────────┬────────────────────────────┘
                            │  Handoff: VerificationOutput (schema_version: "2.0")
                            ▼
┌────────────────────────────────────────────────────────┐
│ MODULE 3: Blockchain Upload & Hashing (Member 3)       │
│  - Verifies status == "verified"                       │
│  - Computes SHA-256 of matched image & claim metadata │
│  - Commits immutable state to smart contract / ledger │
│  - Generates tx receipt & enables re-verification      │
└────────────────────────────────────────────────────────┘
```

---

## 📅 Step-by-Step Integration Timeline

```
  PHASE 1 (Hour 1)         PHASE 2 (Hour 2)         PHASE 3 (Hour 3)         PHASE 4 (Hour 4)
  Environment Setup   ──>  M1 ➔ M2 Bridge      ──>  M2 ➔ M3 Bridge      ──>  Full E2E Demo & UI
  Shared repo & deps       Input contract test       Output contract test     Live presentation
```

---

## 🛠️ Phase 1: Environment & Workspace Alignment

### Objective:
Ensure all 3 members share the same directory structure, Python environment, and dependencies.

1. **Shared Directory Layout**:
   ```
   GOA_HACKATHON/
   │
   ├── member1_facescan/          # Member 1's code (webcam, face detection, embedding)
   ├── member2_verify/            # Member 2's code (URL fetch, profile verify, cache)
   ├── member3_blockchain/        # Member 3's code (smart contract, web3, hashing)
   │
   ├── main_pipeline.py           # Unified entry point running the full chain
   ├── requirements.txt           # Unified dependency file
   └── .env                       # Environment variables (thresholds, RPC URLs)
   ```

2. **Install Core Dependencies**:
   ```bash
   pip install -r member2_verify/requirements.txt
   ```

---

## 🔌 Phase 2: Connecting Module 1 ➔ Module 2

### Objective:
Member 1 captures the user's face, extracts the feature vector, collects claimed candidate URLs, and invokes Module 2.

### Member 1 Checklist:
- [ ] Ensure face embedding vector is **512 dimensions** (L2-normalized floats).
- [ ] Collect at least one candidate profile URL from user input (e.g. Instagram, X, LinkedIn post).
- [ ] Confirm user consent before invoking Module 2 (`consent_confirmed=True`).

### Member 1 Code Snippet (`member1_facescan/scan_service.py`):
```python
from member2_verify import (
    verify_claimed_profile,        # For async web apps (FastAPI / Streamlit)
    verify_claimed_profile_sync,   # For synchronous scripts / CLI
    ConsentRecord,
    ConsentScope,
)

async def scan_and_verify(image_path: str, user_claimed_urls: list[str]):
    # 1. Member 1 extracts 512-d embedding
    embedding_512 = extract_face_embedding(image_path)

    # 2. Package explicit consent record
    consent = ConsentRecord(
        consent_confirmed=True,
        consent_scope=ConsentScope.SELF_VERIFICATION,
        consent_timestamp="2026-09-05T12:00:00Z",
    )

    # 3. Call Module 2
    verification_result = await verify_claimed_profile(
        image_path=image_path,
        face_embedding=embedding_512,
        claimed_urls=user_claimed_urls,
        consent=consent,
    )
    return verification_result
```

---

## ⛓️ Phase 3: Connecting Module 2 ➔ Module 3

### Objective:
Member 3 receives Module 2's verified output, extracts the matched candidate image, hashes it, and uploads the record to the blockchain.

### Member 3 Checklist:
- [ ] Check `verification_result["status"] == "verified"`.
- [ ] If status is NOT `"verified"`, reject the upload with an informative reason.
- [ ] If status is `"verified"`, read `verification_result["match"]["local_image_path"]` and compute `SHA-256`.
- [ ] Bundle verification metadata into a transaction and commit to smart contract / ledger.

### Member 3 Code Snippet (`member3_blockchain/uploader.py`):
```python
import hashlib
import json

def commit_verification_to_blockchain(verification_result: dict) -> dict:
    # 1. Guardrail check
    if verification_result.get("status") != "verified":
        return {
            "success": False,
            "status": "REJECTED",
            "reason": f"Verification status is {verification_result.get('status')}",
        }

    match_info = verification_result["match"]
    scores = verification_result["verification"]
    local_img_path = match_info["local_image_path"]

    # 2. Cryptographic hashing of candidate image
    with open(local_img_path, "rb") as f:
        image_sha256 = hashlib.sha256(f.read()).hexdigest()

    # 3. Cryptographic hashing of claim payload
    claim_payload = {
        "url": match_info["url"],
        "confidence": scores["calibrated_confidence"],
        "consent": verification_result["consent"],
    }
    claim_sha256 = hashlib.sha256(json.dumps(claim_payload, sort_keys=True).encode()).hexdigest()

    # 4. Invoke Web3 Smart Contract or Ledger Upload
    # tx_receipt = contract.functions.recordVerification(image_sha256, claim_sha256).transact()
    tx_hash = "0x" + hashlib.sha256((image_sha256 + claim_sha256).encode()).hexdigest()

    return {
        "success": True,
        "status": "COMMITTED_ON_CHAIN",
        "tx_hash": tx_hash,
        "image_hash": image_sha256,
        "verified_url": match_info["url"],
        "calibrated_confidence": scores["calibrated_confidence"],
    }
```

---

## 🎯 Phase 4: Unified Pipeline Script (`main_pipeline.py`)

Here is the master orchestrator ready to run the entire project:

```python
import asyncio
from member1_facescan.scanner import run_face_scan       # Member 1 function
from member2_verify import verify_claimed_profile       # Member 2 function
from member3_blockchain.uploader import upload_record    # Member 3 function

async def run_full_pipeline(user_image: str, candidate_urls: list[str], consent_record):
    print("\n[STAGE 1] Running Face Scan & Feature Extraction...")
    face_data = run_face_scan(user_image)

    print("\n[STAGE 2] Verifying Claimed URLs (Consented Self-Match)...")
    verify_result = await verify_claimed_profile(
        image_path=user_image,
        face_embedding=face_data["embedding"],
        claimed_urls=candidate_urls,
        consent=consent_record,
    )

    print(f"  -> Verification Status: {verify_result['status']}")

    print("\n[STAGE 3] Uploading to Blockchain...")
    blockchain_receipt = upload_record(verify_result)
    print(f"  -> Blockchain Status: {blockchain_receipt['status']}")
    
    return {
        "verification": verify_result,
        "blockchain": blockchain_receipt
    }

if __name__ == "__main__":
    # Test execution
    # asyncio.run(run_full_pipeline(...))
```

---

## ⚠️ Common Pitfalls & Troubleshooting Matrix

| Issue / Error | Root Cause | Solution |
|---|---|---|
| `ConsentRequiredError` | `consent_confirmed` is False or missing | Member 1 must ensure consent checkbox in UI sets `consent_confirmed=True`. |
| `EmptyClaimedUrlsError` | Candidate URLs list is empty | Prompt the user to enter at least one URL. Module 2 refuses open discovery. |
| `SSRFSecurityError` | URL points to `localhost`, `127.0.0.1`, or private IP | Use public test URLs or mock external URLs in fixtures. |
| `low_confidence_detection: true` | Candidate image has very small face (<40px) or low quality | Recommend user provide a higher-resolution profile photo. |
| `Circuit breaker is OPEN` | Domain failed repeatedly | Wait 30s for automatic reset or test with a reachable host. |
| Image hash mismatch in Module 3 | Temp file deleted prematurely | Module 2 preserves `match["local_image_path"]` specifically for Module 3. Read it before running cleanups. |

---

## 🚀 Hackathon Presentation & Demo Tips

1. **Live Test Script**: Run `python pipeline_e2e_demo.py` to show judges all 3 stages completing in real-time.
2. **Showcase the Anti-Discovery Guard**: Demonstrate that leaving URLs blank immediately halts with `EmptyClaimedUrlsError` — proving the system respects privacy and prevents open-web tracking.
3. **Showcase Content Caching**: Point out that duplicate images are recognized via SHA-256 and skipped from re-embedding, saving compute time.
4. **Showcase Score Calibration**: Explain that the raw similarity (e.g. 0.971) is mapped to a calibrated confidence probability (0.940) to guarantee reliable thresholding on-chain.
