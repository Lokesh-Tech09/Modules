"""Face Encoder Module.

This module is responsible for:
- Extracting face embeddings (512-dimensional feature vectors) from detected faces.
- Applying L2 unit normalization to embeddings for accurate cosine distance comparison.
- Saving embeddings as NumPy binary files (.npy).
- Loading saved embeddings from disk.
- Robust error handling for invalid face objects and corrupt files.
"""

import os
from typing import Any, Optional, Union
import numpy as np


class FaceEncoder:
    """Extracts, normalizes, and manages face feature embeddings."""

    @staticmethod
    def extract_embedding(face: Any, normalize: bool = True) -> np.ndarray:
        """Extract a 512-dimensional face embedding vector from an InsightFace face object.

        Args:
            face: InsightFace detected face object containing 'embedding' or 'normed_embedding'.
            normalize: Whether to apply L2 normalization to ensure unit length.

        Returns:
            np.ndarray: 1D float32 numpy array of length 512.

        Raises:
            ValueError: If the face object is None or contains no embedding.
        """
        if face is None:
            raise ValueError("Cannot extract embedding: face object is None.")

        # Check for normed_embedding or embedding attribute
        if hasattr(face, "normed_embedding") and face.normed_embedding is not None and normalize:
            embedding = np.array(face.normed_embedding, dtype=np.float32)
        elif hasattr(face, "embedding") and face.embedding is not None:
            embedding = np.array(face.embedding, dtype=np.float32)
            if normalize:
                norm = np.linalg.norm(embedding)
                if norm > 1e-7:
                    embedding = embedding / norm
                else:
                    raise ValueError("Embedding vector has near-zero L2 norm; extraction failed.")
        else:
            raise ValueError(
                "Face object does not contain an embedding. Ensure face recognition model (ArcFace/buffalo_l) is active."
            )

        # Flatten to 1D vector
        embedding = embedding.flatten().astype(np.float32)
        return embedding

    @staticmethod
    def save_embedding(embedding: np.ndarray, output_path: str) -> str:
        """Save a face embedding numpy array to a .npy file.

        Args:
            embedding: 1D numpy array representing the face embedding.
            output_path: Filepath where the .npy file will be saved.

        Returns:
            str: Resolved absolute filepath of the saved .npy file.

        Raises:
            ValueError: If embedding is invalid or empty.
            IOError: If saving to disk fails.
        """
        if embedding is None or embedding.size == 0:
            raise ValueError("Cannot save empty or None embedding array.")

        if not output_path.lower().endswith(".npy"):
            output_path = output_path + ".npy"

        abs_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        try:
            np.save(abs_path, embedding)
            print(f"[FaceEncoder] Saved embedding (shape: {embedding.shape}) to: {abs_path}")
            return abs_path
        except Exception as e:
            raise IOError(f"Failed to save embedding to '{abs_path}': {e}")

    @staticmethod
    def load_embedding(file_path: str) -> np.ndarray:
        """Load a saved face embedding from a .npy file.

        Args:
            file_path: Path to the .npy file.

        Returns:
            np.ndarray: Loaded 1D float32 embedding array.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not a valid numpy array.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Embedding file not found at: '{file_path}'")

        try:
            embedding = np.load(file_path)
            if not isinstance(embedding, np.ndarray) or embedding.size == 0:
                raise ValueError(f"File '{file_path}' did not contain a valid non-empty numpy array.")
            embedding = embedding.flatten().astype(np.float32)
            print(f"[FaceEncoder] Loaded embedding (shape: {embedding.shape}) from: {file_path}")
            return embedding
        except Exception as e:
            raise ValueError(f"Failed to load embedding from '{file_path}': {e}")
