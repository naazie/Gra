from sentence_transformers import SentenceTransformer
import numpy as np


class Embedder:
    def __init__(self):
        # self.model = SentenceTransformer("all-mpnet-base-v2")
        self.model = SentenceTransformer("all-mpnet-base-v2", device="cuda")


    def embed(self, text: str):
        vector = self.model.encode(text)

        # Normalize for cosine similarity
        vector = np.array(vector).astype("float32")
        norm = np.linalg.norm(vector)

        if norm != 0:
            vector = vector / norm

        return vector