"""
GraphMind — FAISS Manager v4.0
Per-user index isolation using separate .index + _meta.json files.

Fix vs v3: remove_vector() now correctly rebuilds the index WITH the remaining
vectors by storing raw float32 arrays alongside metadata. Previously it reset
to an empty index, silently deleting all other user memories.
"""

import os
import json
import numpy as np
import faiss


class FAISSManager:
    def __init__(self, dimension: int = 768, base_path: str = "vector_store/data"):
        self.dimension = dimension
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        self.indices:  dict = {}
        self.metadata: dict = {}
        # Raw vector cache for correct rebuild during deletion
        self._vectors: dict = {}

    def _index_path(self, user_id: str) -> str:
        return os.path.join(self.base_path, f"user_{user_id}.index")

    def _meta_path(self, user_id: str) -> str:
        return os.path.join(self.base_path, f"user_{user_id}_meta.json")

    def _vec_path(self, user_id: str) -> str:
        return os.path.join(self.base_path, f"user_{user_id}_vecs.npy")

    def create_or_load_index(self, user_id: str):
        if user_id in self.indices:
            return self.indices[user_id]

        index_path = self._index_path(user_id)
        index = faiss.read_index(index_path) if os.path.exists(index_path) \
                else faiss.IndexFlatIP(self.dimension)
        self.indices[user_id] = index

        meta_path = self._meta_path(user_id)
        self.metadata[user_id] = json.load(open(meta_path)) \
            if os.path.exists(meta_path) else []

        vec_path = self._vec_path(user_id)
        self._vectors[user_id] = np.load(vec_path).tolist() \
            if os.path.exists(vec_path) else []

        return index

    def _save_index(self, user_id: str):
        faiss.write_index(self.indices[user_id], self._index_path(user_id))
        with open(self._meta_path(user_id), "w") as f:
            json.dump(self.metadata[user_id], f)
        np.save(self._vec_path(user_id), np.array(self._vectors[user_id], dtype=np.float32))

    def add_vector(self, user_id: str, node_id: str, vector, text: str):
        index  = self.create_or_load_index(user_id)
        vector = np.asarray(vector, dtype=np.float32)
        norm   = np.linalg.norm(vector)
        if norm != 0:
            vector = vector / norm
        if vector.ndim == 1:
            vector = vector.reshape(1, -1)

        index.add(vector)
        self.metadata[user_id].append({"node_id": node_id, "text": text})
        self._vectors[user_id].append(vector.flatten().tolist())
        self._save_index(user_id)

    def remove_vector(self, user_id: str, node_id: str):
        """
        Removes a vector by rebuilding the index without it.
        Correctly preserves all OTHER vectors using the _vectors cache.
        """
        if user_id not in self.indices:
            self.create_or_load_index(user_id)

        current_meta = self.metadata.get(user_id, [])
        current_vecs = self._vectors.get(user_id, [])

        # Find index position of the node to remove
        remove_pos = next(
            (i for i, m in enumerate(current_meta) if m["node_id"] == node_id), None
        )
        if remove_pos is None:
            print(f"[faiss] node_id {node_id} not found for user {user_id}")
            return

        new_meta = [m for i, m in enumerate(current_meta) if i != remove_pos]
        new_vecs = [v for i, v in enumerate(current_vecs) if i != remove_pos]

        # Rebuild the index with remaining vectors
        new_index = faiss.IndexFlatIP(self.dimension)
        if new_vecs:
            mat = np.array(new_vecs, dtype=np.float32)
            new_index.add(mat)

        self.indices[user_id]  = new_index
        self.metadata[user_id] = new_meta
        self._vectors[user_id] = new_vecs
        self._save_index(user_id)
        print(f"[faiss] {node_id} removed for user {user_id} ({len(new_meta)} remaining)")

    def search(self, user_id: str, query_vector, top_k: int = 5):
        if user_id not in self.indices:
            self.create_or_load_index(user_id)

        index = self.indices[user_id]
        if index.ntotal == 0:
            return []

        query_vector = np.asarray(query_vector, dtype=np.float32)
        norm = np.linalg.norm(query_vector)
        if norm != 0:
            query_vector = query_vector / norm
        query_vector = np.expand_dims(query_vector, axis=0)

        scores, idxs = index.search(query_vector, min(top_k, index.ntotal))
        results = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx == -1 or idx >= len(self.metadata[user_id]):
                continue
            entry = self.metadata[user_id][idx]
            results.append({
                "node_id":           entry["node_id"],
                "text":              entry["text"],
                "cosine_similarity": float(score),
            })
        return results
