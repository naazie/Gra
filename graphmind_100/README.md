# 🧠 GraphMind v4.0 — Hybrid RAG Memory Engine

**WCE Hackathon 2026 · Problem Statement 1**
*MINDMAP + Hybrid RAG Assistant · Use Cases: Learning Path Planner + Interview Prep Memory*

---

## 🏗️ Architecture

```
User Input
    │
    ▼
Intent Classifier (Llama 3.1 via Ollama)           ← NOT counted in retrieval_time_ms
    │   Returns: is_memory, is_query, entities[],
    │            query_profile, potential_conflict
    │
    ├─── if is_memory ──► Ingestion Pipeline
    │                         │
    │                         ├─ MultiModalParser  (text / PDF / image OCR)
    │                         ├─ Chunker           (paragraph → sentence hierarchy)
    │                         ├─ Embedder          (all-mpnet-base-v2 → FAISS)
    │                         ├─ Gemini 2.5 Flash  (relation extraction → triples)
    │                         └─ GraphEngine       (Neo4j: User→Memory→Concept[user-scoped])
    │
    └─── if is_query ───► ┌─ retrieval_time_ms STARTS HERE ─────────────────┐
                          │  asyncio.gather (parallel fetch)                 │
                          │    ├─ FAISS vector search  (semantic similarity)  │
                          │    └─ Neo4j entity search  (graph traversal)      │
                          │              │                                    │
                          │              ▼                                    │
                          │    Hybrid RRF Ranker                              │
                          │    (FACTUAL → w_v=0.7 / RELATIONAL → w_g=0.7)   │
                          │    score = w_v*(1/(k+v_rank)) + w_g*(1/(k+g_rank))│
                          │    graph_score = centrality * decay_score         │
                          └────────────────────────────────────────────────── ┘
                                         │
                                         ▼
                               Answer Generator (Llama 3.1)
                               + retrieval_time_ms returned (pure retrieval only)
                               + llm_generation_time_ms returned separately
                               + memory_citations with full score breakdown
                               + Contradiction alert if conflict detected
                               + Cited nodes glow gold in 3D mindmap
```

---

## 🛠️ Tech Stack

| Layer         | Technology                                      |
|---------------|-------------------------------------------------|
| Graph DB      | Neo4j (User→Memory→Concept, user-scoped)        |
| Vector DB     | FAISS (IndexFlatIP, per-user isolation)         |
| SQL           | PostgreSQL (identity vault)                     |
| Embeddings    | sentence-transformers/all-mpnet-base-v2 (768d)  |
| Relation ext. | Gemini 2.5 Flash (structured JSON triples)      |
| LLM           | Llama 3.1 via local Ollama (100% private)       |
| Backend       | FastAPI + asyncio                               |
| Frontend      | React + Vite + Three.js (3D mindmap)            |

---

## 🚀 Setup

### 1. Infrastructure (Docker)
```bash
cd Backend
docker-compose up -d
# Starts: PostgreSQL on 5433, Neo4j on 7687/7474
```

### 2. Ollama + Llama 3.1
```bash
ollama serve           # in one terminal
ollama pull llama3.1   # one-time download (~4GB)
```

### 3. Backend
```bash
cd Backend
cp .env.example .env
# Edit .env: add your GEMINI_API_KEY (free at aistudio.google.com)
pip install -r Requirements.txt
python main.py
# Server at http://localhost:8000  ·  Docs at http://localhost:8000/docs
```

### 4. Frontend
```bash
cd Frontend
npm install
npm run dev
# App at http://localhost:5173
```

---

## 📡 API Endpoints

| Method | Endpoint                      | Description                                          |
|--------|-------------------------------|------------------------------------------------------|
| GET    | `/health`                     | Neo4j + Postgres + Ollama status (§1.8)             |
| POST   | `/register`                   | Create user (SQL + Neo4j)                            |
| POST   | `/login`                      | Authenticate user                                    |
| POST   | `/memory/ingest`              | Direct memory ingestion (§1.8 exact spec)            |
| POST   | `/memory`                     | Alias for `/memory/ingest`                           |
| POST   | `/chat`                       | Unified chat (intent → ingest OR retrieve)           |
| POST   | `/chat?stream=true`           | SSE streaming response (§1.7)                        |
| GET    | `/memory/mindmap?username=X`  | Mindmap data (§1.8 spec)                             |
| GET    | `/graph-visuals/{username}`   | Nodes + links for 3D mindmap                         |
| GET    | `/recall/{username}`          | Graph state + memory count                           |
| POST   | `/memory/forget/{username}`   | Trigger memory decay archival (§1.7)                 |

### POST `/memory/ingest` response
```json
{
  "success": true,
  "nodes_created": 3,
  "edges_created": 3,
  "preview": ["I want to learn React after mastering...", "..."],
  "execution_time_ms": 14230.5
}
```

### POST `/chat` response
```json
{
  "answer": "Based on your memories, you should start with JavaScript [1]...",
  "type": "query",
  "retrieval_time_ms": 47.3,
  "llm_generation_time_ms": 812.1,
  "total_time_ms": 859.4,
  "memory_citations": [
    {
      "node_id": "uuid-...",
      "title": "I want to learn React after mastering...",
      "snippet": "I want to learn React after mastering JavaScript first.",
      "relevance_score": 16.6667,
      "breakdown": {
        "vector_rank": 0,
        "graph_rank": 1,
        "cosine_sim": 0.8821,
        "graph_score": 0.4444,
        "w_vector": 0.7,
        "w_graph": 0.3
      }
    }
  ],
  "entities": ["React", "JavaScript"],
  "intent_profile": {
    "is_query": true,
    "query_profile": "RELATIONAL",
    "potential_conflict": false,
    "sentiment": "NEUTRAL"
  },
  "conflict_alert": ""
}
```

---

## 📊 Graph Data Model

```
(User) -[:REMEMBERS]-> (Memory {
    id, content, timestamp,
    confidence_score,
    graph_score,          ← normalised degree centrality
    decay_score,          ← e^(-λ * days_since_last_reinforced)
    usage_count,
    last_reinforced,
    archived              ← true if decay_score < FORGET_THRESHOLD
}) -[:MENTIONS]-> (Concept {
    name,
    user_id               ← USER-SCOPED: each user owns their own concept nodes
})

(Concept) -[:PREREQUISITE_OF]-> (Concept)
(Concept) -[:REQUIRES]--------->(Concept)
(Concept) -[:WEAK_IN]---------->(Concept)
(Concept) -[:STRONG_IN]--------> (Concept)
(Concept) -[:CONTRADICTS]------> (Concept)
(Concept) -[:TARGETS_COMPANY]--> (Concept)
(Concept) -[:ANSWERED]---------> (Concept)
(Concept) -[:ATTEMPTED]--------> (Concept)
```

### Sample Cypher Queries
```cypher
-- All memories for a user (excluding archived/decayed)
MATCH (u:User {username: "alice"})-[:REMEMBERS]->(m:Memory)
WHERE m.archived = false
RETURN m ORDER BY m.timestamp DESC LIMIT 10;

-- Prerequisite chain for a target skill
MATCH (a:Concept)-[:PREREQUISITE_OF*1..3]->(b:Concept {name: "React"})
WHERE a.user_id = "alice"
RETURN a.name, b.name;

-- Find weaknesses (for interview prep)
MATCH (u:User {username: "alice"})-[:REMEMBERS]->(m:Memory)
      -[:MENTIONS]->(c1:Concept)-[r:WEAK_IN]->(c2:Concept)
RETURN c1.name AS topic, c2.name AS weak_area, r.confidence;

-- Contradictions
MATCH (c1:Concept {user_id: "alice"})-[r:CONTRADICTS]->(c2:Concept)
RETURN c1.name, c2.name, r.confidence;

-- Top memories by combined score (centrality × recency)
MATCH (u:User {username: "alice"})-[:REMEMBERS]->(m:Memory)
RETURN m.content, m.graph_score, m.decay_score,
       m.graph_score * m.decay_score AS combined_score
ORDER BY combined_score DESC LIMIT 5;
```

---

## 🧮 Scoring Formula

```
graph_score   = degree(m) / max_degree         (structural importance)
decay_score   = e^(-λ × days_since_reinforced) (recency, λ=0.05 → half-life ≈14 days)
combined      = graph_score × decay_score       (fed to hybrid ranker)

RRF final score = w_v × (1/(k + vector_rank))
                + w_g × (1/(k + graph_rank))

FACTUAL query:    w_v=0.7, w_g=0.3
RELATIONAL query: w_v=0.3, w_g=0.7
```

---

## ✅ Requirements Checklist

| Requirement | Status | Notes |
|---|---|---|
| §1.2A User-scoped memory, strict isolation | ✅ | REMEMBERS ownership + user-scoped Concept nodes |
| §1.2B Ingestion pipeline with metadata | ✅ | timestamp, confidence, usage_count, last_reinforced |
| §1.2C Hybrid retrieval (graph + vector) | ✅ | True union RRF, asyncio.gather parallel fetch |
| §1.2D Answer generation with citations | ✅ | memory_citations with full score breakdown |
| §1.2E Retrieval time displayed (mandatory) | ✅ | Pure retrieval_time_ms, excludes intent LLM |
| §1.5 Frontend with mindmap | ✅ | React + Three.js 3D mindmap, cited nodes glow gold |
| §1.5 /health endpoint | ✅ | Neo4j + Postgres + Ollama |
| §1.6 Auditability (path, score, source) | ✅ | vector_rank, graph_rank, cosine_sim, graph_score per citation |
| §1.7 Sub-100ms retrieval target | ✅ | asyncio.gather, pure retrieval timer |
| §1.7 Memory decay / forgetting | ✅ | decay_score = e^(-λt), soft-archive below threshold |
| §1.7 Contradiction resolution | ✅ | CONTRADICTS edges, alert surfaced in API + UI |
| §1.7 Reinforcement learning of memory | ✅ | usage_count++ + last_reinforced reset on retrieval |
| §1.7 Hybrid ranker (graph + vector + recency) | ✅ | Dynamic RRF + decay-weighted graph score |
| §1.7 Streaming responses | ✅ | SSE via /chat?stream=true, meta event before first token |
| §1.7 Multi-modal memory | ✅ | PDF (PyMuPDF) + image OCR (Tesseract) |
| POST /memory/ingest (§1.8 spec) | ✅ | Exact spec endpoint + /memory alias |
| GET /memory/mindmap (§1.8 spec) | ✅ | Returns nodes[], edges[], metadata |
| Cited nodes highlighted in 3D graph | ✅ | Gold glow on cited node_ids after each query |
| No LangChain/LlamaIndex memory libs | ✅ | All memory logic built from scratch |
| API key not in repo | ✅ | .env.example uses placeholder only |

---

## 🔐 Security Note

Never commit your `.env` file. The `.env.example` contains only placeholder values.
Generate a fresh `SECRET_KEY` with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 👥 Team

- **Member A (Logic Lead)** — GraphEngine, contradiction resolution, time-decay, schema design
- **Member B (Search Specialist)** — HybridRanker (RRF + decay weights), FAISS, orchestrator
- **Member C (Integration Engineer)** — main.py, pipeline, multimodal, frontend, UI auditability
