"""
GraphMind — Demo Data Seeder
=============================
Run this ONCE before your hackathon presentation:

    python seed_demo.py

Creates a demo user with 12 rich memories covering both use cases:
  - Learning Path Planner (§1.4 use case 3)
  - Interview Prep Memory (§1.4 use case 4)

After seeding, log in as:
  username: demo
  password: graphmind2026

The 3D mindmap will already show a fully connected brain with Memory nodes,
Concept nodes, PREREQUISITE_OF / WEAK_IN / STRONG_IN / TARGETS_COMPANY edges,
and decay scores. Cited nodes will glow gold on the first query.
"""

import requests
import time
import sys

BASE     = "http://localhost:8000"
USERNAME = "demo"
PASSWORD = "graphmind2026"

# ── 12 memories that produce rich graph edges via Gemini extraction ────────────
# Covering: learning path, interview prep, goals, strengths, weaknesses, company targeting

MEMORIES = [
    # Goal + target company
    "My goal is to become a backend software engineer at Google. "
    "I have a referral and my interview is scheduled in 8 weeks.",

    # Strong foundation
    "I am strong in Python and have 2 years of experience building REST APIs with FastAPI and Django. "
    "I understand HTTP, REST principles, and have deployed services on AWS.",

    # Known weakness - triggers WEAK_IN relation
    "I struggle with dynamic programming. I attempted the coin change problem last week "
    "and could not identify the subproblem structure. DP is my biggest weakness.",

    # Graph algorithms knowledge state
    "I know BFS and DFS well and can implement them from scratch. "
    "I am learning Dijkstra's algorithm and shortest path problems this week.",

    # Data structures strength
    "I am confident with arrays, linked lists, stacks, queues, and hash maps. "
    "Binary trees feel comfortable but I need more practice with balanced BSTs and AVL trees.",

    # System design gap - triggers PREREQUISITE_OF / REQUIRES relations
    "System design is a prerequisite for senior Google interviews. "
    "I need to study consistent hashing, load balancers, and database sharding. "
    "I have not built a distributed system before.",

    # Interview attempt - triggers ATTEMPTED / MISTAKE_ON relations
    "I did a mock Google interview last Tuesday. I failed the system design round. "
    "The question was to design a URL shortener. I forgot to address scalability and caching.",

    # Learning resource
    "I am using Neetcode 150 to practice LeetCode problems. "
    "I target 3 problems per day. Currently at 60 out of 150 completed.",

    # OS and networking - strong area
    "I studied operating systems: processes, threads, scheduling, and memory management. "
    "I am strong in networking fundamentals including TCP/IP, DNS, and HTTP/2.",

    # Contradiction memory - will trigger CONTRADICTS detection
    "I used to think I was weak at recursion, but after solving 15 recursive problems "
    "I now feel confident. Recursion is now a strength, not a weakness.",

    # This memory directly contradicts the DP weakness memory above
    # — reliably triggers CONTRADICTS edge and conflict_alert in demo
    "Update: I finally mastered dynamic programming after completing the DP sheet. "
    "Dynamic programming is now my strongest topic. I solved coin change, "
    "longest common subsequence, and knapsack correctly without hints.",

    # Specific prep goal
    "This week I must practice: designing a rate limiter, a notification system, "
    "and a distributed cache. These are common Google system design questions.",

    # Emotional/motivation memory
    "I feel confident about the coding rounds but anxious about the behavioural interview. "
    "I need to prepare STAR format stories for leadership, conflict resolution, and impact.",
]


def main():
    print("GraphMind Demo Seeder v5.0")
    print("=" * 50)
    print(f"Target: {BASE}")
    print(f"User:   {USERNAME}")
    print()

    # 1. Health check
    print("Checking backend health...")
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
        health = r.json()
        print(f"  Neo4j:    {health['services']['neo4j']['status']}")
        print(f"  Postgres: {health['services']['postgres']['status']}")
        print(f"  Ollama:   {health['services']['ollama']['status']}")
        if health["status"] != "healthy":
            print("\nWARNING: Some services are unhealthy. Continuing anyway...")
    except Exception as e:
        print(f"  Cannot reach backend: {e}")
        print("  Make sure 'python main.py' is running first.")
        sys.exit(1)

    print()

    # 2. Register user (ignore if already exists)
    print(f"Registering user '{USERNAME}'...")
    r = requests.post(f"{BASE}/register?username={USERNAME}&password={PASSWORD}")
    if r.status_code == 200:
        print(f"  User created in {r.json().get('execution_time_ms', '?')}ms")
    elif r.status_code == 400:
        print("  User already exists — continuing")
    else:
        print(f"  Unexpected response: {r.status_code} {r.text}")

    print()

    # 3. Ingest all memories
    print(f"Ingesting {len(MEMORIES)} memories (Gemini extracts relations from each)...")
    print("Note: 4s delay between chunks to respect Gemini free-tier rate limits.\n")

    total_nodes = 0
    for i, memory in enumerate(MEMORIES):
        print(f"[{i+1:2d}/{len(MEMORIES)}] {memory[:70]}...")
        try:
            r = requests.post(
                f"{BASE}/memory/ingest",
                params={"username": USERNAME, "text": memory},
                timeout=120,
            )
            if r.status_code == 200:
                data = r.json()
                nodes = data.get("nodes_created", 0)
                ms    = data.get("execution_time_ms", 0)
                total_nodes += nodes
                print(f"         {nodes} nodes — {ms:.0f}ms")
            else:
                print(f"         ERROR {r.status_code}: {r.text[:80]}")
        except Exception as e:
            print(f"         FAILED: {e}")

        # Rate-limit buffer between ingestions (not needed on last item)
        if i < len(MEMORIES) - 1:
            time.sleep(4)

    print()
    print("=" * 50)
    print(f"Seeding complete.")
    print(f"  Total memory nodes created: {total_nodes}")
    print()
    print("Demo login:")
    print(f"  Username: {USERNAME}")
    print(f"  Password: {PASSWORD}")
    print()
    print("Suggested demo queries:")
    print('  "What should I study this week to prepare for my Google interview?"')
    print('  "What are my weaknesses and how should I address them?"')
    print('  "Create a 8-week study plan for my Google interview"')
    print('  "What system design topics do I need to learn?"')
    print()
    print("Contradiction demo query (will trigger ⚠️ alert):")
    print('  "Tell me about my dynamic programming skills"')


if __name__ == "__main__":
    main()
