# VeriFace

**Face Identification → Post Verification → Blockchain Anchoring**

HH Goa 2026 — Task 3 Submission

---

## Architecture

```
python main.py --image path/to/face.jpg

[1] FACE SCAN          Module 1  InsightFace buffalo_l, 512-d ArcFace embedding
[2] FACE ID            Module 1  CandidateMatcher — cosine similarity gallery search
[3] WEB DISCOVERY      shared/   DuckDuckGo — genuine real-time search (no hardcoded URLs)
[4] POST VERIFICATION  Module 2  Async 14-step VerificationPipeline
[5] SHA-256 HASH       Module 3  Canonical JSON → SHA-256 fingerprint
[6] BLOCKCHAIN ANCHOR  Module 3  MockChainClient (dev) / EVMChainClient (Sepolia testnet)
[7] RE-VERIFICATION    Module 3  Tamper detection — stored hash vs recomputed hash
```

---

## Team Structure

| Module | Owner | Location |
|--------|-------|----------|
| Module 1 — Face Identification | Mayur | `member1_face/` |
| Module 2 — Post Verification | Lokesh | `member2_verify/` |
| Module 3 — Blockchain | (your name) | `member3_blockchain/` |
| Integration Layer | All | `main.py`, `pipeline_e2e_demo.py`, `shared/` |

---

## Quickstart

```bash
# 1. Clone and enter directory
git clone https://github.com/Lokesh-Tech09/Modules.git --branch feature/module3-blockchain
cd Modules

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Copy environment config
cp .env.example .env           # Edit .env for real testnet credentials

# 5. Run the full E2E pipeline
python main.py --image member1_face/data/input/input.jpg --tamper-test
```

> **Note:** On first run InsightFace will download the `buffalo_l` model (~280 MB). This is a one-time operation.

---

## Usage

```bash
# Full E2E pipeline (default input image)
python main.py --image member1_face/data/input/input.jpg

# With tamper detection demo
python main.py --image member1_face/data/input/input.jpg --tamper-test

# Provide manual URL (bypass DuckDuckGo search — useful for testing)
python main.py --image path/to/face.jpg --url https://example.com/post/123

# Adjust similarity threshold
python main.py --image path/to/face.jpg --threshold 0.45

# Control search results count
python main.py --image path/to/face.jpg --max-search-results 3

# Skip web search entirely
python main.py --image path/to/face.jpg --no-search

# Legacy E2E demo script
python pipeline_e2e_demo.py --image member1_face/data/input/input.jpg --tamper-test
```

---

## Pipeline Steps — Detailed

### [1] Face Scan
- `FaceDetector` initializes InsightFace `buffalo_l` model (CPU mode)
- Detects all faces; selects primary face by largest bounding box area
- No face → pipeline aborts with clear error message

### [2] Face Identification
- `FaceEncoder` extracts 512-dimensional L2-normalized ArcFace embedding
- `CandidateMatcher` compares input embedding against `member1_face/data/candidates/` gallery
- Returns best match, similarity score, and match flag (threshold default: 0.50)

### [3] Web / Social Discovery
- Uses `duckduckgo-search` library — **genuine real-time search, no hardcoded URLs**
- Query: `"{candidate_name} social media profile photo"`
- Results sorted by social domain priority (Twitter, Instagram, LinkedIn, etc.)
- Empty result → clearly reported; no fabrication
- Adapter is modular — swap in SerpAPI or Google Custom Search by setting `SERPAPI_KEY`

### [4] Post Verification (Module 2)
- Async `VerificationPipeline` with 14-step lifecycle
- Fetches discovered URLs with bounded concurrency, circuit-breaker, robots.txt respect
- Extracts post images; computes cosine similarity vs face embedding
- Returns `VerificationOutput` with status, match details, and calibrated confidence scores

### [5] SHA-256 Fingerprinting (Module 3)
- `canonicalize_verification_record()`: deterministic JSON with sorted keys
- Excludes ephemeral fields: `local_image_path`, `face_embedding`, `image_bytes`, `embedding`
- `compute_sha256()`: 64-char hex digest over canonical UTF-8 string

### [6] Blockchain Anchoring (Module 3)
- **Development mode** (`BLOCKCHAIN_PROVIDER=mock`): in-memory `MockChainClient`
  - Simulates block number increments and reference ID generation
  - Enforces data minimization: only `record_hash + {timestamp, schema_version}` stored on-chain
  - Never commits raw data, URLs, embeddings, or PII
- **Testnet mode** (`BLOCKCHAIN_PROVIDER=sepolia`): real `EVMChainClient` via JSON-RPC
  - Configure `BLOCKCHAIN_RPC_URL` (Alchemy/Infura) + `WALLET_PRIVATE_KEY` in `.env`

### [7] Re-Verification & Tamper Detection
- `reverify_record(reference_id, current_result)`:
  1. Load stored record from SQLite off-chain store
  2. Fetch stored hash from blockchain (MockChain or EVM)
  3. Recompute SHA-256 over current record
  4. Compare: `stored_hash == recomputed_hash` → **VERIFIED** / **TAMPERED**

---

## Blockchain Configuration

| `BLOCKCHAIN_PROVIDER` | Mode | Requirements |
|-----------------------|------|--------------|
| `mock` (default)      | In-memory simulation | None |
| `sepolia`             | Ethereum Sepolia testnet | `BLOCKCHAIN_RPC_URL` + `WALLET_PRIVATE_KEY` |
| `ganache`             | Local Ganache | Running Ganache instance |
| `evm`                 | Any EVM chain | `BLOCKCHAIN_RPC_URL` |

```bash
# .env for Sepolia testnet
BLOCKCHAIN_PROVIDER=sepolia
BLOCKCHAIN_NETWORK=sepolia-testnet
BLOCKCHAIN_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_ALCHEMY_KEY
# In shell (NEVER in .env file):
export WALLET_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
```

---

## Running Tests

```bash
# All tests
python -m pytest

# Integration tests only (no insightface model required)
python -m pytest tests/test_integration.py -v

# Module 3 unit tests
python -m pytest member3_blockchain/tests/ -v

# Module 2 unit tests
python -m pytest tests/ -v
```

**Test results (at submission):** 43/43 passed ✅

---

## Project Structure

```
VeriFace/
├── main.py                        ← Root E2E CLI entry point
├── pipeline_e2e_demo.py           ← Demo script (updated: real M1 + genuine search)
├── requirements.txt               ← Consolidated dependencies
├── pytest.ini                     ← Test discovery config
├── conftest.py                    ← Root conftest
├── .env.example                   ← Environment config template (never commit .env)
│
├── member1_face/                  ← Module 1: Face Identification (by Mayur)
│   ├── adapter.py                 ← Integration adapter (NEW)
│   ├── main.py                    ← Original CLI (unchanged)
│   ├── src/
│   │   ├── face_detector.py       ← InsightFace detector (unchanged)
│   │   ├── face_encoder.py        ← ArcFace embedding (unchanged)
│   │   ├── face_matcher.py        ← Cosine similarity (unchanged)
│   │   └── candidate_matcher.py   ← Gallery matching (unchanged)
│   └── data/
│       ├── input/input.jpg
│       └── candidates/
│
├── member2_verify/                ← Module 2: Post Verification (by Lokesh)
│   ├── verification_pipeline.py   ← 14-step async pipeline (unchanged)
│   ├── candidate_fetcher.py       ← Async HTTP + circuit breaker (unchanged)
│   └── ...                        ← All files unchanged
│
├── member3_blockchain/            ← Module 3: Blockchain (unchanged)
│   ├── hasher.py                  ← SHA-256 + canonical JSON (unchanged)
│   ├── chain_client.py            ← MockChain + EVMChain (unchanged)
│   ├── upload_pipeline.py         ← Anchor pipeline (unchanged)
│   ├── reverify_pipeline.py       ← Tamper detection (unchanged)
│   ├── offchain_store.py          ← SQLite store (unchanged)
│   ├── contracts/
│   │   └── VerificationAnchor.sol ← Solidity smart contract (unchanged)
│   └── tests/                     ← 5 existing test files (unchanged)
│
├── shared/
│   ├── schemas.py                 ← Cross-module contracts (unchanged)
│   └── search_adapter.py          ← Genuine web discovery (NEW)
│
└── tests/
    └── test_integration.py        ← E2E integration tests (NEW)
```

---

## Security

- **No PII on-chain**: `chain_client.py` enforces strict data minimization — only `record_hash + {timestamp, schema_version}` written to blockchain
- **No private keys in code**: `WALLET_PRIVATE_KEY` must be set as shell environment variable
- **No hardcoded URLs**: search results are genuine, real-time DuckDuckGo discoveries
- **No fabricated results**: if search returns 0 results, pipeline reports it clearly — no simulation
- **Ephemeral fields excluded from hash**: `local_image_path`, `face_embedding`, `image_bytes` never affect the on-chain fingerprint

---

## Screen Recording — Final Demo Steps

```bash
# Terminal 1: Run full E2E pipeline with tamper test
python main.py --image member1_face/data/input/input.jpg --tamper-test

# Expected output sequence:
# [1] FACE SCAN          → Face detected, embedding extracted
# [2] FACE IDENTIFICATION → Best candidate matched
# [3] WEB/SOCIAL SEARCH  → Real DuckDuckGo discovery results
# [4] POST VERIFICATION  → Module 2 status (verified/not_verified)
# [5] BLOCKCHAIN ANCHOR  → SHA-256 hash + reference ID
# [6] RE-VERIFICATION    → ✅ VERIFIED (hashes match)
# TAMPER TEST            → ❌ TAMPERED (hashes differ after modification)
```
