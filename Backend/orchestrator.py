"""
GraphMind — Parallel Orchestrator v7.0

Changes vs v5:
  - Single GraphEngine instance: orchestrator now accepts the graph engine
    injected from main.py via init_orchestrator(graph_engine). Eliminates
    the dual Neo4j bolt connection that existed when orchestrator created
    its own GraphEngine() separately from main.py's instance.
  - Contradiction check now runs on every query with entities (not just when
    Llama flags potential_conflict=True — that flag is too conservative for demo).
  - Embedder + FAISSManager remain lazy singletons (no change).
"""

import time
import asyncio
from intent_classifier import get_agentic_intent
from retrieval.hybrid_ranker import HybridRanker
from vector_store.faiss_mgr import FAISSManager
from embeddings.embedder import Embedder

ranker = HybridRanker(k_rrf=60)

# ── Singletons ────────────────────────────────────────────────────────────────
_embedder:    Embedder   = None
_faiss_tool:  FAISSManager = None
_graph_engine             = None   # injected by main.py via init_orchestrator()


def init_orchestrator(graph_engine_instance):
    """
    Called once at startup from main.py.
    Injects the shared GraphEngine so orchestrator and main.py
    use a single Neo4j bolt connection.
    """
    global _graph_engine
    _graph_engine = graph_engine_instance


def _get_graph():
    if _graph_engine is None:
        raise RuntimeError("Orchestrator not initialised. Call init_orchestrator() first.")
    return _graph_engine


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def _get_faiss() -> FAISSManager:
    global _faiss_tool
    if _faiss_tool is None:
        _faiss_tool = FAISSManager()
    return _faiss_tool


async def handle_user_input(user_id: str, text: str) -> dict:
    """
    Main orchestration function.

    Intent classification runs first (LLM call — NOT counted in retrieval_ms).
    Retrieval timer starts only after intent is known, measuring pure hybrid
    fetch time (FAISS + Neo4j + RRF) as required by §1.2E.
    """
    # Step 1: Intent classification (excluded from retrieval timer)
    intent   = await get_agentic_intent(text)
    is_query = intent.get("is_query",  False)
    entities = intent.get("entities",  [])

    # Step 2: Pure retrieval — timer starts here
    retrieval_start = time.perf_counter()
    evidence        = []

    if is_query:
        evidence = await _retrieval_logic(user_id, text, intent)

    retrieval_ms = round((time.perf_counter() - retrieval_start) * 1000, 2)

    # Step 3: Contradiction check — runs on every query with entities.
    # More reliable than relying on Llama's potential_conflict flag alone.
    conflict_warning = ""
    if entities:
        conflict_warning = _get_graph().check_contradictions(
            username=user_id, entities=entities
        )

    # Step 4: Reinforce retrieved memories (§1.7)
    if evidence:
        retrieved_ids = [r.get("node_id", "") for r in evidence if r.get("node_id")]
        _get_graph().reinforce_memories(retrieved_ids)

    # Step 5: Soft-archive stale memories (§1.7 memory decay)
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
    RELATIONAL queries → w_g=0.7 (graph + decay leads)
    asyncio.to_thread runs FAISS and Neo4j in true parallel.
    """
    profile = intent.get("query_profile", "FACTUAL")
    w_v = 0.7 if profile == "FACTUAL" else 0.3
    w_g = 1.0 - w_v

    entities     = intent.get("entities", [])
    query_vector = _get_embedder().embed(text=text)

    v_hits, g_hits = await asyncio.gather(
        asyncio.to_thread(_get_faiss().search,             user_id, query_vector, 15),
        asyncio.to_thread(_get_graph().search_by_entities, user_id, entities),
    )

    return ranker.rank(v_hits, g_hits, w_v=w_v, w_g=w_g)
