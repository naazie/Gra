"""
GraphMind — Demo Data Seeder v11.0
====================================
Run this ONCE before your hackathon presentation:

    python seed_demo.py

Seeds memories for:
  username: huma1@test.com
  password: 0000

v11 change: /memory/ingest requires a JWT Bearer token, not a username
query param. This seeder registers (or logs in) first, captures the
token, then passes it in every request.
"""

import requests
import time
import sys

BASE     = "http://localhost:8000"
USERNAME = "huma1@test.com"
PASSWORD = "0000"

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

    # Interview attempt - triggers ATTEMPTED / MISTAKE_IN relations
    "I did a mock Google interview last Tuesday. I failed the system design round. "
    "The question was to design a URL shortener. I forgot to address scalability and caching.",

    # Learning resource
    "I am using Neetcode 150 to practice LeetCode problems. "
    "I target 3 problems per day. Currently at 60 out of 150 completed.",

    # OS and networking - strong area
    "I studied operating systems: processes, threads, scheduling, and memory management. "
    "I am strong in networking fundamentals including TCP/IP, DNS, and HTTP/2.",

    # Contradiction memory - triggers CONTRADICTS detection
    "I used to think I was weak at recursion, but after solving 15 recursive problems "
    "I now feel confident. Recursion is now a strength, not a weakness.",

    # Contradicts the DP weakness memory - triggers conflict_alert in demo
    "Update: I finally mastered dynamic programming after completing the DP sheet. "
    "Dynamic programming is now my strongest topic. I solved coin change, "
    "longest common subsequence, and knapsack correctly without hints.",

    # Specific prep goal
    "This week I must practice: designing a rate limiter, a notification system, "
    "and a distributed cache. These are common Google system design questions.",

    # Behavioural prep
    "I feel confident about the coding rounds but anxious about the behavioural interview. "
    "I need to prepare STAR format stories for leadership, conflict resolution, and impact.",
]


def get_token() -> str:
    """Register or login and return the JWT token."""

    # Try registering first
    r = requests.post(
        f"{BASE}/register",
        params={"username": USERNAME, "password": PASSWORD},
        timeout=10,
    )
    if r.status_code == 200:
        token = r.json().get("token", "")
        if token:
            print(f"  User created — token obtained.")
            return token

    if r.status_code == 400 and "already exists" in r.text:
        print("  User already exists — logging in...")
    else:
        print(f"  Register response {r.status_code}: {r.text[:120]}")
        print("  Trying login anyway...")

    # Login
    r = requests.post(
        f"{BASE}/login",
        params={"username": USERNAME, "password": PASSWORD},
        timeout=10,
    )
    if r.status_code == 200:
        token = r.json().get("token", "")
        if token:
            print(f"  Login successful — token obtained.")
            return token
        print("  Login succeeded but no token in response.")
        sys.exit(1)

    print(f"  Login failed {r.status_code}: {r.text[:120]}")
    sys.exit(1)


def main():
    print("GraphMind Demo Seeder v11.0")
    print("=" * 50)
    print(f"Target:   {BASE}")
    print(f"Username: {USERNAME}")
    print(f"Password: {PASSWORD}")
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
            print("\nWARNING: Some services unhealthy. Continuing anyway...")
    except Exception as e:
        print(f"  Cannot reach backend: {e}")
        print("  Make sure 'python main.py' is running first.")
        sys.exit(1)
    print()

    # 2. Register / login — get JWT token
    print(f"Authenticating as '{USERNAME}'...")
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    print()

    # 3. Ingest memories
    print(f"Ingesting {len(MEMORIES)} memories...")
    print("Note: 4 s delay between memories for Ollama rate-limit safety.\n")

    total_nodes = 0
    for i, memory in enumerate(MEMORIES):
        print(f"[{i+1:2d}/{len(MEMORIES)}] {memory[:70]}...")
        try:
            r = requests.post(
                f"{BASE}/memory/ingest",
                params={"text": memory},   # username comes from JWT, not query param
                headers=headers,
                timeout=120,
            )
            if r.status_code == 200:
                data  = r.json()
                nodes = data.get("nodes_created", 0)
                ms    = data.get("execution_time_ms", 0)
                dup   = data.get("duplicate", False)
                total_nodes += nodes
                status = "duplicate — skipped" if dup else f"{nodes} nodes — {ms:.0f}ms"
                print(f"           {status}")
            elif r.status_code == 401:
                print("           401 Unauthorized — token may have expired. Re-run the seeder.")
                sys.exit(1)
            else:
                print(f"           ERROR {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"           FAILED: {e}")

        if i < len(MEMORIES) - 1:
            time.sleep(4)

    print()
    print("=" * 50)
    print(f"Done. {total_nodes} memory nodes created.")
    print()
    print("Login credentials:")
    print(f"  Username: {USERNAME}")
    print(f"  Password: {PASSWORD}")
    print()
    print("Suggested demo queries:")
    print('  "What should I study this week to prepare for my Google interview?"')
    print('  "What are my weaknesses and how should I address them?"')
    print('  "Create an 8-week study plan for my Google interview"')
    print('  "What system design topics do I need to learn?"')
    print()
    print("Contradiction demo (triggers ⚠️ alert):")
    print('  "Tell me about my dynamic programming skills"')


if __name__ == "__main__":
    main()