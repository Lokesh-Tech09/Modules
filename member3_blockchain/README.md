# ⛓️ Module 3: Blockchain Upload & Re-verification

> **Task 3: Face Identification & Blockchain Verification**  
> *Component: Module 3 — Immutable Ledger Anchoring & Cryptographic Tamper Detection*

---

## 📖 1. Overview & Purpose

Module 3 is the final stage of the 3-member identity verification pipeline:

```
[Module 1: Face Scan] ──> [Module 2: Profile Verification] ──> [Module 3: Blockchain Upload & Re-verify]
```

When Module 2 successfully verifies a claimed profile (matching a scanned face against user-provided candidate URLs with explicit consent), Module 3 receives the structured `VerificationResult` and creates an **immutable, tamper-evident cryptographic record** of that verification event.

### 🛡️ Why Hashing (Not Raw Data) Goes On-Chain: Strict Data Minimization

Blockchains are **public, replicated, and permanently immutable**. Anything written to a smart contract or distributed ledger remains visible and cannot be deleted or rectified (contrary to GDPR "Right to be Forgotten" and privacy regulations).

To solve this, Module 3 enforces **Strict Data Minimization**:
1. **Never writes personal data on-chain**: Face images, facial embeddings, profile URLs, captions, author usernames, and PII are strictly barred from the blockchain.
2. **Anchors only a cryptographic fingerprint**: Module 3 computes a canonical **SHA-256 digest** over the verified record and anchors only:
   - `record_hash`: 64-character hex SHA-256 fingerprint
   - `timestamp`: UTC ISO 8601 timestamp
   - `schema_version`: e.g. `"2.0"`
   - `reference_id`: Unique non-reversible transaction/anchor reference
3. **Off-Chain Confidential Storage**: The complete verification record is preserved in a secure, access-controlled local repository (`offchain_store.py`).
4. **Zero Knowledge Proof of Integrity**: Anyone holding the verification record can recompute its SHA-256 hash and match it against the immutable on-chain state to prove it has not been altered, forged, or backdated.

---

## 🏗️ 2. Architecture & Directory Structure

```
member3_blockchain/
│
├── __init__.py               # Public API: upload_verification_record, reverify_record
├── hasher.py                 # Canonicalize + SHA-256 record hashing
├── chain_client.py           # Blockchain abstraction: MockChainClient & EVMChainClient
├── offchain_store.py         # SQLite private store with restricted file permissions
├── upload_pipeline.py        # Orchestration: validate -> hash -> on-chain anchor -> store
├── reverify_pipeline.py      # Orchestration: fetch -> rehash -> compare -> tamper detection
├── models.py                 # Pydantic v2 schemas: UploadResult, ReverificationResult, BlockchainConfig
├── config.py                 # Environment variables loader & rate limiter / cost-guard
├── utils.py                  # Deterministic JSON canonicalization & cryptographic helpers
├── exceptions.py             # Custom exceptions hierarchy
├── demo.py                   # Standalone runnable demonstration script
├── contracts/
│   └── VerificationAnchor.sol# Production-ready Solidity smart contract for EVM networks
├── tests/                    # 100% coverage unit & integration tests
│   ├── test_hasher.py
│   ├── test_chain_client.py
│   ├── test_offchain_store.py
│   ├── test_upload_pipeline.py
│   └── test_reverify_pipeline.py
├── requirements.txt          # Module-specific dependencies
└── README.md                 # This documentation
```

---

## 🔌 3. Integration Contract with Upstream (Module 2)

Module 3 has **no downstream consumers** — it is the immutable audit terminal of the pipeline.

### Input Contract (Expected from Module 2)

```json
{
  "schema_version": "2.0",
  "status": "verified",
  "match": {
    "url": "https://instagram.com/p/candidate_01",
    "image_url": "https://cdn.instagram.com/v/photo_123.jpg",
    "local_image_path": "temp/candidate_01.jpg",
    "caption": "Summit selfie at Goa Hackathon! #ConsentedVerification",
    "metadata": {
      "platform": "instagram"
    }
  },
  "verification": {
    "raw_similarity": 0.971,
    "calibrated_confidence": 0.94,
    "low_confidence_detection": false
  },
  "consent": {
    "consent_scope": "self_verification",
    "consent_confirmed": true
  }
}
```

> [!IMPORTANT]
> **Guardrail**: If `status != "verified"`, Module 3 immediately refuses execution and raises `UnverifiedRecordError`. Unverified, rejected, or error outputs are never committed to the ledger.

---

## ⚙️ 4. Configuration & Environment Variables

Copy `.env.example` to `.env` or set environment variables:

```bash
# Provider selection: 'mock' (default, offline sandbox) or 'sepolia', 'ganache', 'evm'
BLOCKCHAIN_PROVIDER=mock
BLOCKCHAIN_NETWORK=sepolia-testnet

# Remote RPC URL (for Sepolia / Ganache / EVM testnets)
BLOCKCHAIN_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_ALCHEMY_KEY

# Smart contract address for VerificationAnchor.sol
BLOCKCHAIN_CONTRACT_ADDRESS=0x1234567890123456789012345678901234567890

# Wallet private key reference (NEVER write keys in code or repo; use an env reference)
BLOCKCHAIN_PRIVATE_KEY_ENV_VAR=WALLET_PRIVATE_KEY

# Cost Guard & Rate Limiter: Max writes per minute to prevent runaway transaction fees
MAX_WRITES_PER_MINUTE=10

# Off-chain SQLite database path
OFFCHAIN_STORE_PATH=member3_blockchain/offchain_store.db
```

---

## 💻 5. Quickstart & Usage

### 1. Installation

```bash
cd member3_blockchain
pip install -r requirements.txt
```

### 2. Python API Usage

```python
from member3_blockchain import (
    upload_verification_record,
    reverify_record,
    BlockchainConfig,
)

# Step A: Upload verified record
upload_result = upload_verification_record(module2_verification_output)

print(f"Status: {upload_result.status}")              # 'uploaded'
print(f"Reference ID: {upload_result.reference_id}")  # '0xabc123...'
print(f"Record Hash: {upload_result.record_hash}")    # 'd37f4daf...'
print(f"Block Number: {upload_result.chain.block_number}")

# Step B: Re-verify record at any time later
reverify_result = reverify_record(reference_id=upload_result.reference_id)

print(f"Integrity: {reverify_result.status}")  # 'intact'
print(f"Matches On-Chain: {reverify_result.match}")  # True
```

### 3. Output Contract Schemas

#### Upload Output (`UploadResult`):
```json
{
  "status": "uploaded",
  "reference_id": "0xb2c5a71e67dabadf2c0ecadd7e424c96965088f37d09e225272148c231d34c92",
  "record_hash": "d37f4dafe09ba899ba29b5ff37048d56d082a7ab0ead32247bbc425a2346cc57",
  "chain": {
    "network": "sepolia-testnet",
    "confirmed": true,
    "block_number": 123457,
    "tx_hash": "0xb2c5a71e67dabadf2c0ecadd7e424c96965088f37d09e225272148c231d34c92",
    "timestamp": "2026-09-06T13:25:40Z"
  }
}
```

#### Re-verification Output (`ReverificationResult`):
- **Untampered Record**:
  ```json
  {
    "status": "intact",
    "reference_id": "0xb2c5a71e...",
    "on_chain_hash": "d37f4daf...",
    "recomputed_hash": "d37f4daf...",
    "match": true
  }
  ```
- **Tampered Record** (e.g. modified score or URL):
  ```json
  {
    "status": "tampered",
    "reference_id": "0xb2c5a71e...",
    "on_chain_hash": "d37f4daf...",
    "recomputed_hash": "8216b1e4...",
    "match": false
  }
  ```
- **Unknown Record**:
  ```json
  {
    "status": "not_found",
    "reference_id": "0xunknown...",
    "on_chain_hash": null,
    "recomputed_hash": null,
    "match": false
  }
  ```

---

## 🧪 6. Testing & Demonstration

### Run All Module 3 Unit Tests
```bash
pytest member3_blockchain/tests/ -v
```

### Run Standalone Demonstration Script
```bash
python member3_blockchain/demo.py
```

### Run Full End-to-End Pipeline (Modules 1, 2, 3)
```bash
python pipeline_e2e_demo.py
```

---

## 🔐 7. Security & Cost Guard

1. **Zero Secret Leaks**: No private keys or RPC secrets are checked into source control. All sensitive keys are loaded via `.env` and excluded in `.gitignore`.
2. **Cost Guard**: Built-in sliding-window rate limiter prevents accidental high-frequency on-chain writes (raises `RateLimitExceededError`).
3. **POSIX Permissions**: Database files are initialized with `0600` owner permissions to prevent unauthorized local reading.
4. **Failure Atomicity**: If blockchain interaction fails, no orphaned records are committed to the off-chain store.
