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
from neo4j import GraphDatabase
from typing import List, Dict
from dotenv import load_dotenv
import re

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

    def add_custom_relation(self, memory_id, subj, rel, obj, confidence=0.8, user_id=None):
        """Injects extracted semantic triples. Concept nodes are user-scoped."""    

        # Sanitize relationship type for Neo4j
        rel = (rel or "RELATED_TO").upper().strip()
        safe_rel = re.sub(r"[^A-Z0-9_]", "_", rel)  

        # Neo4j relationship types should not start with a digit
        if not safe_rel or safe_rel[0].isdigit():
            safe_rel = f"REL_{safe_rel}" if safe_rel else "RELATED_TO"  

        cypher = f"""
        MATCH (m:Memory {{id: $id}})
        MERGE (s:Concept {{name: $subj, user_id: $uid}})
        MERGE (o:Concept {{name: $obj, user_id: $uid}})
        MERGE (s)-[r:{safe_rel}]->(o)
        ON CREATE SET r.confidence = $conf, r.created_at = datetime()
        MERGE (m)-[:MENTIONS]->(s)
        MERGE (m)-[:MENTIONS]->(o)
        """ 

        try:
            with self.driver.session() as session:
                session.run(  # type: ignore[arg-type]
                    cypher,
                    id=memory_id,
                    subj=(subj or "Unknown").strip(),
                    obj=(obj or "Unknown").strip(),
                    conf=float(confidence),
                    uid=user_id,
                )
        except Exception as e:
            print(f"[graph_engine] add_custom_relation error: rel={rel}, safe_rel={safe_rel}, error={e}")
            raise
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
                "MATCH (m:Memory) RETURN m.id AS id, m.last_reinforced AS lr, m.usage_count AS rc"
            )]

        now = datetime.now(timezone.utc)
        updates = []
        for row in rows:
            lr = row.get("lr")
            rc = row.get("rc", 0) or 0
            try:
                lr_dt = datetime(lr.year, lr.month, lr.day,
                                 lr.hour, lr.minute, lr.second,
                                 tzinfo=timezone.utc) if lr else now
                days = max((now - lr_dt).total_seconds() / 86400.0, 0.0)
            except Exception:
                days = 0.0
            # Improved Ebbinghaus: reinforcement count slows decay
            # decay = e^(-λ * days / (1 + reinforcement_count * 0.3))
            effective_lambda = DECAY_LAMBDA / (1 + rc * 0.3)
            updates.append({"id": row["id"], "decay": round(math.exp(-effective_lambda * days), 6)})

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


    def get_graph_data_for_ids(self, memory_ids: List[str]) -> Dict[str, dict]:
        """
        Returns {memory_id: {score, content}} for the hybrid ranker.
        score   = graph_score * decay_score (combined signal)
        content = actual memory text (prevents blank citations from graph-only hits)
        """
        if not memory_ids:
            return {}
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (m:Memory) WHERE m.id IN $ids
                RETURN m.id          AS id,
                       m.graph_score AS graph_score,
                       m.decay_score AS decay_score,
                       m.content     AS content,
                       m.usage_count AS usage_count,
                       m.last_reinforced AS last_reinforced
                """,
                ids=memory_ids,
            )
            return {
                r["id"]: {
                    "score":          round((r["graph_score"] or 0.0) * (r["decay_score"] or 1.0), 6),
                    "content":        r["content"] or "",
                    "usage_count":    r["usage_count"] or 0,
                    "decay_score":    r["decay_score"] or 1.0,
                }
                for r in result
            }

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
            # result = session.run(
            #     """
            #     MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
            #     WHERE (m.archived IS NULL OR m.archived = false)
            #     OPTIONAL MATCH (m)-[r]-(c)
            #     WHERE c IS NULL OR NOT c:User
            #     RETURN m, collect({rel: r, node: c}) AS connections
            #     """,
            #     username=username,
            # )

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


    def add_confirms_edge(self, username: str, memory_id: str, concept_name: str):
        """
        Creates a CONFIRMS edge: Memory -[:CONFIRMS]-> Concept
        Called when user correctly answers a drill question about a concept.
        Used in readiness score calculation (confirmed = full credit).
        """
        try:
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (m:Memory {id: $mid})
                    MERGE (c:Concept {name: $concept, user_id: $uid})
                    MERGE (m)-[:CONFIRMS {confirmed_at: datetime()}]->(c)
                    """,
                    mid=memory_id, concept=concept_name.lower(), uid=username,
                )
        except Exception as e:
            print(f"[graph_engine] add_confirms_edge error: {e}")

    def add_derived_from_edge(self, username: str, memory_id: str, concept_name: str, confidence: float = 0.75):
        """
        Creates a DERIVED_FROM edge: Memory -[:DERIVED_FROM]-> Concept
        Called when system infers user knowledge that wasn't explicitly stated.
        E.g. user solved 3 hard DP problems → infer: comfortable with DP basics.
        """
        try:
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (m:Memory {id: $mid})
                    MERGE (c:Concept {name: $concept, user_id: $uid})
                    MERGE (m)-[:DERIVED_FROM {confidence: $conf, derived_at: datetime()}]->(c)
                    """,
                    mid=memory_id, concept=concept_name.lower(), uid=username, conf=confidence,
                )
        except Exception as e:
            print(f"[graph_engine] add_derived_from_edge error: {e}")

    def add_mistake_edge(self, username: str, memory_id: str, concept_name: str):
        """
        Creates a MISTAKE_IN edge: Memory -[:MISTAKE_IN]-> Concept
        Called when user gets a drill question wrong.
        Surfaced in next session: "last time you got this wrong..."
        """
        try:
            with self.driver.session() as session:
                session.run(
                    """
                    MATCH (m:Memory {id: $mid})
                    MERGE (c:Concept {name: $concept, user_id: $uid})
                    MERGE (m)-[:MISTAKE_IN {attempted_at: datetime()}]->(c)
                    """,
                    mid=memory_id, concept=concept_name.lower(), uid=username,
                )
        except Exception as e:
            print(f"[graph_engine] add_mistake_edge error: {e}")

    def get_past_mistakes(self, username: str, limit: int = 5) -> List[Dict]:
        """
        Returns recent MISTAKE_IN edges — used for continuity:
        'Last time you tried X and got stuck on Y.'
        """
        try:
            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                          -[:MISTAKE_IN]->(c:Concept)
                    RETURN c.name AS topic, m.content AS context,
                           m.timestamp AS when
                    ORDER BY m.timestamp DESC
                    LIMIT $limit
                    """,
                    username=username, limit=limit,
                )
                return [{"topic": r["topic"], "context": (r["context"] or "")[:60]} for r in result]
        except Exception:
            return []

    def get_improved_topics(self, username: str) -> List[str]:
        """
        Returns topics where user has BOTH MISTAKE_IN (past) and CONFIRMS (recent).
        These are genuine improvements worth celebrating.
        """
        try:
            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH (u:User {username: $username})-[:REMEMBERS]->(m1:Memory)
                          -[:MISTAKE_IN]->(c:Concept)
                    MATCH (u)-[:REMEMBERS]->(m2:Memory)-[:CONFIRMS]->(c)
                    WHERE m2.timestamp > m1.timestamp
                    RETURN DISTINCT c.name AS topic
                    LIMIT 5
                    """,
                    username=username,
                )
                return [r["topic"] for r in result]
        except Exception:
            return []

    def improve_contradiction_check(self, username: str, entities: List[str]) -> str:
        """
        Enhanced contradiction detection:
        1. CONTRADICTS edges in graph
        2. Content heuristic: same entity with weak AND strong markers
        3. Stated vs demonstrated contradiction: claimed strong but MISTAKE_IN edge exists
        """
        if not entities:
            return ""

        parts = []

        with self.driver.session() as session:
            # 1. Graph CONTRADICTS edges
            result = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                      -[:MENTIONS]->(c1:Concept {user_id: $username})
                MATCH (c1)-[r:CONTRADICTS]->(c2:Concept)
                WHERE c1.name IN $entities OR c2.name IN $entities
                RETURN c1.name AS a, c2.name AS b, r.confidence AS conf
                LIMIT 3
                """,
                username=username, entities=entities,
            )
            for r in result:
                conf = r["conf"]
                try:
                    conf = float(conf)
                except Exception:
                    conf = 0.8
                parts.append(f"'{r['a']}' contradicts '{r['b']}' (conf={conf:.2f})")

            # 2. Content heuristic
            r2 = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                WHERE ANY(e IN $entities WHERE toLower(m.content) CONTAINS toLower(e))
                RETURN m.content AS content
                ORDER BY m.timestamp DESC LIMIT 20
                """,
                username=username, entities=entities,
            )
            contents = [r["content"] or "" for r in r2]

        weak_markers   = ["weak", "struggle", "can't", "cannot", "failing", "confused"]
        strong_markers = ["strong", "confident", "mastered", "know well", "comfortable"]
        entity_weak    = set()
        entity_strong  = set()
        for c in contents:
            cl = c.lower()
            for e in entities:
                if e.lower() in cl:
                    if any(w in cl for w in weak_markers):   entity_weak.add(e)
                    if any(s in cl for s in strong_markers): entity_strong.add(e)

        for e in entity_weak & entity_strong:
            parts.append(f"'{e}' has conflicting strength assessments in your memories")

        # 3. Stated strong but has MISTAKE_IN
        try:
            with self.driver.session() as session:
                r3 = session.run(
                    """
                    MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                          -[:MISTAKE_IN]->(c:Concept)
                    WHERE c.name IN $entities
                    RETURN DISTINCT c.name AS topic
                    """,
                    username=username, entities=entities,
                )
                for r in r3:
                    if r["topic"] in entity_strong:
                        parts.append(
                            f"You said you're strong in '{r['topic']}' but had a mistake on a drill — worth revisiting"
                        )
        except Exception:
            pass

        if not parts:
            return ""
        return "Conflicting information: " + "; ".join(parts[:3])

    def close(self):
        self.driver.close()
