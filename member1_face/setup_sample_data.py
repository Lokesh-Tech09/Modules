"""Sample Data Setup Helper.

Sets up sample test face images in:
- data/input/input.jpg (Face A - Lena)
- data/candidates/candidate1.jpg (Face A - Same person with slight lighting variation)
- data/candidates/candidate2.jpg (Face B - Different person, Messi)
- data/candidates/candidate3.jpg (Face B - Different person with altered contrast)
"""

import os
import urllib.request
import cv2
import numpy as np


def ensure_directories():
    """Create data and output directory tree."""
    dirs = [
        "data/input",
        "data/candidates",
        "output/detected",
        "output/embeddings",
        "output/results",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"[Setup] Directory ready: {d}")


def download_file(url: str, target_path: str) -> bool:
    """Download file with timeout and browser user-agent."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            with open(target_path, "wb") as f:
                f.write(data)
        print(f"[Setup] Downloaded: {target_path}")
        return True
    except Exception as e:
        print(f"[Setup] Notice: Could not download {url} ({e})")
        return False


def setup_sample_images():
    """Download and prepare candidate images for the face identification test."""
    ensure_directories()

    # Source 1: Lena (Person A)
    lena_url = "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg"
    # Source 2: Messi (Person B)
    messi_url = "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/messi5.jpg"

    input_path = "data/input/input.jpg"
    cand1_path = "data/candidates/candidate1.jpg"
    cand2_path = "data/candidates/candidate2.jpg"
    cand3_path = "data/candidates/candidate3.jpg"

    # Download input face (Person A)
    if not os.path.exists(input_path) or os.path.getsize(input_path) < 1000:
        download_file(lena_url, input_path)

    # Candidate 1: Same person A with slight color/lighting adjustment
    if os.path.exists(input_path):
        img_a = cv2.imread(input_path)
        if img_a is not None:
            # Create a realistic variation (e.g. brightness shift)
            cand1_img = cv2.convertScaleAbs(img_a, alpha=0.95, beta=10)
            cv2.imwrite(cand1_path, cand1_img)
            print(f"[Setup] Prepared: {cand1_path} (Person A - True Match)")

    # Candidate 2: Person B (Different person)
    download_file(messi_url, cand2_path)

    # Candidate 3: Person B variation (Different person)
    if os.path.exists(cand2_path):
        img_b = cv2.imread(cand2_path)
        if img_b is not None:
            cand3_img = cv2.convertScaleAbs(img_b, alpha=0.85, beta=20)
            cv2.imwrite(cand3_path, cand3_img)
            print(f"[Setup] Prepared: {cand3_path} (Person B - True Non-Match)")


if __name__ == "__main__":
    setup_sample_images()
    print("\n[OK] Sample test data ready. You can now execute 'python main.py'.")
