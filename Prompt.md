# MODULE 2 — Claimed-Profile Verification (Self-Match)

## Face Identification & Blockchain Verification — Task 3

You are an expert Python AI engineer responsible ONLY for implementing **Module 2: Claimed-Profile Verification** of a larger 3-member project.

The overall project pipeline is:

Face Scan → Face Identification → Verify Against User-Provided Profile → Blockchain Upload → Re-verification

Module 1 handles face detection and face embedding. Module 3 handles hashing, blockchain upload, and re-verification. Your module sits between them.

> **Key difference from open-web identity search:** this module never searches the internet to discover who someone is. It only verifies whether a face matches images already present at a URL the user themselves explicitly supplies (e.g., "here is my own Instagram post, confirm it's me"). This makes it a 1-to-1 consented verification tool, not a person-finder.

---

## 1. Primary Objective

Build a Python module that:

1. Receives a face image/embedding from Module 1.
2. Receives one or more **user-supplied candidate URLs** (the user asserts "this is my own post/profile").
3. Fetches only those specific, user-provided public URLs — never searches for or discovers new ones.
4. Detects and embeds any faces in the fetched content.
5. Compares those faces against the input embedding.
6. Returns a verification result: does the claimed profile/post contain the same face as the scanned input?

No reverse-image search, no social-media crawling, no discovery of pages the user didn't explicitly provide.

---

## 2. Important Requirement

Do NOT implement:

- Any reverse-image search or web search step
- Any mechanism that takes only a face and returns URLs the user didn't supply
- Auth bypass, CAPTCHA bypass, private-account access, or scraping beyond what the user's provided URL exposes publicly
- Storage or reuse of the candidate's face data beyond this single verification call

The system's job is confirmation of a claimed identity link, not discovery of an unknown one.

---

## 3. Input Contract

```json
{
  "image_path": "input.jpg",
  "face_embedding": [...],
  "claimed_urls": ["https://instagram.com/p/xyz", "https://twitter.com/handle/status/123"]
}
```

Interface:

```python
def verify_claimed_profile(
    image_path,
    face_embedding=None,
    claimed_urls: list[str] = []
):
    ...
```

`claimed_urls` is **required and non-empty** — the module should refuse to run in "discovery mode" with zero URLs.

---

## 4. Architecture

```
member2_verify/
│
├── __init__.py
├── candidate_fetcher.py      # fetch only the given URLs
├── post_extractor.py         # extract image/caption/metadata from those URLs
├── face_matcher.py           # compare faces
├── verification_pipeline.py  # orchestration
├── models.py
├── config.py
├── utils.py
├── exceptions.py
├── requirements.txt
└── README.md
```

Note: no `reverse_search.py`, no `web_search.py`, no `candidate_ranker.py` searching across many discovered candidates — ranking only applies across the finite list the user supplied.

---

## 5. `candidate_fetcher.py`

Given each URL in `claimed_urls`:

1. Fetch only publicly accessible content at that exact URL.
2. Extract the primary image if available.
3. Validate it's an image; reject invalid files.
4. Enforce file-size/timeout limits.
5. Never bypass login, CAPTCHA, paywalls, or access controls — mark unavailable and continue.

Same result shape as before (`fetch_status: success/failed`).

---

## 6. `post_extractor.py`

Same responsibilities as the original spec (OpenGraph → JSON-LD → HTML meta → title/snippet fallback chain, no fabrication, nulls for missing fields) — just applied only to the user-given URLs, never to search results.

---

## 7. `face_matcher.py`

Same as the original spec: detect faces in the fetched image(s), embed with the same representation Module 1 uses (e.g. InsightFace), compare to the input embedding, handle multi-face images by taking the best match, configurable threshold in `config.py`. No invented thresholds.

---

## 8. `verification_pipeline.py`

```
STEP 1  Validate input image + embedding
STEP 2  Validate claimed_urls is non-empty
STEP 3  Fetch each claimed URL
STEP 4  Extract post metadata per URL
STEP 5  Detect faces in each fetched image
STEP 6  Generate embeddings for detected faces
STEP 7  Compare each to the input embedding
STEP 8  Score per-URL match confidence
STEP 9  Aggregate: best-matching claimed URL, if any
STEP 10 Return structured result
```

---

## 9. Output Contract to Module 3

```json
{
  "status": "verified",
  "input": { "image_path": "input.jpg" },
  "match": {
    "url": "https://...",
    "image_url": "https://...",
    "local_image_path": "temp/candidate_01.jpg",
    "caption": "...",
    "metadata": {}
  },
  "verification": {
    "face_similarity": 0.968,
    "overall_score": 0.968
  },
  "checked": {
    "urls_provided": 2,
    "urls_fetched": 2,
    "urls_with_face_match": 1
  }
}
```

If no claimed URL matches: `"status": "not_verified"`, `match: null`.

If a URL is unreachable: mark it `fetch_status: "failed"` and continue with the rest — never fail the whole pipeline for one bad URL.

---

## 10. Privacy / Responsible Use

- This module only ever processes URLs the user explicitly and knowingly submitted about themselves (or content they have rights/consent to verify).
- It must reject or flag usage patterns where `claimed_urls` appears to reference a third party without their consent (e.g., a required `consent_confirmed: true` flag from Module 1/the frontend).
- No open-ended discovery function should exist anywhere in this module — that's a structural guarantee, not just a policy note.

---

## 11. Testing

Same categories as the original list (valid/invalid input, no face detected, URL fetch success/failure, same face/different face, multiple faces, missing metadata, duplicate URLs) — adapted to fixed-URL-list mocks instead of mocked search responses.

---

## 12. Acceptance Criteria

- [ ] Requires and validates non-empty `claimed_urls` input
- [ ] Never performs search/discovery of new URLs
- [ ] Fetches only user-provided URLs
- [ ] Compares faces and returns similarity/confidence
- [ ] Handles per-URL failures gracefully
- [ ] Includes a consent-flag check
- [ ] No hardcoded credentials
- [ ] Tests + documentation included

---

This spec preserves the engineering value of the original design — embeddings, fetching, metadata extraction, scoring, blockchain handoff — while removing the piece that would turn it into a tool for identifying non-consenting people from a photo.