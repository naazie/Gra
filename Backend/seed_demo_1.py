"""
GraphMind — Demo Seeder v13.0
==============================
Run ONCE before the hackathon demo:

    python seed_demo.py

What this builds:
  - A realistic user with 3 weeks of study history
  - Memory queue: 3-5 topics fading at different urgency levels
  - Progress radar: 8 topics with varied confidence (strong vs weak)
  - Contradiction arc: DP was weak, now partially improving
  - Heatmap: 9 of last 14 days active (written via task completion)

Demo credentials:
  Username : demo@graphmind.ai
  Password : demo123

Phase 1 — ingest 20 memories via API   (builds real graph edges via Ollama)
Phase 2 — patch Neo4j directly          (sets realistic decay, timestamps, edges)
Phase 3 — verify                         (prints exactly what each tab will show)
"""

import os, sys, time, math, uuid, datetime
import requests

BASE     = "http://localhost:8000"
USERNAME = "demo@graphmind.ai"
PASSWORD = "demo123"

try:
    from neo4j import GraphDatabase
    from dotenv import load_dotenv
    load_dotenv()
    NEO4J_URI  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USERNAME",  "neo4j")
    NEO4J_PASS = os.getenv("NEO4J_PASSWORD",  "password")
except ImportError:
    print("ERROR: neo4j or dotenv not installed.")
    print("Run: pip install neo4j python-dotenv")
    sys.exit(1)

def decay(days_ago, reinforcements=1):
    lam = 0.05 / (1 + reinforcements * 0.3)
    return round(math.exp(-lam * days_ago), 4)

# =============================================================================
# PHASE 1 — MEMORIES
# These go through the full pipeline: Ollama extracts entities/relations,
# writes MENTIONS/CONFIRMS/WEAK_IN/MISTAKE_IN edges automatically.
# =============================================================================

MEMORIES = [
    "My name is Arjun. I am targeting a Software Engineer role at Google. "
    "My interview is in 14 days. I have been preparing for 3 weeks.",

    "I am very confident with arrays and two pointers. "
    "I solved Two Sum, Three Sum, Container With Most Water, and Trapping Rain Water "
    "all without hints. Arrays is definitely my strongest topic.",

    "Binary search feels natural now. I can solve search on rotated arrays, "
    "find minimum in rotated array, and median of two sorted arrays correctly. "
    "Binary search is a strong area for me.",

    "Linked lists are comfortable. I implemented reverse linked list, merge two sorted lists, "
    "detect cycle, and find middle node all correctly in timed mock sessions.",

    "I understand recursion deeply. Fibonacci, tree traversals, merge sort — "
    "I can derive the recurrence relation and base case without help now.",

    "Trees are mostly solid. I can do level order traversal, max depth, "
    "lowest common ancestor, and BST validation. "
    "But AVL trees and red-black trees still confuse me.",

    "I studied BFS and DFS last week and got them working on LeetCode. "
    "I understand when to use BFS versus DFS for shortest path versus exhaustive search. "
    "But graph problems with complex state like word ladder still trip me up.",

    "Stacks and queues I know well. Valid parentheses, daily temperatures, "
    "monotonic stack problems — all solved without hints.",

    "Dynamic programming is my biggest gap. I attempted the coin change problem "
    "three times and could not identify the subproblem correctly. "
    "Longest increasing subsequence, edit distance — I get lost in the state definition. "
    "DP is critical for Google and I am worried about it.",

    "System design is weak. I have never designed a distributed system. "
    "I do not understand consistent hashing, database sharding, or how to handle "
    "ten million users at scale. The URL shortener design question in my mock interview "
    "went very badly because I forgot caching and load balancing completely.",

    "Backtracking problems confuse me. Permutations, subsets, N-Queens — "
    "I understand the concept but cannot translate it to clean code under pressure. "
    "Backtracking is a known weak area I need to fix.",

    "I feel reasonably confident about behavioral interviews. "
    "I have prepared STAR format answers for leadership, conflict resolution, and impact stories. "
    "Behavioral is not my main concern right now.",

    "Mock interview session one, two weeks ago: coding round I solved two medium "
    "problems on arrays correctly and got positive feedback on communication. "
    "System design round I failed to address scalability for the design question.",

    "Mock interview session two, one week ago: I was asked a dynamic programming "
    "problem on longest common subsequence. I could not solve it in forty five minutes. "
    "The interviewer had to give multiple hints. This confirmed DP is my biggest risk.",

    "Mock interview session three, yesterday: arrays and binary search round went well. "
    "I solved both problems optimally. Trees round was okay, solved level order "
    "traversal correctly but was slow on the balanced BST check.",

    "Update on graphs: after practicing eight graph problems this week including "
    "number of islands, clone graph, course schedule, and Pacific Atlantic water flow, "
    "I feel much more confident with graph traversal now. "
    "Graphs moved from weak to moderate for me.",

    "I completed the Neetcode DP playlist today and attempted five DP problems. "
    "I solved coin change and climbing stairs correctly without hints this time. "
    "Dynamic programming is still hard but I am noticeably improving now.",

    "This week my priority is: day one and two dynamic programming practice, "
    "day three and four system design fundamentals, day five backtracking, "
    "day six and seven full mock interview simulation. "
    "I need to complete this plan to be ready for Google in fourteen days.",

    "I am using Neetcode 150 as my primary resource. "
    "For system design I am reading the System Design Primer on GitHub. "
    "I watch Abdul Bari for algorithm explanations when I get stuck.",

    "I prefer studying in the morning for two hours before work. "
    "I learn best by implementing algorithms from scratch rather than reading solutions. "
    "My study style is active coding, not passive video watching.",
]

# =============================================================================
# PHASE 2 — NEO4J PATCHES
# =============================================================================

def patch_neo4j(driver, username):
    print("\n── Phase 2: Patching Neo4j ───────────────────────────────────────────")

    with driver.session() as s:

        # Step 1: Backdate timestamps so memories feel spread over 3 weeks
        print("  Backdating memory timestamps...")
        BACKDATE = [
            ("Arrays is definitely my strongest",       21),
            ("Binary search feels natural",             19),
            ("Linked lists are comfortable",            18),
            ("recursion deeply",                        17),
            ("Trees are mostly solid",                  15),
            ("studied BFS and DFS last week",            7),
            ("Stacks and queues I know well",           14),
            ("Dynamic programming is my biggest gap",   14),
            ("System design is weak",                   13),
            ("Backtracking problems confuse me",        10),
            ("behavioral interviews",                    9),
            ("Mock interview session one",              14),
            ("Mock interview session two",               7),
            ("Mock interview session three",             1),
            ("graphs: after practicing",                 3),
            ("completed the Neetcode DP playlist",       2),
            ("This week my priority",                    1),
            ("Neetcode 150 as my primary resource",     12),
            ("studying in the morning",                 11),
            ("targeting a Software Engineer",           21),
        ]
        for keyword, days_ago in BACKDATE:
            ts = (datetime.datetime.now() - datetime.timedelta(days=days_ago)).isoformat()
            s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                WHERE m.content CONTAINS $kw
                SET m.timestamp = $ts, m.last_reinforced = $ts
            """, un=username, kw=keyword[:38], ts=ts)

        # Step 2: Set decay_score, usage_count, graph_score, confidence_score
        print("  Setting decay scores and confidence levels...")
        # Format: (keyword, decay_score, usage_count, graph_score, confidence_score)
        # Memory queue shows topics where decay < 0.7 AND usage_count > 0
        # sorted by (graph_score * (1 - decay_score)) DESC = importance * urgency
        PATCHES = [
            # MEMORY QUEUE items (decay < 0.7)
            ("studied BFS and DFS last week",           0.22, 3, 0.85, 0.55),  # CRITICAL
            ("System design is weak",                   0.32, 3, 0.82, 0.35),  # CRITICAL
            ("Binary search feels natural",             0.38, 5, 0.80, 0.82),  # FADING
            ("Trees are mostly solid",                  0.48, 4, 0.75, 0.68),  # FADING
            ("Dynamic programming is my biggest gap",   0.52, 4, 0.88, 0.30),  # FADING
            ("Backtracking problems confuse me",        0.58, 2, 0.68, 0.32),  # FADING
            ("Stacks and queues I know well",           0.63, 3, 0.65, 0.78),  # borderline
            # FRESH items (decay >= 0.7, won't appear in memory queue)
            ("Linked lists are comfortable",            0.74, 6, 0.72, 0.74),
            ("Arrays is definitely my strongest",       0.88, 8, 0.90, 0.87),
            ("recursion deeply",                        0.83, 5, 0.70, 0.80),
            ("behavioral interviews",                   0.76, 3, 0.55, 0.72),
            ("graphs: after practicing",                0.91, 2, 0.74, 0.58),
            ("completed the Neetcode DP playlist",      0.95, 1, 0.70, 0.45),
        ]
        for kw, dec, usage, gscore, conf in PATCHES:
            s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                WHERE m.content CONTAINS $kw
                SET m.decay_score      = $dec,
                    m.usage_count      = $usage,
                    m.graph_score      = $gscore,
                    m.confidence_score = $conf
            """, un=username, kw=kw[:38], dec=dec,
                 usage=usage, gscore=gscore, conf=conf)

        # Step 3: CONFIRMS edges for strong topics
        print("  Creating CONFIRMS edges (strong topics)...")
        CONFIRMS = [
            ("Arrays is definitely",  "Arrays",        0.87, 8),
            ("Binary search feels",   "Binary Search", 0.82, 5),
            ("Linked lists are",      "Linked Lists",  0.74, 6),
            ("recursion deeply",      "Recursion",     0.80, 5),
            ("Stacks and queues",     "Stacks",        0.78, 3),
        ]
        for kw, concept, conf, uses in CONFIRMS:
            r = s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                WHERE m.content CONTAINS $kw
                RETURN m.id AS mid LIMIT 1
            """, un=username, kw=kw)
            row = r.single()
            if not row:
                continue
            s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory {id: $mid})
                MERGE (c:Concept {name: $concept})
                MERGE (m)-[:CONFIRMS {confirmed_at: datetime(), confidence: $conf}]->(c)
                SET m.confidence_score = $conf, m.usage_count = $uses
            """, un=username, mid=row["mid"], concept=concept, conf=conf, uses=uses)

        # Step 4: WEAK_IN edges for weak topics
        print("  Creating WEAK_IN edges (weak topics)...")
        WEAK = [
            ("Dynamic programming is my biggest",  "Dynamic Programming", 0.30),
            ("System design is weak",              "System Design",       0.35),
            ("Backtracking problems confuse me",   "Backtracking",        0.32),
            ("AVL trees and red-black trees",      "Advanced Trees",      0.42),
        ]
        for kw, concept, conf in WEAK:
            r = s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                WHERE m.content CONTAINS $kw
                RETURN m.id AS mid LIMIT 1
            """, un=username, kw=kw[:38])
            row = r.single()
            if not row:
                mid = str(uuid.uuid4())
                s.run("""
                    MATCH (u:User {username: $un})
                    CREATE (m:Memory {
                        id: $mid, content: $concept + ' is a weak area for me',
                        decay_score: 0.52, graph_score: 0.75,
                        confidence_score: $conf, usage_count: 2,
                        timestamp: datetime(), last_reinforced: datetime(),
                        archived: false
                    })
                    MERGE (u)-[:REMEMBERS]->(m)
                """, un=username, mid=mid, concept=concept, conf=conf)
                mid_val = mid
            else:
                mid_val = row["mid"]

            s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory {id: $mid})
                MERGE (c1:Concept {name: 'topic'})
                MERGE (c2:Concept {name: $concept})
                MERGE (m)-[:MENTIONS]->(c1)
                MERGE (c1)-[:WEAK_IN]->(c2)
                SET m.confidence_score = $conf
            """, un=username, mid=mid_val, concept=concept, conf=conf)

        # Step 5: MISTAKE_IN edges
        print("  Creating MISTAKE_IN edges...")
        MISTAKES = [
            ("Mock interview session two",  "Dynamic Programming", 0.28),
            ("Mock interview session one",  "System Design",       0.33),
            ("Backtracking problems",       "Backtracking",        0.30),
        ]
        for kw, concept, conf in MISTAKES:
            r = s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                WHERE m.content CONTAINS $kw
                RETURN m.id AS mid LIMIT 1
            """, un=username, kw=kw[:38])
            row = r.single()
            if not row:
                continue
            s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory {id: $mid})
                MERGE (c:Concept {name: $concept})
                MERGE (m)-[:MISTAKE_IN {attempted_at: datetime()}]->(c)
                SET m.confidence_score = $conf
            """, un=username, mid=row["mid"], concept=concept, conf=conf)

        # Step 6: Recent CONFIRMS for improving topics (shows ↑ trend)
        print("  Creating improvement arc (graphs + DP recovery)...")
        RECENT = [
            ("graphs: after practicing",       "Graphs",             0.58),
            ("completed the Neetcode DP",      "Dynamic Programming", 0.45),
        ]
        for kw, concept, conf in RECENT:
            r = s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                WHERE m.content CONTAINS $kw
                RETURN m.id AS mid LIMIT 1
            """, un=username, kw=kw[:35])
            row = r.single()
            if not row:
                continue
            s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory {id: $mid})
                MERGE (c:Concept {name: $concept})
                MERGE (m)-[:CONFIRMS {confirmed_at: datetime(), confidence: $conf}]->(c)
                SET m.confidence_score = $conf
            """, un=username, mid=row["mid"], concept=concept, conf=conf)

        # Step 7: Recompute graph scores
        print("  Recomputing graph scores...")
        s.run("""
            MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
            OPTIONAL MATCH (m)-[r]-()
            WITH m, count(r) AS degree
            WITH max(degree) AS maxD, collect({m: m, d: degree}) AS items
            UNWIND items AS item
            SET item.m.graph_score = CASE WHEN maxD = 0 THEN 0.1
                ELSE round(0.1 + 0.9 * toFloat(item.d) / maxD, 4) END
        """, un=username)

        # Override a few key graph scores for demo clarity
        high_importance = [
            ("Dynamic programming is my biggest", 0.88),
            ("System design is weak",             0.85),
            ("Arrays is definitely",              0.90),
            ("studied BFS and DFS",               0.82),
        ]
        for kw, gscore in high_importance:
            s.run("""
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                WHERE m.content CONTAINS $kw
                SET m.graph_score = $gs
            """, un=username, kw=kw[:35], gs=gscore)

        print("  ✓ All patches applied.")


# =============================================================================
# PHASE 3 — VERIFY
# =============================================================================

def verify(driver, username):
    print("\n── Phase 3: Verification — what each tab will show ───────────────────")

    with driver.session() as s:

        # Memory Queue
        r = s.run("""
            MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
            WHERE m.decay_score IS NOT NULL
              AND m.decay_score < 0.7
              AND m.usage_count > 0
            RETURN m.content AS content, m.decay_score AS decay, m.graph_score AS gs
            ORDER BY (m.graph_score * (1.0 - m.decay_score)) DESC
            LIMIT 6
        """, un=username)
        rows = list(r)
        print(f"\n  🧠 MEMORY tab — {len(rows)} topics in queue:")
        for row in rows:
            pct   = int((row["decay"] or 1.0) * 100)
            label = "CRITICAL" if pct < 30 else "FADING" if pct < 60 else "OK"
            urgency = round((row["gs"] or 0) * (1 - (row["decay"] or 1.0)), 3)
            print(f"     [{label:8}] {pct:3d}% fresh  urgency={urgency}  {row['content'][:50]}…")

        # Weak areas (for progress radar)
        r2 = s.run("""
            MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                  -[:MENTIONS]->(c1:Concept)-[:WEAK_IN]->(c2:Concept)
            RETURN DISTINCT c2.name AS topic, m.confidence_score AS conf
            ORDER BY m.confidence_score ASC LIMIT 6
        """, un=username)
        r3 = s.run("""
            MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                  -[:MISTAKE_IN]->(c:Concept)
            RETURN DISTINCT c.name AS topic, m.confidence_score AS conf
            ORDER BY m.confidence_score ASC LIMIT 4
        """, un=username)

        all_weak = {}
        for row in r2: all_weak[row["topic"]] = int((row["conf"] or 0.35) * 100)
        for row in r3:
            if row["topic"] not in all_weak:
                all_weak[row["topic"]] = int((row["conf"] or 0.30) * 100)

        print(f"\n  📈 PROGRESS radar — {len(all_weak)} topics:")
        for topic, conf in sorted(all_weak.items(), key=lambda x: x[1]):
            bar = "█" * (conf // 10) + "░" * (10 - conf // 10)
            print(f"     {bar}  {conf:3d}%  {topic}")

        # Confirmed strong
        r4 = s.run("""
            MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                  -[:CONFIRMS]->(c:Concept)
            RETURN DISTINCT c.name AS topic, m.confidence_score AS conf
            ORDER BY m.confidence_score DESC LIMIT 8
        """, un=username)
        confirmed = [(row["topic"], int((row["conf"] or 0.5) * 100)) for row in r4]
        print(f"\n  ✓  CONFIRMS (strong topics for radar):  {confirmed}")

        # Total
        r5 = s.run("MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory) RETURN count(m) AS n", un=username)
        print(f"\n  Total memories in graph: {r5.single()['n']}")


# =============================================================================
# AUTH
# =============================================================================

def get_token():
    r = requests.post(f"{BASE}/register",
        params={"username": USERNAME, "password": PASSWORD}, timeout=10)
    if r.status_code == 200:
        token = r.json().get("token", "")
        if token:
            print("  ✓ User created.")
            return token

    r = requests.post(f"{BASE}/login",
        params={"username": USERNAME, "password": PASSWORD}, timeout=10)
    if r.status_code == 200:
        token = r.json().get("token", "")
        if token:
            print("  ✓ Login successful.")
            return token

    print(f"  ✗ Auth failed: {r.status_code} {r.text[:100]}")
    sys.exit(1)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║   GraphMind Demo Seeder v13.0                    ║")
    print("╚══════════════════════════════════════════════════╝\n")

    print("Checking backend...")
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        h = r.json()
        for svc, info in h.get("services", {}).items():
            st = info.get("status", info) if isinstance(info, dict) else info
            icon = "✓" if any(x in str(st).lower() for x in ["ok","healthy","running"]) else "⚠"
            print(f"  {icon} {svc}: {st}")
        print()
    except Exception as e:
        print(f"  ✗ Backend unreachable: {e}\n  Start backend first: python main.py")
        sys.exit(1)

    print("Authenticating...")
    token   = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    print()

    # Phase 1
    print(f"── Phase 1: Ingesting {len(MEMORIES)} memories ──────────────────────────────")
    print("  4s delay between each for Ollama safety.\n")
    total = 0
    for i, mem in enumerate(MEMORIES):
        print(f"  [{i+1:2d}/{len(MEMORIES)}] {mem[:65].replace(chr(10),' ')}…")
        try:
            r = requests.post(f"{BASE}/memory/ingest",
                params={"text": mem}, headers=headers, timeout=120)
            if r.status_code == 200:
                d = r.json()
                n = d.get("nodes_created", 0)
                total += n
                tag = "duplicate — skipped" if d.get("duplicate") else f"+{n} nodes  {d.get('execution_time_ms',0):.0f}ms"
                print(f"           {tag}")
            elif r.status_code == 401:
                print("           ✗ 401 — re-run seeder."); sys.exit(1)
            else:
                print(f"           ✗ {r.status_code}: {r.text[:80]}")
        except Exception as e:
            print(f"           ✗ {e}")
        if i < len(MEMORIES) - 1:
            time.sleep(4)

    print(f"\n  ✓ {total} nodes created.\n")

    # Phase 2
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        driver.verify_connectivity()
    except Exception as e:
        print(f"✗ Neo4j direct connection failed: {e}")
        print("  Check NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD in .env")
        sys.exit(1)

    patch_neo4j(driver, USERNAME)
    verify(driver, USERNAME)
    driver.close()

    print("""
╔══════════════════════════════════════════════════════╗
║  Demo account ready!                                 ║
╠══════════════════════════════════════════════════════╣
║  Username : demo@graphmind.ai                        ║
║  Password : demo123                                  ║
╠══════════════════════════════════════════════════════╣
║  Intelligence Panel demo flow:                       ║
║  🎯 Today    — 14-day countdown, 3 missions          ║
║  🧠 Memory   — 5 fading topics (Critical → OK)       ║
║  📈 Progress — radar: Arrays 87%, DP 30%             ║
║  🗓 Plan     — set Google SWE → generate plan        ║
╠══════════════════════════════════════════════════════╣
║  Chat demo queries:                                  ║
║  1. "What should I study today for Google?"          ║
║  2. "What are my weakest areas right now?"           ║
║  3. "Explain dynamic programming to me"              ║
║  4. "Design a URL shortener"                         ║
║  5. "How much progress have I made on graphs?"       ║
╠══════════════════════════════════════════════════════╣
║  Contradiction demo (show ⚠ alert):                  ║
║  "How good am I at dynamic programming?"             ║
║  → WEAK_IN (14d ago) + CONFIRMS (2d ago) conflict   ║
╚══════════════════════════════════════════════════════╝
""")

if __name__ == "__main__":
    main()