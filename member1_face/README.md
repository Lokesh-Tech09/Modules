# 🎯 Face Identification & Verification Module

A modular, production-ready Python pipeline for **Face Detection, 512-Dimensional Deep Feature Embedding Extraction, Cosine Similarity Matching, and Candidate Ranking** powered by [InsightFace](https://github.com/deepinsight/insightface), [OpenCV](https://opencv.org/), [ONNX Runtime](https://onnxruntime.ai/), and [NumPy](https://numpy.org/).

---

## 📌 Project Context & Pipeline

In the full hackathon architecture, this module handles the core visual biometric intelligence:

```
                  ┌───────────────────────────────┐
                  │       Input Face Image        │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │ Face Detection & Embedding    │  ◄── [THIS MODULE]
                  │ Extraction (InsightFace 512D) │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │ Web / Social Media Candidate  │
                  │ Search & Image Retrieval      │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │ Face Comparison & Match       │  ◄── [THIS MODULE]
                  │ Verification (Cosine Ranker)  │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │ Blockchain Hash Storage &     │
                  │ Verification Audit Trail      │
                  └───────────────────────────────┘
```

---

## 📂 Project Structure

```
face_identification/
│
├── data/
│   ├── input/
│   │   └── input.jpg               # Primary query face image
│   │
│   └── candidates/
│       ├── candidate1.jpg          # Candidate/Reference face 1
│       ├── candidate2.jpg          # Candidate/Reference face 2
│       └── candidate3.jpg          # Candidate/Reference face 3
│
├── output/
│   ├── detected/                   # Annotated images with bounding boxes & landmarks
│   ├── embeddings/                 # Saved 512-D float32 .npy feature vectors
│   └── results/                    # Match results JSON & side-by-side comparison images
│
├── src/
│   ├── __init__.py                 # Package initializations
│   ├── face_detector.py            # Face detection & bounding box annotations
│   ├── face_encoder.py             # 512-D embedding extraction & L2 normalization
│   ├── face_matcher.py             # Cosine similarity calculation & threshold metrics
│   └── candidate_matcher.py        # Multi-candidate directory scanning & ranking engine
│
├── main.py                         # End-to-end 8-step pipeline CLI application
├── setup_sample_data.py            # Sample test dataset downloader
├── requirements.txt                # Python dependencies
└── README.md                       # Comprehensive documentation
```

---

## 🚀 Key Features

- **Robust Face Detection**: Uses InsightFace (`buffalo_l` / SCRFD) to locate all faces, coordinates, and 5-point facial keypoints.
- **Primary Face Selection**: Automatically prioritizes the foreground/largest bounding box area in multi-person images.
- **512-D Deep Metric Embeddings**: Generates ArcFace feature vectors normalized with L2 unit norm for geometric invariance.
- **Persistent Vectors**: Saves and loads high-precision embeddings as `.npy` NumPy binary files.
- **Multi-Candidate Search & Ranking**: Scans entire directories of candidate images, detects faces in each, computes similarities, and ranks candidates in descending order.
- **Configurable Cosine Matching**: Compares embedding angles with calibrated thresholds for False Acceptance Rate (FAR) vs. False Rejection Rate (FRR) control.
- **Structured JSON Output**: Exports standardized JSON reports for seamless integration with downstream web search and blockchain modules.
- **Rich Visual Diagnostics**: Exports annotated bounding boxes, keypoint overlays, and side-by-side comparison graphics.
- **Fail-Safe Error Handling**: Gracefully handles missing directories, corrupted files, images with zero faces, and edge cases.

---

## ⚙️ Installation & Setup

### 1. Prerequisites
- **Python 3.10+** (Tested on Python 3.10 and 3.11 on Windows, Linux, and macOS)
- **pip** package manager

### 2. Clone or Navigate to Directory
```bash
cd "d:/Personal_projects/HH_Goa hackathon/face_identification"
```

### 3. Install Required Dependencies
```bash
pip install -r requirements.txt
```

> **Note on Dependencies:** The pipeline runs on `onnxruntime` with `CPUExecutionProvider` by default for universal zero-configuration compatibility without requiring CUDA/CUDNN setup.

---

## 🧪 Quick Start & Testing

### Step 1: Set Up Sample Test Images
Run the automated downloader to populate `data/input/` and `data/candidates/` with test portraits:
```bash
python setup_sample_data.py
```

### Step 2: Run the Pipeline
Run the main application:
```bash
python main.py
```

### Custom CLI Arguments
You can customize paths, similarity thresholds, and preview display:
```bash
# Example with custom input, candidate folder, and threshold
python main.py --input "data/input/input.jpg" --candidates "data/candidates" --threshold 0.50

# Run in headless mode (no pop-up GUI windows, perfect for automated testing)
python main.py --no-display
```

---

## 📊 Sample Execution Output

### Terminal Output
```
====================================
FACE IDENTIFICATION RESULT
====================================

Input Image:
input.jpg

Faces Detected:
1

Candidates Processed:
3

Best Candidate:
candidate1.jpg

Similarity Score:
0.82

Result:
MATCH

====================================
```

### Generated JSON Output (`output/results/match_results.json`)
```json
{
    "input_image": "data/input/input.jpg",
    "matches": [
        {
            "candidate": "candidate1.jpg",
            "similarity": 0.8184,
            "match": true,
            "status": "SUCCESS"
        },
        {
            "candidate": "candidate2.jpg",
            "similarity": 0.1245,
            "match": false,
            "status": "SUCCESS"
        },
        {
            "candidate": "candidate3.jpg",
            "similarity": 0.0832,
            "match": false,
            "status": "SUCCESS"
        }
    ]
}
```

---

## 🧠 Technical Deep-Dive

### 1. Face Embeddings Explained
A face embedding is a compact, fixed-length numerical representation (in this case, a **512-dimensional floating-point vector**) that encapsulates the unique topological and geometric features of a human face (distance between eyes, nose bridge geometry, jawline contours, etc.).

InsightFace's ArcFace model maps raw facial pixels onto a hyperspherical latent space where:
- Images of the **same individual** map to points that are clustered closely together (small angular distance).
- Images of **different individuals** map to points that are far apart (large angular distance).

### 2. Cosine Similarity & Threshold Calibration
We evaluate match likelihood by calculating the **Cosine Similarity** between two L2-normalized embedding vectors $\mathbf{u}$ and $\mathbf{v}$:

$$\text{Cosine Similarity} = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\|_2 \|\mathbf{v}\|_2}$$

Because both vectors are unit-normalized ($\|\mathbf{u}\| = \|\mathbf{v}\| = 1$), this reduces to the direct dot product $\mathbf{u} \cdot \mathbf{v}$.

| Similarity Range | Interpretation | Typical Confidence Category |
| :--- | :--- | :--- |
| **0.70 to 1.00** | Extremely high similarity; identical individual with high certainty. | Very High Match |
| **0.50 to 0.70** | Same individual under different lighting, aging, or slight camera angles. | High / Moderate Match |
| **0.40 to 0.50** | Borderline zone; possible lookalike or extreme facial pose distortion. | Borderline |
| **< 0.40** | Distinct individuals. | Mismatch |

> **Threshold Recommendation**: The default threshold is configured at `0.50`. Increase to `0.60+` if your application requires strict zero-false-positive security, or lower to `0.45` if matching low-resolution or historic photos.

---

## 🔗 Downstream Hackathon Integration

### Integrating with Web / Social Media Candidate Search
1. The search crawler extracts images from public sources and saves them into `data/candidates/`.
2. `CandidateMatcher.match_gallery()` is invoked programmatically:
   ```python
   from src.candidate_matcher import CandidateMatcher
   
   matcher = CandidateMatcher(threshold=0.50)
   results = matcher.match_gallery(
       input_image_path="data/input/input.jpg",
       candidates_dir="data/candidates",
       output_json_path="output/results/match_results.json"
   )
   print("Top match:", results["best_candidate"])
   ```

### Integrating with Blockchain Hash Storage
1. Hash the saved `.npy` embedding file (`output/embeddings/input_embedding.npy`) using SHA-256:
   ```python
   import hashlib
   
   with open("output/embeddings/input_embedding.npy", "rb") as f:
       embedding_hash = hashlib.sha256(f.read()).hexdigest()
   print("Blockchain Record Hash:", embedding_hash)
   ```
2. Store `embedding_hash`, `input_image_hash`, and match verification timestamp on-chain for tamper-proof audit trails.

---

## ⚠️ Known Limitations & Edge Cases

1. **Extreme Occlusion**: Heavy sunglasses, masks, or extreme side profiles (>60 degrees yaw) can impede face detection.
2. **Low Resolution**: Faces with bounding box sizes smaller than 40x40 pixels yield degraded embedding fidelity.
3. **Lighting & Contrast**: Extreme overexposure or underexposure may require histogram equalization preprocessing.

---

## 🛡️ Privacy & Ethical Considerations

- **Consent & Authorization**: Biometric recognition must strictly comply with local data protection regulations (e.g., GDPR, CCPA, DPDP Act).
- **No Direct Storage of PII**: The system stores mathematical embedding vectors (`.npy`) rather than personal identifiable information.
- **Fairness & Bias**: Evaluated with balanced models to mitigate demographic disparities in facial recognition accuracy.
