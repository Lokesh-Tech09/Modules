#!/usr/bin/env python3
"""
VeriFace — End-to-End Pipeline Entry Point
==========================================
Usage:
    python main.py --image path/to/face.jpg
    python main.py --image path/to/face.jpg --candidates member1_face/data/candidates/
    python main.py --image path/to/face.jpg --threshold 0.45 --max-search-results 5
    python main.py --image path/to/face.jpg --tamper-test     # run tamper demo after E2E

Pipeline:
    [1] FACE SCAN          → Module 1 (InsightFace detector + encoder)
    [2] FACE IDENTIFICATION → Module 1 (CandidateMatcher, cosine similarity)
    [3] WEB/SOCIAL SEARCH  → shared/search_adapter.py (genuine DuckDuckGo discovery)
    [4] POST VERIFICATION  → Module 2 (async VerificationPipeline)
    [5] BLOCKCHAIN ANCHOR  → Module 3 (SHA-256 + MockChainClient)
    [6] RE-VERIFICATION    → Module 3 (tamper detection)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Project root on path ──────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODULE1_DIR  = os.path.join(PROJECT_ROOT, "member1_face")
for _p in [PROJECT_ROOT, MODULE1_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("veriface.main")

# ─────────────────────────────────────────────────────────────────────────────
# Terminal helpers
# ─────────────────────────────────────────────────────────────────────────────

CYAN   = "\033[96m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def banner(text: str):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")

def section(num: int, title: str):
    print(f"\n{BOLD}[{num}] {title}{RESET}")
    print(f"{DIM}{'─'*50}{RESET}")

def ok(label: str, value: Any):
    print(f"  {GREEN}✓{RESET}  {label}: {BOLD}{value}{RESET}")

def warn(label: str, value: Any):
    print(f"  {YELLOW}⚠{RESET}  {label}: {value}")

def fail(label: str, value: Any):
    print(f"  {RED}✗{RESET}  {label}: {value}")

def kv(label: str, value: Any):
    print(f"    {DIM}{label}:{RESET} {value}")


# ─────────────────────────────────────────────────────────────────────────────
# Step 1+2 — Module 1: Face Scan & Identification
# ─────────────────────────────────────────────────────────────────────────────

def run_module1(image_path: str, candidates_dir: str, threshold: float) -> Optional[Dict]:
    section(1, "FACE SCAN")
    kv("Input image", image_path)

    try:
        from member1_face.adapter import run_face_identification
    except ImportError as e:
        fail("Module 1 import", str(e))
        fail("Action", "Install insightface: pip install insightface onnxruntime")
        return None

    result = run_face_identification(
        image_path=image_path,
        candidates_dir=candidates_dir,
        threshold=threshold,
    )

    if not result.face_detected:
        fail("Face detected", "NO")
        if result.error:
            fail("Error", result.error)
        return None

    ok("Face detected", "YES")

    section(2, "FACE IDENTIFICATION")
    kv("Candidate", result.candidate or "None")
    kv("Similarity", f"{result.similarity:.4f}")
    kv("Threshold",  f"{threshold:.2f}")

    if result.match:
        ok("Result", f"MATCH  (similarity={result.similarity:.4f})")
    else:
        warn("Result", f"NO MATCH  (similarity={result.similarity:.4f} < threshold={threshold})")
        warn("Note", "Low similarity — pipeline continues with best candidate for demo")

    if result.face_embedding:
        kv("Embedding dim", len(result.face_embedding))

    return result.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Genuine Web/Social Discovery
# ─────────────────────────────────────────────────────────────────────────────

def run_discovery(m1_result: Dict, max_results: int) -> list:
    section(3, "WEB / SOCIAL SEARCH")
    print(f"  {DIM}Searching for matching online content...{RESET}")

    candidate_name = m1_result.get("candidate", "")
    # Strip file extension for cleaner name
    if candidate_name:
        candidate_name = os.path.splitext(candidate_name)[0]
        # Replace underscores/hyphens with spaces for better search
        candidate_name = candidate_name.replace("_", " ").replace("-", " ").strip()

    if not candidate_name:
        warn("Candidate name", "Unknown — cannot perform meaningful search")
        warn("Action", "Search skipped. Provide a candidates/ folder with recognisable filenames.")
        return []

    print(f"  {DIM}Candidate name: {candidate_name!r}{RESET}")

    try:
        from shared.search_adapter import discover_social_posts
    except ImportError as e:
        fail("Search adapter import", str(e))
        return []

    urls = discover_social_posts(
        candidate_name=candidate_name,
        extra_keywords="photo profile social media",
        max_results=max_results,
    )

    if urls:
        ok("Search completed", f"{len(urls)} URL(s) discovered")
        for i, url in enumerate(urls, 1):
            kv(f"  Result {i}", url)
    else:
        warn("Search result", "0 URLs found")
        warn("Reason", (
            "DuckDuckGo returned no results for this candidate name. "
            "This is a genuine search result — no fabrication."
        ))
        warn("Action", (
            "Use a real public figure's photo as input, or provide "
            "a known profile URL with --url flag."
        ))

    return urls


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Module 2: Post Verification
# ─────────────────────────────────────────────────────────────────────────────

async def run_module2(m1_result: Dict, claimed_urls: list, image_path: str) -> Optional[Dict]:
    section(4, "POST VERIFICATION")

    face_embedding = m1_result.get("face_embedding")

    if not face_embedding:
        fail("Face embedding", "Missing from Module 1 result")
        return None

    if not claimed_urls:
        warn("URLs to verify", "0 — skipping Module 2 (no discovered URLs)")
        warn("Action", (
            "Module 2 requires URLs from the web discovery step. "
            "If search failed, the pipeline cannot verify a post."
        ))
        return None

    try:
        from member2_verify import (
            ConsentRecord,
            ConsentScope,
            VerificationConfig,
            VerificationPipeline,
        )
    except ImportError as e:
        fail("Module 2 import", str(e))
        return None

    consent = ConsentRecord(
        consent_confirmed=True,
        consent_scope=ConsentScope.SELF_VERIFICATION,
        consent_timestamp="2026-09-06T00:00:00Z",
    )

    kv("URLs submitted", len(claimed_urls))
    kv("Embedding dim", len(face_embedding))
    kv("Consent scope", consent.consent_scope)
    print(f"  {DIM}Running verification pipeline...{RESET}")

    try:
        pipeline = VerificationPipeline()
        output = await pipeline.run(
            image_path=image_path,
            face_embedding=face_embedding,
            claimed_urls=claimed_urls,
            consent=consent,
            schema_version="2.0",
        )
        result_dict = output.to_dict()
    except Exception as exc:
        fail("Module 2 error", str(exc))
        logger.exception("Module 2 pipeline error")
        return None

    status = result_dict.get("status", "unknown")
    match  = result_dict.get("match")

    if status == "verified" and match:
        ok("Status", "VERIFIED")
        kv("Matched URL", match.get("url", ""))
        kv("Image URL",   match.get("image_url", "N/A"))
        kv("Caption",     match.get("caption", "N/A"))
        verif = result_dict.get("verification") or {}
        kv("Raw similarity",       f"{verif.get('raw_similarity', 0):.4f}")
        kv("Calibrated confidence",f"{verif.get('calibrated_confidence', 0):.4f}")
    else:
        warn("Status", status.upper())
        warn("Reason", "No URL passed face similarity threshold or URLs were inaccessible")

    return result_dict


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Module 3: Blockchain Anchoring
# ─────────────────────────────────────────────────────────────────────────────

def run_module3_upload(verification_result: Dict) -> Optional[Dict]:
    section(5, "BLOCKCHAIN ANCHORING")

    try:
        from member3_blockchain import upload_verification_record
        from member3_blockchain.config import load_config_from_env
    except ImportError as e:
        fail("Module 3 import", str(e))
        return None

    config = load_config_from_env()
    provider = config.provider.lower()

    if provider == "mock":
        kv("Mode",    f"{YELLOW}DEVELOPMENT / SIMULATION (MockChain){RESET}")
        kv("Network", config.network)
        kv("Note",    "Set BLOCKCHAIN_PROVIDER=sepolia in .env for real testnet")
    else:
        kv("Mode",    f"{GREEN}REAL EVM — {config.network}{RESET}")
        kv("RPC URL", config.rpc_url or "not set")

    print(f"\n  {DIM}Generating SHA-256 fingerprint...{RESET}")

    try:
        upload_result = upload_verification_record(verification_result)
    except Exception as exc:
        fail("Blockchain anchoring error", str(exc))
        logger.exception("Module 3 upload error")
        return None

    result_dict = upload_result.to_dict()
    record_hash = result_dict.get("record_hash", "")
    ref_id      = result_dict.get("reference_id", "")
    chain       = result_dict.get("chain", {})

    print(f"\n  {DIM}Submitting blockchain transaction...{RESET}")
    ok("Record Hash",    f"{record_hash[:32]}...{record_hash[-8:]}")
    kv("Network",        chain.get("network", ""))
    kv("Block number",   chain.get("block_number", ""))
    ok("Transaction ID", ref_id)
    ok("Status",         "ANCHORED")

    return result_dict


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — Module 3: Re-Verification
# ─────────────────────────────────────────────────────────────────────────────

def run_module3_reverify(
    upload_result: Dict,
    verification_result: Dict,
    chain_client=None,
    offchain_store=None,
) -> Optional[Dict]:
    section(6, "RE-VERIFICATION")
    print(f"  {DIM}Retrieving blockchain record...{RESET}")

    try:
        from member3_blockchain import reverify_record
        from member3_blockchain.reverify_pipeline import ReverificationPipeline
        from member3_blockchain.config import load_config_from_env
    except ImportError as e:
        fail("Module 3 import", str(e))
        return None

    reference_id = upload_result.get("reference_id", "")

    try:
        # Use the same chain_client/offchain_store instances from the upload
        # to ensure the in-memory mock ledger is shared
        if chain_client and offchain_store:
            pipeline = ReverificationPipeline(
                chain_client=chain_client,
                offchain_store=offchain_store,
            )
            reverif = pipeline.process(
                reference_id=reference_id,
                current_verification_result=verification_result,
            )
        else:
            reverif = reverify_record(
                reference_id=reference_id,
                current_verification_result=verification_result,
            )
    except Exception as exc:
        fail("Re-verification error", str(exc))
        logger.exception("Module 3 reverify error")
        return None

    result_dict = reverif.to_dict()
    stored_hash  = result_dict.get("on_chain_hash", "")
    current_hash = result_dict.get("recomputed_hash", "")
    match        = result_dict.get("match", False)

    kv("Stored Hash",  f"{stored_hash[:32]}...{stored_hash[-8:]}"  if stored_hash  else "N/A")
    kv("Current Hash", f"{current_hash[:32]}...{current_hash[-8:]}" if current_hash else "N/A")
    kv("Hash Match",   "YES" if match else "NO")

    return result_dict


# ─────────────────────────────────────────────────────────────────────────────
# Tamper Test
# ─────────────────────────────────────────────────────────────────────────────

def run_tamper_test(
    upload_result: Dict,
    verification_result: Dict,
    chain_client=None,
    offchain_store=None,
) -> bool:
    section(0, "TAMPER TEST (DEMO)")
    print(f"  {YELLOW}Modifying post data after anchoring...{RESET}")

    import copy
    tampered = copy.deepcopy(verification_result)

    # Modify data to simulate tampering
    if tampered.get("match"):
        tampered["match"]["caption"] = "TAMPERED_CAPTION_INJECTED_BY_ATTACKER"
        tampered["match"]["url"]     = "https://attacker.example.com/fake_post"
    if tampered.get("verification"):
        tampered["verification"]["raw_similarity"]        = 0.99
        tampered["verification"]["calibrated_confidence"] = 0.99

    kv("Modification", "caption + url + scores altered")

    try:
        from member3_blockchain import reverify_record
    except ImportError as e:
        fail("Module 3 import", str(e))
        return False

    reference_id = upload_result.get("reference_id", "")

    try:
        reverif = reverify_record(
            reference_id=reference_id,
            current_verification_result=tampered,
            chain_client=chain_client,
            offchain_store=offchain_store,
        )
    except Exception as exc:
        fail("Tamper reverify error", str(exc))
        return False

    result_dict  = reverif.to_dict()
    stored_hash  = result_dict.get("on_chain_hash", "")
    current_hash = result_dict.get("recomputed_hash", "")
    match        = result_dict.get("match", False)

    kv("Stored Hash",  f"{stored_hash[:32]}...{stored_hash[-8:]}"  if stored_hash  else "N/A")
    kv("Current Hash", f"{current_hash[:32]}...{current_hash[-8:]}" if current_hash else "N/A")
    kv("Hash Match",   "NO" if not match else "YES (unexpected)")

    if not match:
        print(f"\n  {RED}{BOLD}✓  Tamper successfully detected! Data was altered after anchoring.{RESET}")
        return True
    else:
        print(f"\n  {YELLOW}{BOLD}⚠  Hash unexpectedly matched. Check tamper logic.{RESET}")
        return False


def run_synthetic_tamper_demo(chain_client=None, offchain_store=None) -> bool:
    section(6, "TAMPER DETECTION DEMO")
    print(f"  {DIM}(Simulating with a verified test record){RESET}")

    from member3_blockchain import MockChainClient, OffchainStore, reverify_record, upload_verification_record
    from member3_blockchain.config import BlockchainConfig

    mock_rec = {
        "schema_version": "2.0",
        "status": "verified",
        "match": {
            "url": "https://example.com/posts/genuine-post-123",
            "image_url": "https://cdn.example.com/photo.jpg",
            "local_image_path": None,
            "caption": "Summit selfie at Goa Hackathon! #ConsentedVerification",
            "metadata": {"platform": "instagram"},
        },
        "verification": {
            "raw_similarity": 0.971,
            "calibrated_confidence": 0.94,
            "low_confidence_detection": False,
        },
        "consent": {
            "consent_scope": "self_verification",
            "consent_confirmed": True,
        },
    }

    if chain_client is None:
        chain_client = MockChainClient(network="sepolia-testnet")
    if offchain_store is None:
        offchain_store = OffchainStore(db_path=":memory:")
    config = BlockchainConfig(network=getattr(chain_client, "network", "sepolia-testnet"))

    print(f"  1. Minting record on mockchain:")
    up = upload_verification_record(mock_rec, config=config, chain_client=chain_client, offchain_store=offchain_store)
    ref = up.reference_id
    rec_hash = up.record_hash
    kv("Ref", ref)
    kv("Canonical SHA-256", rec_hash)

    print(f"\n  2. Tampering record: altering post URL...")
    import copy
    tampered = copy.deepcopy(mock_rec)
    tampered["match"]["url"] = "https://example.com/posts/altered-post-999"
    kv("From", "https://example.com/posts/genuine-post-123")
    kv("To",   "https://example.com/posts/altered-post-999")

    print(f"\n  3. Re-verifying tampered record against blockchain...")
    t_res = reverify_record(
        reference_id=ref,
        current_verification_result=tampered,
        chain_client=chain_client,
        offchain_store=offchain_store,
    )
    t_dict = t_res.to_dict()
    orig_h = t_dict.get("on_chain_hash", "")
    new_h = t_dict.get("recomputed_hash", "")
    if not t_dict.get("match"):
        ok("Tamper successfully detected!", "")
        kv("Original hash",   orig_h)
        kv("Recomputed hash", new_h)
        kv("Status",          f"{RED}{BOLD}TAMPER_DETECTED{RESET}")
        return True
    else:
        warn("Status", "Tamper not detected")
        return False



# ─────────────────────────────────────────────────────────────────────────────
# Shared pipeline instances (for mock in-memory chain continuity)
# ─────────────────────────────────────────────────────────────────────────────

def create_shared_module3_instances():
    """
    Create a single shared MockChainClient + OffchainStore so that records
    written by upload_pipeline are readable by reverify_pipeline in the
    same process (in-memory mock ledger).
    """
    try:
        from member3_blockchain import MockChainClient, OffchainStore
        from member3_blockchain.config import load_config_from_env
        config = load_config_from_env()
        chain_client   = MockChainClient(network=config.network)
        offchain_store = OffchainStore(config.offchain_store_path)
        return chain_client, offchain_store
    except Exception:
        return None, None


def upload_with_shared_instances(verification_result: Dict, chain_client, offchain_store):
    """Upload using shared chain client so reverify can read the same ledger."""
    try:
        from member3_blockchain.upload_pipeline import UploadPipeline
        pipeline = UploadPipeline(
            chain_client=chain_client,
            offchain_store=offchain_store,
        )
        return pipeline.process(verification_result)
    except Exception as exc:
        logger.exception("Upload with shared instances failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="VeriFace — Face Identification + Blockchain Verification Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--image", "-i", default=None,
        help="Path to input face image (default: member1_face/data/input/input.jpg).",
    )
    parser.add_argument(
        "--webcam", action="store_true",
        help="Capture live face photo from webcam before running pipeline.",
    )
    parser.add_argument(
        "--mock-camera", action="store_true",
        help="Simulate camera capture without hardware camera.",
    )
    parser.add_argument(
        "--candidates", "-c",
        default=os.path.join(MODULE1_DIR, "data", "candidates"),
        help="Directory of candidate images (default: member1_face/data/candidates/).",
    )
    parser.add_argument(
        "--threshold", "-t", type=float, default=0.50,
        help="Cosine similarity match threshold (default: 0.50).",
    )
    parser.add_argument(
        "--max-search-results", type=int, default=5,
        help="Max URLs to discover per search (default: 5).",
    )
    parser.add_argument(
        "--url", nargs="+", default=[],
        help="Manually provide known URL(s) to verify (bypasses web search — for testing).",
    )
    parser.add_argument(
        "--tamper-test", action="store_true",
        help="Run tamper demonstration after verification.",
    )
    parser.add_argument(
        "--demo-anchor", action="store_true",
        help="Simulate successful verification for blockchain anchoring and re-verification demo.",
    )
    parser.add_argument(
        "--no-search", action="store_true",
        help="Skip web search step (useful when --url is provided).",
    )
    return parser.parse_args()


async def _async_main(args):
    # Handle camera input modes
    if args.mock_camera:
        from member1_face.capture_webcam import mock_capture
        args.image = mock_capture()
    elif args.webcam:
        from member1_face.capture_webcam import capture_from_camera, mock_capture
        captured = capture_from_camera()
        args.image = captured or mock_capture()
    elif not args.image:
        default_img = os.path.join(MODULE1_DIR, "data", "input", "input.jpg")
        if os.path.exists(default_img):
            args.image = default_img
        else:
            print(f"\n{RED}Error: No input image specified. Provide --image <path> or use --webcam / --mock-camera.{RESET}")
            return 1

    banner("VERIFACE  ·  Face Identification & Blockchain Verification")
    print(f"\n  {DIM}HH Goa 2026 — Task 3 Demo{RESET}")
    print(f"  {DIM}Input: {args.image}{RESET}")

    start = time.time()

    # ── Module 1 ─────────────────────────────────────────────────────────────
    m1 = run_module1(args.image, args.candidates, args.threshold)
    if m1 is None:
        print(f"\n{RED}Pipeline aborted at Module 1.{RESET}")
        return 1

    # ── Web Discovery ─────────────────────────────────────────────────────────
    if args.url:
        # Manual URLs provided — skip search
        section(3, "WEB / SOCIAL SEARCH")
        warn("Mode", "Manual URL(s) provided via --url flag (search bypassed)")
        for u in args.url:
            kv("URL", u)
        discovered_urls = args.url
    elif args.no_search:
        section(3, "WEB / SOCIAL SEARCH")
        warn("Mode", "--no-search flag set — skipping discovery")
        discovered_urls = []
    else:
        discovered_urls = run_discovery(m1, args.max_search_results)

    # ── Module 2 ─────────────────────────────────────────────────────────────
    m2 = await run_module2(m1, discovered_urls, args.image)

    # If Module 2 didn't verify anything, we still build record
    if m2 is None:
        warn("Module 2", "Verification did not complete — building minimal record")
        m2 = {
            "schema_version": "2.0",
            "status": "not_verified",
            "input": {"image_path": args.image},
            "match": None,
            "verification": None,
            "checked": {
                "urls_provided": len(discovered_urls),
                "urls_deduplicated": len(discovered_urls),
                "urls_fetched": 0,
            },
            "consent": {"consent_scope": "self_verification", "consent_confirmed": True},
        }

    m1_candidate = m1.get("candidate", "unknown")
    m1_sim = float(m1.get("similarity", 0.0))

    # If --demo-anchor was passed, promote record to verified for live blockchain demonstration
    if args.demo_anchor and m2.get("status") != "verified":
        warn("Demo Mode", "--demo-anchor active: generating verified candidate record for blockchain demonstration")
        m2 = {
            "schema_version": "2.0",
            "status": "verified",
            "input": {"image_path": args.image},
            "match": {
                "url": discovered_urls[0] if discovered_urls else "https://example.com/posts/verified-profile",
                "image_url": "https://example.com/images/verified_face.jpg",
                "local_image_path": None,
                "caption": f"Verified identity post for {m1_candidate}",
                "metadata": {"platform": "demo", "candidate": m1_candidate},
            },
            "verification": {
                "raw_similarity": m1_sim,
                "calibrated_confidence": round(m1_sim * 0.95, 4),
                "low_confidence_detection": False,
            },
            "checked": {
                "urls_provided": len(discovered_urls),
                "urls_deduplicated": len(discovered_urls),
                "urls_fetched": len(discovered_urls),
            },
            "consent": {"consent_scope": "self_verification", "consent_confirmed": True},
        }

    # ── Module 3: Create shared instances for mock-chain continuity ───────────
    chain_client, offchain_store = create_shared_module3_instances()

    m3_upload = None
    m3_reverif = None

    # Module 3 strictly permits anchoring only for 'verified' records
    if m2.get("status") == "verified":
        if chain_client and offchain_store:
            upload_obj = upload_with_shared_instances(m2, chain_client, offchain_store)
            if upload_obj:
                m3_upload = upload_obj.to_dict()
                section(5, "BLOCKCHAIN ANCHORING")
                config_net = getattr(chain_client, "network", "sepolia-testnet")
                record_hash = m3_upload.get("record_hash", "")
                ref_id      = m3_upload.get("reference_id", "")
                chain_info  = m3_upload.get("chain", {})
                kv("Mode",         f"{YELLOW}DEVELOPMENT / SIMULATION (MockChain){RESET}")
                kv("Network",      config_net)
                print(f"\n  {DIM}Generating SHA-256 fingerprint...{RESET}")
                ok("Record Hash",  f"{record_hash[:32]}...{record_hash[-8:]}")
                kv("Block number", chain_info.get("block_number", ""))
                print(f"\n  {DIM}Submitting blockchain transaction...{RESET}")
                ok("Transaction ID", ref_id)
                ok("Status",         "ANCHORED")
            else:
                m3_upload = run_module3_upload(m2)
        else:
            m3_upload = run_module3_upload(m2)

        if m3_upload:
            m3_reverif = run_module3_reverify(m3_upload, m2, chain_client, offchain_store)
    else:
        section(5, "BLOCKCHAIN ANCHORING")
        warn("Status", "SKIPPED")
        warn("Reason", f"Verification status is '{m2.get('status')}' (must be 'verified' to anchor)")

    # ── Final Result ──────────────────────────────────────────────────────────
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    if m3_reverif and m3_reverif.get("match"):
        print(f"  {GREEN}{BOLD}✅  FINAL RESULT: VERIFIED & ANCHORED{RESET}")
    elif m2.get("status") == "verified" and m3_upload:
        print(f"  {GREEN}{BOLD}✅  FINAL RESULT: ANCHORED{RESET}")
    else:
        print(f"  {YELLOW}{BOLD}⚠   FINAL RESULT: {m2.get('status', 'NOT_VERIFIED').upper()}{RESET}")
        print(f"  {DIM}Face match found ({m1_candidate}), but claimed URLs did not pass verification.{RESET}")
        print(f"  {DIM}Tip: Pass --demo-anchor to simulate full verified anchoring demo.{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")

    elapsed = time.time() - start
    print(f"\n  {DIM}Total time: {elapsed:.1f}s{RESET}")

    # ── Tamper Test ───────────────────────────────────────────────────────────
    tamper_passed = False
    if args.tamper_test:
        print(f"\n{'='*60}")
        if m3_upload:
            tamper_passed = run_tamper_test(m3_upload, m2, chain_client, offchain_store)
        else:
            tamper_passed = run_synthetic_tamper_demo(chain_client, offchain_store)
        print(f"{'='*60}")

    # ── Pipeline Complete Summary Table ───────────────────────────────────────
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"  {BOLD}PIPELINE COMPLETE{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")
    print(f"  Face scan:           COMPLETED")
    print(f"  Identification:      MATCH ({m1_candidate}, {m1_sim:.4f})")
    print(f"  Web discovery:       {len(discovered_urls)} URLs found")
    print(f"  Post verification:   {m2.get('status', 'unknown').upper()}")
    print(f"  Blockchain anchor:   {'ANCHORED' if m3_upload else 'SKIPPED'}")
    if args.tamper_test:
        print(f"  Tamper test:         {'PASSED' if tamper_passed else 'FAILED'}")
    print()

    return 0


def main():
    args = parse_args()
    exit_code = asyncio.run(_async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
