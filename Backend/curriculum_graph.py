"""
GraphMind — Curriculum Graph v11.0

Pre-built, authoritative CS knowledge dependency graph.
Loaded ONCE into Neo4j at startup / seed time.

This makes prerequisite backtracking RELIABLE — the system knows
the actual dependency structure of CS topics, not inferred from
random text. When a user says "I want to study DP", the system
instantly knows: DP requires recursion, recursion requires functions
and base cases, etc. — from ground truth, not an LLM guess.

The LLM requirement lookup (Gemini) is STILL used for:
  - Topics not in the curriculum graph
  - Company-specific requirements
  - Unusual goals

This is the foundation that makes every other tutor feature reliable.
"""

# ── Curriculum node definitions ───────────────────────────────────────────────
# Format: {name, difficulty (1-5), category, description}

CURRICULUM_NODES = [
    # Fundamentals
    {"name": "variables and data types",    "difficulty": 1, "category": "fundamentals"},
    {"name": "control flow",               "difficulty": 1, "category": "fundamentals"},
    {"name": "functions",                  "difficulty": 1, "category": "fundamentals"},
    {"name": "recursion",                  "difficulty": 2, "category": "fundamentals"},
    {"name": "object oriented programming","difficulty": 2, "category": "fundamentals"},
    {"name": "time complexity",            "difficulty": 2, "category": "fundamentals"},
    {"name": "space complexity",           "difficulty": 2, "category": "fundamentals"},

    # Data Structures
    {"name": "arrays",                     "difficulty": 1, "category": "data_structures"},
    {"name": "strings",                    "difficulty": 1, "category": "data_structures"},
    {"name": "linked lists",               "difficulty": 2, "category": "data_structures"},
    {"name": "stacks",                     "difficulty": 2, "category": "data_structures"},
    {"name": "queues",                     "difficulty": 2, "category": "data_structures"},
    {"name": "hash tables",                "difficulty": 2, "category": "data_structures"},
    {"name": "trees",                      "difficulty": 3, "category": "data_structures"},
    {"name": "binary search trees",        "difficulty": 3, "category": "data_structures"},
    {"name": "heaps",                      "difficulty": 3, "category": "data_structures"},
    {"name": "graphs",                     "difficulty": 3, "category": "data_structures"},
    {"name": "tries",                      "difficulty": 4, "category": "data_structures"},
    {"name": "segment trees",              "difficulty": 5, "category": "data_structures"},

    # Algorithms
    {"name": "binary search",              "difficulty": 2, "category": "algorithms"},
    {"name": "two pointers",               "difficulty": 2, "category": "algorithms"},
    {"name": "sliding window",             "difficulty": 2, "category": "algorithms"},
    {"name": "sorting algorithms",         "difficulty": 2, "category": "algorithms"},
    {"name": "bfs",                        "difficulty": 3, "category": "algorithms"},
    {"name": "dfs",                        "difficulty": 3, "category": "algorithms"},
    {"name": "dynamic programming",        "difficulty": 4, "category": "algorithms"},
    {"name": "greedy algorithms",          "difficulty": 3, "category": "algorithms"},
    {"name": "backtracking",               "difficulty": 4, "category": "algorithms"},
    {"name": "divide and conquer",         "difficulty": 4, "category": "algorithms"},
    {"name": "graph algorithms",           "difficulty": 4, "category": "algorithms"},
    {"name": "bit manipulation",           "difficulty": 3, "category": "algorithms"},

    # System Design
    {"name": "networking basics",          "difficulty": 2, "category": "system_design"},
    {"name": "databases",                  "difficulty": 2, "category": "system_design"},
    {"name": "sql",                        "difficulty": 2, "category": "system_design"},
    {"name": "nosql",                      "difficulty": 3, "category": "system_design"},
    {"name": "rest apis",                  "difficulty": 2, "category": "system_design"},
    {"name": "caching",                    "difficulty": 3, "category": "system_design"},
    {"name": "load balancing",             "difficulty": 3, "category": "system_design"},
    {"name": "system design",              "difficulty": 4, "category": "system_design"},
    {"name": "distributed systems",        "difficulty": 5, "category": "system_design"},
    {"name": "microservices",              "difficulty": 4, "category": "system_design"},
    {"name": "message queues",             "difficulty": 4, "category": "system_design"},
]

# ── Prerequisite edges ─────────────────────────────────────────────────────────
# Format: (prerequisite, target, confidence)
# "You need to know X before studying Y"

CURRICULUM_EDGES = [
    # Fundamentals chain
    ("variables and data types", "control flow",    0.95),
    ("control flow",             "functions",       0.95),
    ("functions",                "recursion",       0.90),
    ("functions",                "object oriented programming", 0.85),
    ("time complexity",          "space complexity", 0.80),
    ("arrays",                   "time complexity", 0.85),

    # Data structures chain
    ("arrays",                   "strings",         0.70),
    ("arrays",                   "linked lists",    0.85),
    ("arrays",                   "binary search",   0.90),
    ("linked lists",             "stacks",          0.85),
    ("linked lists",             "queues",          0.85),
    ("arrays",                   "hash tables",     0.80),
    ("arrays",                   "two pointers",    0.85),
    ("arrays",                   "sliding window",  0.85),
    ("recursion",                "trees",           0.90),
    ("trees",                    "binary search trees", 0.90),
    ("binary search trees",      "heaps",           0.80),
    ("trees",                    "tries",           0.85),
    ("arrays",                   "graphs",          0.75),
    ("linked lists",             "graphs",          0.75),

    # Algorithm prerequisites
    ("arrays",                   "sorting algorithms", 0.85),
    ("graphs",                   "bfs",             0.95),
    ("graphs",                   "dfs",             0.95),
    ("bfs",                      "graph algorithms", 0.90),
    ("dfs",                      "graph algorithms", 0.90),
    ("recursion",                "dynamic programming", 0.90),
    ("arrays",                   "dynamic programming", 0.85),
    ("recursion",                "backtracking",    0.90),
    ("recursion",                "divide and conquer", 0.85),
    ("dynamic programming",      "greedy algorithms", 0.70),
    ("arrays",                   "bit manipulation", 0.75),
    ("binary search",            "divide and conquer", 0.80),

    # System design chain
    ("networking basics",        "rest apis",       0.85),
    ("rest apis",                "system design",   0.80),
    ("sql",                      "databases",       0.90),
    ("databases",                "system design",   0.85),
    ("nosql",                    "system design",   0.80),
    ("caching",                  "system design",   0.85),
    ("load balancing",           "system design",   0.85),
    ("system design",            "distributed systems", 0.90),
    ("system design",            "microservices",   0.85),
    ("message queues",           "distributed systems", 0.80),
]


def seed_curriculum(graph_engine, verbose: bool = True):
    """
    Load the curriculum graph into Neo4j.
    Safe to call multiple times — uses MERGE so no duplicates.
    """
    if verbose:
        print(f"[curriculum] Seeding {len(CURRICULUM_NODES)} topics and {len(CURRICULUM_EDGES)} edges...")

    with graph_engine.driver.session() as session:
        # Create curriculum topic nodes
        for node in CURRICULUM_NODES:
            session.run(
                """
                MERGE (c:CurriculumTopic {name: $name})
                SET c.difficulty = $difficulty,
                    c.category   = $category,
                    c.is_curriculum = true
                """,
                name=node["name"],
                difficulty=node["difficulty"],
                category=node["category"],
            )

        # Create prerequisite edges between curriculum topics
        for prereq, target, confidence in CURRICULUM_EDGES:
            session.run(
                """
                MATCH (p:CurriculumTopic {name: $prereq})
                MATCH (t:CurriculumTopic {name: $target})
                MERGE (p)-[r:PREREQUISITE_OF]->(t)
                SET r.confidence = $conf,
                    r.source     = 'curriculum'
                """,
                prereq=prereq, target=target, conf=confidence,
            )

    if verbose:
        print(f"[curriculum] Done. Curriculum graph loaded.")


def get_curriculum_prerequisites(graph_engine, topic: str, depth: int = 3) -> list:
    """
    Given a topic name, returns ordered list of prerequisites from the curriculum graph.
    Returns [] if topic not found in curriculum.
    """
    topic_lower = topic.lower().strip()
    try:
        with graph_engine.driver.session() as session:
            result = session.run(
                f"""
                MATCH path = (p:CurriculumTopic)-[:PREREQUISITE_OF*1..{depth}]->
                             (t:CurriculumTopic)
                WHERE toLower(t.name) CONTAINS $topic
                   OR $topic CONTAINS toLower(t.name)
                RETURN p.name AS prereq, p.difficulty AS diff, length(path) AS level
                ORDER BY level ASC, diff ASC
                LIMIT 15
                """,
                topic=topic_lower,
            )
            return [{"topic": r["prereq"], "difficulty": r["diff"], "level": r["level"]}
                    for r in result]
    except Exception as e:
        print(f"[curriculum] Query error: {e}")
        return []


def get_topic_difficulty(graph_engine, topic: str) -> int:
    """Returns difficulty level 1-5 for a topic, or 3 (medium) if unknown."""
    try:
        with graph_engine.driver.session() as session:
            result = session.run(
                """
                MATCH (c:CurriculumTopic)
                WHERE toLower(c.name) CONTAINS $topic
                RETURN c.difficulty AS diff LIMIT 1
                """,
                topic=topic.lower(),
            )
            row = result.single()
            return int(row["diff"]) if row else 3
    except Exception:
        return 3


def get_all_topics_in_category(graph_engine, category: str) -> list:
    """Returns all curriculum topics in a category (e.g. 'algorithms')."""
    try:
        with graph_engine.driver.session() as session:
            result = session.run(
                """
                MATCH (c:CurriculumTopic {category: $category})
                RETURN c.name AS name, c.difficulty AS difficulty
                ORDER BY c.difficulty ASC
                """,
                category=category,
            )
            return [{"name": r["name"], "difficulty": r["difficulty"]} for r in result]
    except Exception:
        return []
