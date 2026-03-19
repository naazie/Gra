"""
GraphMind — Embedder v9.0
Fix: device="cuda" → auto-detect GPU/CPU so it doesn't crash on CPU-only machines.
"""

import torch
from sentence_transformers import SentenceTransformer
import numpy as np


class Embedder:
    def __init__(self):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer("all-mpnet-base-v2", device=device)

    def embed(self, text):
        if isinstance(text, str):
            vector = self.model.encode(text, show_progress_bar=False)
            vector = np.array(vector).astype("float32")
            norm   = np.linalg.norm(vector)
            if norm != 0:
                vector = vector / norm
            return vector

        elif isinstance(text, list):
            vectors = self.model.encode(text, batch_size=32, show_progress_bar=False)
            vectors = np.array(vectors).astype("float32")
            norms   = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms[norms == 0] = 1
            return vectors / norms
