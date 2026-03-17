"""
GraphMind — Query Engine v4.0
Orchestrates: Embed → FAISS → Graph scores (centrality * decay) → RRF → Return context.
"""

from embeddings.embedder import Embedder
from vector_store.faiss_mgr import FAISSManager
from graph_engine import GraphEngine
from retrieval.hybrid_ranker import HybridRanker
from typing import List, Dict


class QueryEngine:
    def __init__(self, dimension: int = 768, ranker: HybridRanker = None):
        self.embedder     = Embedder()
        self.vector_store = FAISSManager(dimension=dimension)
        self.graph_engine = GraphEngine()
        self.ranker       = ranker or HybridRanker(k_rrf=60)

    def query(
        self,
        user_id: str,
        query_text: str,
        top_k: int = 5,
        w_v: float = 0.7,
        w_g: float = 0.3,
    ) -> List[Dict]:
        """
        §1.2C — Hybrid retrieval:
        1. Embed query
        2. FAISS vector search (semantic similarity)
        3. Fetch graph centrality * decay scores for retrieved nodes
        4. Hybrid RRF ranking with dynamic weights
        5. Reinforce retrieved memories (usage_count++, last_reinforced refresh)
        """
        query_vector = self.embedder.embed(query_text)

        vector_results = self.vector_store.search(
            user_id=user_id, query_vector=query_vector, top_k=top_k * 3
        )
        if not vector_results:
            return []

        memory_ids       = [r["node_id"] for r in vector_results]
        graph_scores_map = self.graph_engine.get_graph_scores_for_ids(memory_ids)

        graph_results = [
            {"node_id": nid, "text": "", "graph_score": score}
            for nid, score in sorted(graph_scores_map.items(), key=lambda x: x[1], reverse=True)
        ]

        ranked = self.ranker.rank(vector_results, graph_results, w_v=w_v, w_g=w_g)

        self.graph_engine.reinforce_memories([r["node_id"] for r in ranked[:top_k]])

        return ranked[:top_k]
