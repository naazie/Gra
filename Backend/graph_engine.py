"""
GraphMind — GraphEngine v4.0
Improvements vs v3:
  - Concept nodes are now USER-SCOPED: MERGE (c:Concept {name, user_id})
    → eliminates the cross-user concept leak present in v3
  - Time-decay scoring: decay_score = e^(-lambda * days_since_last_reinforced)
    stored on every Memory node and used by the hybrid ranker
  - Memory forgetting: forget_stale_memories() archives memories whose
    decay_score drops below FORGET_THRESHOLD (soft-delete preserves auditability)
  - get_visual_graph() exposes decay_score so the frontend can colour-code
    fresh vs stale memories in the 3D mindmap
"""

import os
import math
import random
from datetime import datetime, timezone
from neo4j import GraphDatabase, Query
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

DECAY_LAMBDA      = float(os.getenv("DECAY_LAMBDA",      "0.05"))   # per-day decay rate
FORGET_THRESHOLD  = float(os.getenv("FORGET_THRESHOLD",  "0.05"))   # archive if below this


class GraphEngine:
    def __init__(self):
        uri      = os.getenv("NEO4J_URI",      "bolt://127.0.0.1:7687")
        user     = os.getenv("NEO4J_USER",     "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "graphpassword123")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._init_schema()

    def _init_schema(self):
        with self.driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User)   REQUIRE u.username IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE")
            # Composite node key: same concept name can exist per user independently
            # IS NODE KEY is the correct Neo4j 5.x syntax for composite constraints
            session.run(
                "CREATE INDEX IF NOT EXISTS FOR (c:Concept) ON (c.name, c.user_id)"
            )
            session.run("CREATE INDEX IF NOT EXISTS FOR (m:Memory) ON (m.graph_score)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (m:Memory) ON (m.decay_score)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (m:Memory) ON (m.last_reinforced)")

    def add_user(self, username: str):
        with self.driver.session() as session:
            session.run("MERGE (u:User {username: $username})", username=username)

    # ── Memory Storage ────────────────────────────────────────────────────────

    def store_memory(
        self,
        username: str,
        memory_id: str,
        content: str,
        concepts: List[str],
        confidence_score: float = 1.0,
    ):
        """§1.2A/B — Memory node with metadata. Concepts are user-scoped."""
        with self.driver.session() as session:
            session.run(
                """
                MERGE (m:Memory {id: $id})
                SET m.content          = $content,
                    m.timestamp        = datetime(),
                    m.confidence_score = $conf,
                    m.graph_score      = 0.0,
                    m.decay_score      = 1.0,
                    m.usage_count      = 0,
                    m.last_reinforced  = datetime(),
                    m.archived         = false
                """,
                id=memory_id, content=content, conf=confidence_score,
            )
            session.run(
                """
                MATCH (u:User {username: $un}), (m:Memory {id: $id})
                MERGE (u)-[:REMEMBERS]->(m)
                """,
                un=username, id=memory_id,
            )
            if concepts:
                session.run(
                    """
                    MATCH (m:Memory {id: $id})
                    UNWIND $concepts AS c_name
                    MERGE (c:Concept {name: c_name, user_id: $uid})
                    MERGE (m)-[:MENTIONS]->(c)
                    """,
                    id=memory_id, concepts=concepts, uid=username,
                )

    def add_custom_relation(
        self,
        memory_id: str,
        subj: str,
        rel: str,
        obj: str,
        confidence: float = 0.8,
        user_id: str = "unknown",
    ):
        """Injects Gemini-extracted semantic triples. Concept nodes are user-scoped."""
        safe_rel = rel.upper().replace(" ", "_").replace("-", "_")
        with self.driver.session() as session:
            cypher = Query(
                f"""
                MATCH (m:Memory {{id: $id}})
                MERGE (s:Concept {{name: $subj, user_id: $uid}})
                MERGE (o:Concept {{name: $obj,  user_id: $uid}})
                MERGE (s)-[r:{safe_rel} {{confidence: $conf, created_at: datetime()}}]->(o)
                MERGE (m)-[:MENTIONS]->(s)
                MERGE (m)-[:MENTIONS]->(o)
                """
            )
            session.run(cypher, id=memory_id, subj=subj, obj=obj, conf=confidence, uid=user_id)

    # ── Reinforcement (§1.7) ──────────────────────────────────────────────────

    def reinforce_memories(self, memory_ids: List[str]):
        """Boosts usage_count and resets last_reinforced — slows decay for hot memories."""
        if not memory_ids:
            return
        with self.driver.session() as session:
            session.run(
                """
                MATCH (m:Memory) WHERE m.id IN $ids
                SET m.usage_count     = m.usage_count + 1,
                    m.last_reinforced = datetime()
                """,
                ids=memory_ids,
            )

    # ── Centrality + Time-Decay Scoring ──────────────────────────────────────

    def compute_graph_scores(self):
        """
        Recalculates two scores stored on every Memory node:
          graph_score = normalised degree centrality (structural importance)
          decay_score = e^(-DECAY_LAMBDA * days_since_last_reinforced)  (recency)

        The hybrid ranker multiplies these: combined = graph_score * decay_score
        so well-connected AND recently-used memories rank highest.
        """
        with self.driver.session() as session:
            session.run(
                """
                MATCH (m:Memory)-[r]->()
                WITH m, count(r) AS degree
                WITH max(degree) AS maxD
                MATCH (m:Memory)-[r]->()
                WITH m, count(r) AS degree, maxD
                SET m.graph_score = CASE WHEN maxD = 0 THEN 0.0
                                         ELSE toFloat(degree) / maxD END
                """
            )
            rows = [dict(r) for r in session.run(
                "MATCH (m:Memory) RETURN m.id AS id, m.last_reinforced AS lr"
            )]

        now = datetime.now(timezone.utc)
        updates = []
        for row in rows:
            lr = row.get("lr")
            try:
                lr_dt = datetime(lr.year, lr.month, lr.day,
                                 lr.hour, lr.minute, lr.second,
                                 tzinfo=timezone.utc) if lr else now
                days = max((now - lr_dt).total_seconds() / 86400.0, 0.0)
            except Exception:
                days = 0.0
            updates.append({"id": row["id"], "decay": round(math.exp(-DECAY_LAMBDA * days), 6)})

        if updates:
            with self.driver.session() as session:
                session.run(
                    """
                    UNWIND $updates AS u
                    MATCH (m:Memory {id: u.id})
                    SET m.decay_score = u.decay
                    """,
                    updates=updates,
                )

    def get_graph_scores_for_ids(self, memory_ids: List[str]) -> Dict[str, float]:
        """
        Returns {memory_id: combined_score} where
          combined_score = graph_score * decay_score
        Used by the hybrid ranker to weight structural importance by recency.
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (m:Memory) WHERE m.id IN $ids
                RETURN m.id          AS id,
                       m.graph_score AS graph_score,
                       m.decay_score AS decay_score
                """,
                ids=memory_ids,
            )
            return {
                r["id"]: round((r["graph_score"] or 0.0) * (r["decay_score"] or 1.0), 6)
                for r in result
            }

    # ── Memory Decay / Forgetting (§1.7 stretch) ─────────────────────────────

    def forget_stale_memories(self, username: str) -> int:
        """
        §1.7 Memory forgetting — soft-archives memories whose decay_score has
        fallen below FORGET_THRESHOLD.  Archived memories are excluded from
        retrieval but kept in Neo4j for auditability / manual review.
        Returns the number of newly archived memories.
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                WHERE m.decay_score IS NOT NULL
                  AND m.decay_score < $threshold
                  AND m.archived = false
                SET m.archived = true
                RETURN count(m) AS archived_count
                """,
                username=username,
                threshold=FORGET_THRESHOLD,
            )
            row = result.single()
            return int(row["archived_count"]) if row else 0

    # ── Graph-side Entity Retrieval ───────────────────────────────────────────

    def search_by_entities(self, username: str, entities: List[str]) -> List[Dict]:
        """§1.2C — graph entity search. Filters by user_id on Concept, excludes archived."""
        if not entities:
            return []
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                WHERE (m.archived IS NULL OR m.archived = false)
                MATCH (m)-[:MENTIONS]->(c:Concept {user_id: $username})
                WHERE c.name IN $entities
                RETURN DISTINCT
                    m.id          AS node_id,
                    m.content     AS text,
                    m.graph_score AS graph_score,
                    m.decay_score AS decay_score
                ORDER BY m.graph_score DESC
                LIMIT 15
                """,
                username=username, entities=entities,
            )
            return [dict(r) for r in result]

    # ── Contradiction Resolution (§1.7) ──────────────────────────────────────

    def check_contradictions(self, username: str, entities: List[str]) -> str:
        if not entities:
            return ""
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                      -[:MENTIONS]->(c1:Concept {user_id: $username})
                MATCH (c1)-[r:CONTRADICTS]->(c2:Concept)
                WHERE c1.name IN $entities OR c2.name IN $entities
                RETURN c1.name AS concept_a, c2.name AS concept_b, r.confidence AS conf
                LIMIT 5
                """,
                username=username, entities=entities,
            )
            rows = [r.data() for r in result]
            if not rows:
                return ""
            return "Conflicting memories found: " + "; ".join(
                f"'{r['concept_a']}' contradicts '{r['concept_b']}' (conf={r['conf']:.2f})"
                for r in rows
            )

    # ── Deletion ─────────────────────────────────────────────────────────────

    def delete_memory(self, username: str, memory_id: str):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory {id: $id})
                DETACH DELETE m
                """,
                username=username, id=memory_id,
            )
        self.compute_graph_scores()

    # ── Frontend Visual Graph ─────────────────────────────────────────────────

    def get_visual_graph(self, username: str) -> Dict:
        """
        Returns {nodes, links} for the React 3D mindmap.
        decay_score is included in node metadata so the frontend can
        colour fresh memories brightly and dim stale ones.
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                WHERE (m.archived IS NULL OR m.archived = false)
                OPTIONAL MATCH (m)-[r]-(c)
                WHERE c IS NULL OR NOT c:User
                RETURN m, collect({rel: r, node: c}) AS connections
                """,
                username=username,
            )

            nodes: Dict[str, Dict] = {}
            links: List[Dict]      = []

            def rnd():
                return [random.uniform(-5, 5), random.uniform(-5, 5), random.uniform(-5, 5)]

            for record in result:
                m           = record["m"]
                connections = record["connections"]
                m_id        = m.element_id

                if m_id not in nodes:
                    nodes[m_id] = {
                        "id":    m_id,
                        "label": (m.get("content") or "Memory")[:40],
                        "type":  "Memory",
                        "metadata": {
                            "uuid":             m.get("id"),
                            "graph_score":      m.get("graph_score"),
                            "decay_score":      round(m.get("decay_score") or 1.0, 4),
                            "confidence_score": m.get("confidence_score"),
                            "usage_count":      m.get("usage_count", 0),
                            "timestamp":        str(m.get("timestamp", "")),
                        },
                        "position": rnd(),
                    }

                for item in connections:
                    c = item["node"]
                    r = item["rel"]
                    if c is None or r is None:
                        continue
                    c_id = c.element_id
                    if c_id not in nodes:
                        nodes[c_id] = {
                            "id":       c_id,
                            "label":    c.get("name") or "Concept",
                            "type":     list(c.labels)[0] if c.labels else "Node",
                            "metadata": {},
                            "position": rnd(),
                        }
                    links.append({"source": m_id, "target": c_id, "label": r.type})

            return {"nodes": list(nodes.values()), "links": links}

    def close(self):
        self.driver.close()
