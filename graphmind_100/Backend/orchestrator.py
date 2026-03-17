"""
GraphMind — Parallel Orchestrator v4.0
Improvements vs v3:
  - Retrieval timer starts AFTER intent classification so retrieval_time_ms
    is pure graph+vector time (satisfies §1.2E: exclude LLM generation time).
  - forget_stale_memories() called after retrieval to keep the graph healthy.
  - asyncio.gather for true parallel FAISS + Neo4j fetch (sub-100ms target).
  - Dynamic RRF weights based on intent profile (FACTUAL vs RELATIONAL).
"""

import time
import asyncio
from intent_classifier import get_agentic_intent
from retrieval.hybrid_ranker import HybridRanker
from vector_store.faiss_mgr import FAISSManager
from embeddings.embedder import Embedder
from graph_engine import GraphEngine

ranker = HybridRanker(k_rrf=60)

_graph_engine: GraphEngine = None

def _get_graph() -> GraphEngine:
    global _graph_engine
    if _graph_engine is None:
        _graph_engine = GraphEngine()
    return _graph_engine


async def handle_user_input(user_id: str, text: str) -> dict:
    """
    Main orchestration function.

    Intent classification runs FIRST (LLM call — not counted in retrieval_time_ms).
    Retrieval timer starts only after intent is known, measuring pure hybrid
    fetch time (FAISS + Neo4j + RRF) as required by §1.2E.

    Returns structured dict consumed by main.py /chat.
    """
    # ── Step 1: Intent classification (excluded from retrieval timer) ──────
    intent   = await get_agentic_intent(text)
    is_query = intent.get("is_query",  False)
    entities = intent.get("entities",  [])

    # ── Step 2: Pure retrieval (timer starts here) ─────────────────────────
    retrieval_start = time.perf_counter()
    evidence        = []

    if is_query:
        evidence = await _retrieval_logic(user_id, text, intent)

    retrieval_ms = round((time.perf_counter() - retrieval_start) * 1000, 2)

    # ── Step 3: Contradiction check (§1.7) ────────────────────────────────
    conflict_warning = ""
    if intent.get("potential_conflict") and entities:
        conflict_warning = _get_graph().check_contradictions(
            username=user_id, entities=entities
        )

    # ── Step 4: Reinforce retrieved memories (§1.7) ────────────────────────
    if evidence:
        retrieved_ids = [r.get("node_id", "") for r in evidence if r.get("node_id")]
        _get_graph().reinforce_memories(retrieved_ids)

    # ── Step 5: Soft-archive stale memories (§1.7 memory decay) ────────────
    _get_graph().forget_stale_memories(username=user_id)

    return {
        "intent_profile": intent,
        "evidence":       evidence,
        "retrieval_ms":   retrieval_ms,
        "conflict_alert": conflict_warning,
        "entities":       entities,
    }


async def _retrieval_logic(user_id: str, text: str, intent: dict) -> list:
    """
    Adaptive hybrid retrieval.
    FACTUAL  queries → w_v=0.7 (semantic similarity leads)
    RELATIONAL queries → w_g=0.7 (graph connectivity + decay leads)
    """
    profile = intent.get("query_profile", "FACTUAL")
    w_v = 0.7 if profile == "FACTUAL" else 0.3
    w_g = 1.0 - w_v

    embedder   = Embedder()
    faiss_tool = FAISSManager()
    entities   = intent.get("entities", [])

    query_vector = embedder.embed(text=text)

    # True parallel fetch — key to sub-100ms retrieval target
    v_hits, g_hits = await asyncio.gather(
        asyncio.to_thread(faiss_tool.search, user_id, query_vector, 15),
        asyncio.to_thread(_get_graph().search_by_entities, user_id, entities),
    )

    return ranker.rank(v_hits, g_hits, w_v=w_v, w_g=w_g)
