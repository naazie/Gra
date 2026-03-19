"""
GraphMind — Query Engine v10.0

Fix vs v9: graph_results now carry actual Memory content text, not "".
When a node appears only in graph search (not FAISS), its text was empty
which caused blank citations and empty LLM prompts.
Fixed by fetching m.content alongside graph scores in get_graph_data_for_ids().
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
        query_vector = self.embedder.embed(query_text)

        vector_results = self.vector_store.search(
            user_id=user_id, query_vector=query_vector, top_k=top_k * 3
        )
        if not vector_results:
            return []

        memory_ids = [r["node_id"] for r in vector_results]

        # ── THE FIX: fetch content + score, not just score ─────────────────
        graph_data = self.graph_engine.get_graph_data_for_ids(memory_ids)

        graph_results = [
            {
                "node_id":    nid,
                "text":       data.get("content", ""),   # real content, not ""
                "graph_score": data.get("score", 0.0),
                "usage_count": data.get("usage_count", 0),
            }
            for nid, data in sorted(
                graph_data.items(), key=lambda x: x[1].get("score", 0), reverse=True
            )
        ]

        ranked = self.ranker.rank(vector_results, graph_results, w_v=w_v, w_g=w_g)

        # Attach usage_count to ranked results for human-readable citations
        for r in ranked:
            gd = graph_data.get(r["node_id"], {})
            r["usage_count"] = gd.get("usage_count", 0)

        self.graph_engine.reinforce_memories([r["node_id"] for r in ranked[:top_k]])

        return ranked[:top_k]
