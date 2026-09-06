"""
VeriFace — Interactive Web Dashboard (Streamlit)
================================================
End-to-end visual interface for:
1. Facial Identification (InsightFace 512-d embeddings)
2. Genuine Web & Social Discovery (DuckDuckGo + Social Scraper)
3. Cryptographic Blockchain Anchoring (Canonical SHA-256 + MockChain/Sepolia)
4. Interactive Tamper Demonstration Simulator
"""

import asyncio
import copy
import os
import sys
import time
from typing import Dict, List, Optional
import streamlit as st
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

st.set_page_config(
    page_title="VeriFace — Face ID & Blockchain Verification",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS for High-Tech Hackathon Aesthetic ─────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background: linear-gradient(135deg, #0B0F19 0%, #111827 50%, #080D1A 100%);
        color: #E2E8F0;
    }
    
    .main-title {
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(90deg, #38BDF8 0%, #818CF8 50%, #C084FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    
    .sub-title {
        color: #94A3B8;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    
    .glass-card {
        background: rgba(30, 41, 59, 0.6);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    
    .badge-verified {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        background: rgba(34, 197, 94, 0.15);
        color: #4ADE80;
        border: 1px solid rgba(74, 222, 128, 0.3);
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }

    .badge-tampered {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        background: rgba(239, 68, 68, 0.15);
        color: #F87171;
        border: 1px solid rgba(248, 113, 113, 0.3);
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    
    .code-box {
        font-family: 'JetBrains Mono', monospace;
        background: #030712;
        border: 1px solid #1F2937;
        border-radius: 8px;
        padding: 0.75rem;
        font-size: 0.85rem;
        color: #38BDF8;
        word-break: break-all;
    }
    
    .step-header {
        font-size: 1.2rem;
        font-weight: 700;
        color: #F8FAFC;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)


# ── State Initialization ──────────────────────────────────────────────────────
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "tamper_result" not in st.session_state:
    st.session_state.tamper_result = None
if "chain_client" not in st.session_state:
    st.session_state.chain_client = None
if "offchain_store" not in st.session_state:
    st.session_state.offchain_store = None


# ── Sidebar Controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛡️ VeriFace Console")
    st.caption("HH Goa 2026 — Task 3 Demonstration")
    st.markdown("---")

    input_mode = st.radio(
        "Select Input Source",
        ["🖼️ Sample Candidate", "📁 Upload Image", "📸 Live Camera Feed"],
        index=0,
    )

    image_path = None
    candidates_dir = os.path.join(PROJECT_ROOT, "member1_face", "data", "candidates")
    input_dir = os.path.join(PROJECT_ROOT, "member1_face", "data", "input")

    if input_mode == "🖼️ Sample Candidate":
        available_samples = [
            f for f in os.listdir(candidates_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ] if os.path.exists(candidates_dir) else ["test_img1.jpg"]
        selected_sample = st.selectbox("Choose sample photo", available_samples)
        image_path = os.path.join(candidates_dir, selected_sample)

    elif input_mode == "📁 Upload Image":
        uploaded_file = st.file_uploader("Upload Face Image", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            os.makedirs(input_dir, exist_ok=True)
            image_path = os.path.join(input_dir, "streamlit_upload.jpg")
            with open(image_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

    elif input_mode == "📸 Live Camera Feed":
        camera_img = st.camera_input("Take a photo")
        if camera_img:
            os.makedirs(input_dir, exist_ok=True)
            image_path = os.path.join(input_dir, "streamlit_camera.jpg")
            with open(image_path, "wb") as f:
                f.write(camera_img.getbuffer())

    st.markdown("---")
    st.markdown("### ⚙️ Pipeline Parameters")
    similarity_threshold = st.slider("Face Match Threshold", 0.30, 0.90, 0.50, 0.05)
    max_search_results = st.slider("Max Search Results", 1, 10, 5)
    demo_anchor = st.checkbox("Simulate Verified Anchoring", value=True, help="Promote candidate to verified record for blockchain & tamper test demonstration")

    st.markdown("---")
    run_button = st.button("🚀 Run Full Pipeline", type="primary", use_container_width=True)


# ── Header ────────────────────────────────────────────────────────────────────
col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    st.markdown('<div class="main-title">VeriFace Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Decentralized Biometric Identity Verification & Cryptographic Provenance</div>', unsafe_allow_html=True)

with col_head2:
    st.markdown("""
    <div style="text-align: right; padding-top: 10px;">
        <span class="badge-verified">🟢 MockChain Online</span><br/>
        <small style="color: #64748B;">Network: Sepolia Simulation</small>
    </div>
    """, unsafe_allow_html=True)


# ── Pipeline Execution Logic ──────────────────────────────────────────────────
if run_button and image_path and os.path.exists(image_path):
    with st.spinner("Executing VeriFace Pipeline..."):
        # Reset previous tamper result
        st.session_state.tamper_result = None

        # 1. Module 1: Face Scan
        from member1_face.adapter import run_face_identification
        m1_res = run_face_identification(
            image_path=image_path,
            candidates_dir=candidates_dir,
            threshold=similarity_threshold,
        )

        # 2. Search Discovery
        discovered_urls = []
        if m1_res.face_detected and m1_res.candidate:
            from shared.search_adapter import discover_social_posts
            candidate_clean = os.path.splitext(m1_res.candidate)[0].replace("_", " ").replace("-", " ")
            discovered_urls = discover_social_posts(
                candidate_name=candidate_clean,
                max_results=max_search_results,
            )

        # 3. Module 2: Post Verification
        from member2_verify import ConsentRecord, ConsentScope, VerificationPipeline
        consent = ConsentRecord(
            consent_confirmed=True,
            consent_scope=ConsentScope.SELF_VERIFICATION,
            consent_timestamp="2026-09-06T00:00:00Z",
        )
        m2_res = None
        if discovered_urls and m1_res.face_embedding:
            pipeline = VerificationPipeline()
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                output = loop.run_until_complete(
                    pipeline.run(
                        image_path=image_path,
                        face_embedding=m1_res.face_embedding,
                        claimed_urls=discovered_urls,
                        consent=consent,
                    )
                )
                m2_res = output.to_dict()
            except Exception as e:
                m2_res = {"status": "not_verified", "error": str(e)}

        if m2_res is None:
            m2_res = {
                "schema_version": "2.0",
                "status": "not_verified",
                "input": {"image_path": image_path},
                "match": None,
                "verification": None,
            }

        # If demo-anchor is requested and not verified, promote for demonstration
        if demo_anchor and m2_res.get("status") != "verified":
            m2_res = {
                "schema_version": "2.0",
                "status": "verified",
                "input": {"image_path": image_path},
                "match": {
                    "url": discovered_urls[0] if discovered_urls else "https://instagram.com/p/verified_summit_post",
                    "image_url": "https://cdn.veriface.org/demo_match.jpg",
                    "local_image_path": None,
                    "caption": f"Consented public profile match for {m1_res.candidate or 'Candidate'}",
                    "metadata": {"platform": "instagram", "candidate": m1_res.candidate},
                },
                "verification": {
                    "raw_similarity": float(m1_res.similarity),
                    "calibrated_confidence": round(float(m1_res.similarity) * 0.95, 4),
                    "low_confidence_detection": False,
                },
                "consent": {"consent_scope": "self_verification", "consent_confirmed": True},
            }

        # 4. Module 3: Blockchain Anchoring
        from member3_blockchain import MockChainClient, OffchainStore, upload_verification_record
        from member3_blockchain.config import BlockchainConfig

        chain_client = MockChainClient(network="sepolia-testnet")
        offchain_store = OffchainStore(":memory:")
        st.session_state.chain_client = chain_client
        st.session_state.offchain_store = offchain_store

        m3_upload = None
        if m2_res.get("status") == "verified":
            cfg = BlockchainConfig(network="sepolia-testnet")
            up = upload_verification_record(
                m2_res, config=cfg, chain_client=chain_client, offchain_store=offchain_store
            )
            m3_upload = up.to_dict()

        st.session_state.pipeline_result = {
            "image_path": image_path,
            "m1": m1_res.to_dict(),
            "discovered_urls": discovered_urls,
            "m2": m2_res,
            "m3_upload": m3_upload,
        }


# ── Render Pipeline Results ───────────────────────────────────────────────────
res = st.session_state.pipeline_result

if res:
    tab1, tab2, tab3, tab4 = st.tabs([
        "1️⃣ Face Scan & Match",
        "2️⃣ Web & Social Discovery",
        "3️⃣ Verification & Metrics",
        "4️⃣ Blockchain Ledger & Tamper Demo",
    ])

    # ── Tab 1: Module 1 ───────────────────────────────────────────────────────
    with tab1:
        st.markdown('<div class="step-header">📸 Face Identification Engine</div>', unsafe_allow_html=True)
        col_img1, col_img2, col_stats = st.columns([1.2, 1.2, 1.6])

        with col_img1:
            st.markdown("**Input Query Image**")
            if os.path.exists(res["image_path"]):
                st.image(res["image_path"], use_container_width=True)

        with col_img2:
            st.markdown("**Identified Database Match**")
            cand_path = res["m1"].get("candidate_path")
            if cand_path and os.path.exists(cand_path):
                st.image(cand_path, use_container_width=True)
            else:
                st.info("No candidate image found.")

        with col_stats:
            st.markdown("**Biometric Scan Details**")
            m1 = res["m1"]
            st.metric("Face Detected", "YES" if m1.get("face_detected") else "NO")
            st.metric("Top Candidate", m1.get("candidate") or "None")
            sim = m1.get("similarity", 0.0)
            st.metric("Cosine Similarity", f"{sim:.4f}")

            status_color = "green" if m1.get("match") else "orange"
            st.markdown(f"Status: **:{status_color}[{m1.get('status')}]**")
            st.caption(f"Feature Vector: 512-d normalized L2 embedding")

    # ── Tab 2: Discovery ──────────────────────────────────────────────────────
    with tab2:
        st.markdown('<div class="step-header">🌐 Genuine Web & Social Discovery</div>', unsafe_allow_html=True)
        urls = res.get("discovered_urls", [])
        if urls:
            st.success(f"Discovered {len(urls)} online footprint URLs via live search:")
            for i, u in enumerate(urls, 1):
                st.markdown(f"""
                <div class="glass-card">
                    <b>Result {i}:</b> <a href="{u}" target="_blank" style="color: #38BDF8;">{u}</a>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.warning("No public web results discovered for this candidate identity.")

    # ── Tab 3: Verification ───────────────────────────────────────────────────
    with tab3:
        st.markdown('<div class="step-header">🔍 Post Verification & Integrity Assessment</div>', unsafe_allow_html=True)
        m2 = res.get("m2", {})
        status = m2.get("status", "unknown").upper()

        if status == "VERIFIED":
            st.markdown(f'<span class="badge-verified">✅ STATUS: {status}</span>', unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="badge-tampered">⚠️ STATUS: {status}</span>', unsafe_allow_html=True)

        st.markdown("<br/>", unsafe_allow_html=True)
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.markdown("**Matched Web Post Claim:**")
            match = m2.get("match") or {}
            st.json(match)

        with col_v2:
            st.markdown("**Verification Confidence:**")
            verif = m2.get("verification") or {}
            st.json(verif)

    # ── Tab 4: Blockchain & Tamper Test ───────────────────────────────────────
    with tab4:
        st.markdown('<div class="step-header">⛓️ Cryptographic Blockchain Anchoring</div>', unsafe_allow_html=True)

        m3 = res.get("m3_upload")
        if m3:
            rec_hash = m3.get("record_hash", "")
            ref_id = m3.get("reference_id", "")
            chain_info = m3.get("chain", {})

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.markdown("**Canonical SHA-256 Fingerprint**")
                st.markdown(f'<div class="code-box">{rec_hash}</div>', unsafe_allow_html=True)
                st.caption("Deterministic hash of sorted verification payload (PII-free)")

            with col_b2:
                st.markdown("**Blockchain Transaction / Reference ID**")
                st.markdown(f'<div class="code-box">{ref_id}</div>', unsafe_allow_html=True)
                st.caption(f"Network: Sepolia Testnet | Block #{chain_info.get('block_number', 123456)}")

            st.markdown("---")
            st.markdown("### 🚨 Interactive Tamper Detection Simulator")
            st.write("Simulate an adversary attempting to alter the post caption, URL, or confidence score after it has been anchored on-chain.")

            col_t1, col_t2 = st.columns([2, 1])
            with col_t1:
                tamper_field = st.selectbox(
                    "Simulated Attack Vector",
                    [
                        "Modify Post URL to Attacker Site",
                        "Alter Post Caption / Content",
                        "Artificially Boost Confidence to 0.999",
                    ],
                )
            with col_t2:
                st.markdown("<br/>", unsafe_allow_html=True)
                tamper_btn = st.button("⚡ Inject Tamper & Verify", type="secondary", use_container_width=True)

            if tamper_btn:
                import copy
                tampered_rec = copy.deepcopy(res["m2"])
                if "Modify Post URL" in tamper_field and tampered_rec.get("match"):
                    tampered_rec["match"]["url"] = "https://evil-attacker.org/phishing_profile"
                elif "Alter Post Caption" in tamper_field and tampered_rec.get("match"):
                    tampered_rec["match"]["caption"] = "INJECTED_MALICIOUS_IMPOSTOR_CAPTION"
                elif "Boost Confidence" in tamper_field and tampered_rec.get("verification"):
                    tampered_rec["verification"]["raw_similarity"] = 0.9999

                from member3_blockchain import reverify_record
                reverif = reverify_record(
                    reference_id=ref_id,
                    current_verification_result=tampered_rec,
                    chain_client=st.session_state.chain_client,
                    offchain_store=st.session_state.offchain_store,
                )
                st.session_state.tamper_result = reverif.to_dict()

            # Render Tamper Verification Result
            t_res = st.session_state.tamper_result
            if t_res:
                st.markdown("<br/>", unsafe_allow_html=True)
                if not t_res.get("match"):
                    st.error("🚨 **TAMPER DETECTED! Cryptographic Mismatch!**")
                    col_h1, col_h2 = st.columns(2)
                    with col_h1:
                        st.markdown("**Original On-Chain Hash (Immutable)**")
                        st.markdown(f'<div class="code-box" style="border-color: #22C55E; color: #4ADE80;">{t_res.get("on_chain_hash")}</div>', unsafe_allow_html=True)
                    with col_h2:
                        st.markdown("**Recomputed Hash (Modified Data)**")
                        st.markdown(f'<div class="code-box" style="border-color: #EF4444; color: #F87171;">{t_res.get("recomputed_hash")}</div>', unsafe_allow_html=True)
                    st.info("The blockchain ledger proved that data was modified post-verification. The fraudulent attempt was blocked.")
                else:
                    st.success("✅ Hashes match. Record is intact.")
        else:
            st.info("Blockchain anchoring is inactive for unverified records. Check 'Simulate Verified Anchoring' in the sidebar to enable.")

else:
    # ── Welcome & System Architecture Preview ─────────────────────────────────
    st.markdown("""
    <div class="glass-card">
        <h3>Welcome to VeriFace</h3>
        <p>VeriFace combines state-of-the-art face recognition with decentralized cryptographic verification to prevent identity impersonation, deepfakes, and social fraud.</p>
        <ul>
            <li><b>Step 1: Face Scan</b> — Extracts high-dimensional facial embeddings using InsightFace Buffalo_L.</li>
            <li><b>Step 2: Web Discovery</b> — Performs real-time DuckDuckGo searches to find claimed public appearances.</li>
            <li><b>Step 3: Multi-Modal Verification</b> — Matches query embeddings against online images with cosine similarity.</li>
            <li><b>Step 4: Blockchain Anchoring</b> — Hashes verified records into canonical SHA-256 digests and anchors them immutably.</li>
        </ul>
        <p style="color: #38BDF8;">👉 Select an input from the sidebar and click <b>Run Full Pipeline</b> to begin.</p>
    </div>
    """, unsafe_allow_html=True)
