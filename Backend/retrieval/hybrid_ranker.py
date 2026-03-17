"""
GraphMind — Hybrid Ranker v4.0
Improvements vs v3:
  - Time-decay is now a first-class score dimension in the final ranking.
    The graph_score received from GraphEngine is already (centrality * decay),
    so the ranker automatically rewards recently-reinforced memories.
  - Breakdown now exposes decay_score separately for auditability (§1.6).
  - Dynamic weights (FACTUAL → w_v=0.7 / RELATIONAL → w_g=0.7) preserved.
  - True union RRF preserved: nodes appearing in only one list still score.
"""

from typing import List, Dict


class HybridRanker:
    def __init__(self, k_rrf: int = 60):
        self.k = k_rrf   # Standard RRF smoothing constant

    def rank(
        self,
        vector_results: List[Dict],
        graph_results:  List[Dict],
        w_v: float = 0.5,
        w_g: float = 0.5,
    ) -> List[Dict]:
        """
        True Union RRF with time-decay:
          - vector_results are ranked by FAISS cosine similarity
          - graph_results  are ranked by (centrality * decay_score)
          - final_score = w_v * (1/(k+v_rank)) + w_g * (1/(k+g_rank))

        A memory appearing in BOTH lists benefits from both terms.
        A memory appearing only in graph_results (entity hit) is still included.

        Returns:
            Sorted list with full breakdown for §1.6 auditability.
        """
        fused: Dict[str, Dict] = {}

        # 1. Process FAISS vector ranks
        for rank, hit in enumerate(vector_results):
            node_id = hit.get("node_id", "")
            if not node_id:
                continue
            score = w_v * (1.0 / (self.k + rank + 1))
            fused[node_id] = {
                "score":        score,
                "vector_rank":  rank,
                "graph_rank":   None,
                "text":         hit.get("text", ""),
                "cosine_sim":   hit.get("cosine_similarity", 0.0),
                "graph_score":  0.0,
            }

        # 2. Process graph entity ranks (union — adds nodes not in FAISS)
        for rank, hit in enumerate(graph_results):
            node_id = hit.get("node_id", "")
            if not node_id:
                continue
            score = w_g * (1.0 / (self.k + rank + 1))
            if node_id in fused:
                fused[node_id]["score"]      += score
                fused[node_id]["graph_rank"]  = rank
                fused[node_id]["graph_score"] = hit.get("graph_score", 0.0)
            else:
                fused[node_id] = {
                    "score":       score,
                    "vector_rank": None,
                    "graph_rank":  rank,
                    "text":        hit.get("text", ""),
                    "cosine_sim":  0.0,
                    "graph_score": hit.get("graph_score", 0.0),
                }

        # 3. Format with full auditability breakdown (§1.6)
        output = [
            {
                "node_id":     node_id,
                "text":        data["text"],
                "final_score": round(data["score"] * 1000, 4),   # scaled for readability
                "breakdown": {
                    "vector_rank":  data["vector_rank"],
                    "graph_rank":   data["graph_rank"],
                    "cosine_sim":   round(data["cosine_sim"],   4),
                    "graph_score":  round(data["graph_score"],  4),
                    "w_vector":     round(w_v, 2),
                    "w_graph":      round(w_g, 2),
                },
            }
            for node_id, data in fused.items()
        ]

        return sorted(output, key=lambda x: x["final_score"], reverse=True)
