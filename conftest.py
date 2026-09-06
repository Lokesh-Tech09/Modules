"""Root conftest.py — ensures all module packages are importable from any test."""
import sys
import os

# Add project root to path so all module imports work from any test file
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODULE1_DIR = os.path.join(PROJECT_ROOT, "member1_face")

for path in [PROJECT_ROOT, MODULE1_DIR]:
    if path not in sys.path:
        sys.path.insert(0, path)
