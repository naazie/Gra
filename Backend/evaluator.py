"""
GraphMind — Retrieval Evaluator
Measures Top-1 accuracy and Top-K recall of the hybrid retrieval pipeline.

Usage:
  from evaluator import RetrievalEvaluator
  ev = RetrievalEvaluator(user_id="test_user")
  results = ev.evaluate(k=3)
  print(results)

test_cases format:
  [{"query": "...", "expected_node_id": "uuid..."}]
Populate test_cases by first ingesting known content and noting the returned node_ids.
"""

import os
import sys

_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from retrieval.query_engine import QueryEngine
from retrieval.hybrid_ranker import HybridRanker


class RetrievalEvaluator:
    def __init__(self, user_id: str, ranker: HybridRanker = None):
        self.engine  = QueryEngine(ranker=ranker)
        self.user_id = user_id

    def evaluate(self, test_cases: list, k: int = 3) -> dict:
        """
        Runs each test case through the query engine and computes:
          top1_accuracy — fraction where the expected node is the #1 result
          topk_recall   — fraction where the expected node appears in top-k
        """
        top1_correct = 0
        topk_correct = 0

        for case in test_cases:
            results      = self.engine.query(
                user_id=self.user_id,
                query_text=case["query"],
                top_k=k,
            )
            retrieved_ids = [r["node_id"] for r in results]
            expected      = case["expected_node_id"]

            if results and expected == retrieved_ids[0]:
                top1_correct += 1
            if expected in retrieved_ids:
                topk_correct += 1
            else:
                print(f"  MISS  query='{case['query']}'  expected='{expected}'")

        total = len(test_cases)
        if total == 0:
            return {"top1_accuracy": 0.0, "topk_recall": 0.0, "total": 0}

        return {
            "top1_accuracy": round(top1_correct / total, 4),
            "topk_recall":   round(topk_correct / total, 4),
            "total":         total,
        }
