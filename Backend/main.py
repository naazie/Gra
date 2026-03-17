"""
GraphMind — Backend API v4.0
Improvements vs v3:
  - POST /memory/ingest added (exact §1.8 spec endpoint, aliases /memory)
  - retrieval_time_ms now reflects PURE retrieval time (intent classify excluded)
    because orchestrator.py starts its timer after get_agentic_intent() returns
  - GET /memory/forget/{username} — manually trigger memory decay/archival
  - Ghost/commented code removed throughout
"""

import os
import sys
import json
import time
import uuid
import logging
import requests

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text

current_dir  = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import database as db
import ollama
from graph_engine import GraphEngine
from orchestrator import handle_user_input, init_orchestrator
from ingestion.pipeline import IngestionPipeline
from retrieval.query_engine import QueryEngine
from retrieval.answer_generator import generate_answer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GraphMind: Hybrid RAG Memory Engine",
    description="User-centric long-term memory with Graph + Vector hybrid retrieval",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline     = IngestionPipeline()
graph        = GraphEngine()
init_orchestrator(graph)   # share single Neo4j connection with orchestrator
query_engine = QueryEngine()
db.init_db()


def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════════════════════
#  HEALTH  §1.8
# ══════════════════════════════════════════════════════════════════════════════

def _check_neo4j():
    try:
        with graph.driver.session() as s:
            s.run("RETURN 1")
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def _check_postgres():
    try:
        s = db.SessionLocal()
        try:
            s.execute(sql_text("SELECT 1"))
        finally:
            s.close()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def _check_ollama():
    try:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        r = requests.get(f"{base}/api/tags", timeout=5)
        r.raise_for_status()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/health")
async def health_check():
    """§1.8 — checks Neo4j, Postgres, Ollama."""
    neo4j    = _check_neo4j()
    postgres = _check_postgres()
    ollama_s = _check_ollama()
    overall  = "healthy" if all(
        s["status"] == "healthy" for s in [neo4j, postgres, ollama_s]
    ) else "degraded"
    return {
        "status": overall,
        "services": {"neo4j": neo4j, "postgres": postgres, "ollama": ollama_s},
    }


# ══════════════════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/register")
def register(username: str, password: str, session: Session = Depends(get_db)):
    t0 = time.time()
    if session.query(db.User).filter(db.User.username == username).first():
        raise HTTPException(status_code=400, detail="User already exists")
    session.add(db.User(username=username, password=db.get_password_hash(password)))
    session.commit()
    graph.add_user(username)
    return {"message": "User registered successfully", "execution_time_ms": round((time.time()-t0)*1000, 2)}


@app.post("/login")
def login(username: str, password: str, session: Session = Depends(get_db)):
    t0   = time.time()
    user = session.query(db.User).filter(db.User.username == username).first()
    if not user or not db.verify_password(password, str(user.password)):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Login successful", "username": username,
            "execution_time_ms": round((time.time()-t0)*1000, 2)}


# ══════════════════════════════════════════════════════════════════════════════
#  MEMORY INGESTION  §1.8 POST /memory/ingest  (also aliased at /memory)
# ══════════════════════════════════════════════════════════════════════════════

async def _do_ingest(username: str, text: str):
    t0 = time.time()
    graph.add_user(username)
    nodes = pipeline.ingest(user_id=username, raw_text=text)
    ms    = round((time.time() - t0) * 1000, 2)
    return {
        "success":        True,
        "nodes_created":  len(nodes),
        "edges_created":  sum(1 for n in nodes),   # at least 1 REMEMBERS per node
        "preview":        [str(n.get("text", ""))[:80] for n in nodes[:3]],
        "execution_time_ms": ms,
    }


@app.post("/memory/ingest")
async def ingest_memory_spec(username: str, text: str):
    """§1.8 exact spec endpoint: POST /memory/ingest"""
    try:
        return await _do_ingest(username, text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory")
async def ingest_memory(username: str, text: str):
    """Alias for /memory/ingest — kept for backward compatibility."""
    try:
        return await _do_ingest(username, text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT  §1.8 — unified endpoint with §1.7 streaming + §1.2E retrieval timer
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/chat")
async def chat(username: str, text: str, stream: bool = False):
    """
    Unified chat endpoint.
    retrieval_time_ms = pure graph+vector time (intent classification excluded).
    llm_generation_time_ms = Ollama answer synthesis time.
    Both are always returned separately (§1.2E mandatory).
    """
    t0 = time.time()

    try:
        result = await handle_user_input(user_id=username, text=text)

        intent_profile = result["intent_profile"]
        evidence       = result["evidence"]
        retrieval_ms   = result["retrieval_ms"]     # pure retrieval — no LLM overhead
        is_query       = intent_profile.get("is_query", False)
        entities       = result.get("entities", [])
        conflict_alert = result.get("conflict_alert", "")

        citations_payload = [
            {
                "node_id":         r.get("node_id", ""),
                "title":           r.get("text", "")[:60],
                "snippet":         r.get("text", "")[:120],
                "relevance_score": round(r.get("final_score", 0), 4),
                "breakdown":       r.get("breakdown", {}),
            }
            for r in evidence[:5]
        ]

        # ── Non-streaming path ──────────────────────────────────────────────
        if not stream or not is_query:
            llm_t0 = time.time()

            if is_query:
                if not evidence:
                    answer = "I don't have any memories related to that yet. Tell me more and I'll remember!"
                else:
                    answer = generate_answer(text, evidence)
            else:
                graph.add_user(username)
                pipeline.ingest(user_id=username, raw_text=text)
                answer = "Memory stored and linked to your knowledge graph."

            if conflict_alert:
                answer = f"⚠️ Conflict detected: {conflict_alert}\n\n{answer}"

            llm_ms   = round((time.time() - llm_t0) * 1000, 2)
            total_ms = round((time.time() - t0) * 1000, 2)

            return {
                "answer":                  answer,
                "type":                    "query" if is_query else "memory",
                "retrieval_time_ms":       retrieval_ms,
                "llm_generation_time_ms":  llm_ms,
                "total_time_ms":           total_ms,
                "memory_citations":        citations_payload,
                "entities":                entities,
                "intent_profile":          intent_profile,
                "conflict_alert":          conflict_alert,
            }

        # ── SSE Streaming path (§1.7 stretch) ──────────────────────────────
        context_str = "\n\n".join(
            [f"[Memory {i+1}] {item['text']}" for i, item in enumerate(evidence[:5])]
        )
        prompt = (
            "You are GRAPHMIND, a memory-grounded AI assistant.\n"
            "Answer ONLY using the provided memories. Cite them as [1], [2], etc.\n"
            "If nothing is relevant, say so clearly.\n\n"
            f"MEMORIES:\n{context_str}\n\nQUESTION: {text}\n\nANSWER:"
        )

        async def event_stream():
            # Send retrieval metadata first — UI shows "Retrieval: Xms" before first token
            meta = json.dumps({
                "type":           "meta",
                "retrieval_ms":   retrieval_ms,
                "entities":       entities,
                "citations":      citations_payload,
                "intent_profile": intent_profile,
            })
            yield f"data: {meta}\n\n"

            stream_t0 = time.time()
            try:
                _ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                resp = requests.post(
                    f"{_ollama_url}/api/generate",
                    json={"model": "llama3.1", "prompt": prompt, "stream": True,
                          "options": {"temperature": 0.15, "num_predict": 512}},
                    stream=True, timeout=180,
                )
                for line in resp.iter_lines():
                    if not line:
                        continue
                    decoded = line.decode("utf-8")
                    if not decoded.startswith("{"):
                        continue
                    try:
                        chunk = json.loads(decoded)
                        token = chunk.get("response", "")
                        done  = chunk.get("done", False)
                        if token:
                            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                        if done:
                            gen_ms   = round((time.time() - stream_t0) * 1000, 2)
                            total_ms = round((time.time() - t0) * 1000, 2)
                            yield f"data: {json.dumps({'type': 'done', 'retrieval_ms': retrieval_ms, 'generation_ms': gen_ms, 'total_ms': total_ms})}\n\n"
                            break
                    except Exception:
                        continue
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"[/chat] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  MINDMAP + GRAPH VISUALS  §1.8
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/memory/mindmap")
async def get_mindmap(username: str):
    """§1.8 spec endpoint: GET /memory/mindmap"""
    try:
        data = graph.get_visual_graph(username)
        return {
            "nodes":    data["nodes"],
            "edges":    data["links"],
            "metadata": {"username": username, "node_count": len(data["nodes"])},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph-visuals/{username}")
def get_graph_visuals(username: str):
    """Returns nodes + links for the 3D React mindmap."""
    try:
        return graph.get_visual_graph(username)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/recall/{username}")
async def recall_memories(username: str):
    """Graph state + memory count for the 3D brain UI."""
    try:
        visual_data  = graph.get_visual_graph(username)
        memory_count = len([n for n in visual_data["nodes"] if n["type"] == "Memory"])
        return {"memory_count": memory_count, "graph_data": visual_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  MEMORY DECAY / FORGETTING  §1.7 stretch
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/memory/forget/{username}")
async def trigger_forget(username: str):
    """
    §1.7 Memory decay — manually triggers soft-archival of stale memories.
    Also called automatically inside orchestrator after every query.
    """
    try:
        archived = graph.forget_stale_memories(username=username)
        graph.compute_graph_scores()
        return {
            "archived_count": archived,
            "message": f"{archived} stale memor{'y' if archived == 1 else 'ies'} archived.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════════
#  STATS  — live dashboard numbers for the topbar
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/stats/{username}")
async def get_stats(username: str):
    """Returns live stats for the dashboard topbar."""
    try:
        visual_data  = graph.get_visual_graph(username)
        memory_count = len([n for n in visual_data["nodes"] if n["type"] == "Memory"])
        concept_count = len([n for n in visual_data["nodes"] if n["type"] == "Concept"])
        edge_count    = len(visual_data["links"])
        return {
            "memory_count":  memory_count,
            "concept_count": concept_count,
            "edge_count":    edge_count,
            "node_count":    len(visual_data["nodes"]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
