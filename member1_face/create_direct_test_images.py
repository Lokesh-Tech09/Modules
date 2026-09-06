"""Utility script to create test_img1.jpg and test_img2.jpg directly in face_identification folder."""

import os
import shutil

src_input = os.path.join("data", "input", "input.jpg")
src_cand1 = os.path.join("data", "candidates", "candidate1.jpg")
src_cand2 = os.path.join("data", "candidates", "candidate2.jpg")

if os.path.exists(src_input):
    shutil.copy(src_input, "test_img1.jpg")
    print("[OK] Created test_img1.jpg (Face A)")

if os.path.exists(src_cand1):
    shutil.copy(src_cand1, "test_img2.jpg")
    print("[OK] Created test_img2.jpg (Face A - Match)")

if os.path.exists(src_cand2):
    shutil.copy(src_cand2, "test_img3_different.jpg")
    print("[OK] Created test_img3_different.jpg (Face B - No Match)")
