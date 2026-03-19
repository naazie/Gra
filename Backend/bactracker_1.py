"""
GraphMind — Backtracker v11.0

Natural one-at-a-time prerequisite questioning.

Philosophy:
  - NEVER dump all gaps at once (that's robotic)
  - Ask about the single most critical gap first
  - Store the user's answer as a memory
  - Move to the next gap in a later turn
  - The conversation ITSELF is the backtracking process

Integration with requirement_fetcher.py:
  - If Neo4j has PREREQUISITE_OF edges → use those
  - Otherwise → call Gemini to fetch requirements dynamically
  - Cross-check against FAISS to see what user already knows

New in v11 (aligns with main.py v11):
  - compute_gaps_for_topic() — synchronous gap analysis called directly by main.py
    after curriculum_graph already resolved prerequisites; avoids double async fetch.
  - detect_intent() — lightweight regex/keyword intent classifier; returns
    is_study_request, is_gap_answer, has_goal, topic so the chat endpoint
    can decide whether to trigger backtracking without an extra LLM call.
"""

import re
import asyncio
from typing import List, Dict, Optional

from session_state import (
    get_state, set_gap_queue, get_active_gap,
    advance_gap, clear_gaps, increment_turns,
    should_ask_next_gap, get_context_summary,
)

MAX_DEPTH = 3


# ── Graph-based prerequisite chain ────────────────────────────────────────────

def get_prerequisite_chain_from_graph(
    graph_engine,
    username: str,
    topic: str,
    depth: int = MAX_DEPTH,
) -> List[Dict]:
    """Walk PREREQUISITE_OF/REQUIRES edges in Neo4j."""
    try:
        with graph_engine.driver.session() as session:
            result = session.run(
                f"""
                MATCH path = (c:Concept)-[:PREREQUISITE_OF|REQUIRES*1..{depth}]->
                             (target:Concept {{name: $topic, user_id: $username}})
                WHERE c.user_id = $username OR c.user_id IS NULL
                RETURN c.name AS prereq, length(path) AS level
                ORDER BY level ASC
                LIMIT 20
                """,
                username=username, topic=topic,
            )
            return [{"topic": r["prereq"], "level": r["level"]} for r in result]
    except Exception:
        return []


def _get_strong_topics(graph_engine, username: str) -> set:
    """Topics the user has STRONG_IN edges for."""
    try:
        with graph_engine.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                      -[:MENTIONS]->(c1:Concept)-[:STRONG_IN]->(c2:Concept)
                RETURN DISTINCT c2.name AS topic
                """,
                username=username,
            )
            strong = {r["topic"].lower() for r in result}

            # Also check memory content for strength markers
            mem_result = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                WHERE NOT (m.archived = true)
                RETURN m.content AS content
                LIMIT 30
                """,
                username=username,
            )
            strong_markers = ["strong", "confident", "mastered", "know well",
                             "comfortable", "good at", "solved", "understand"]
            for r in mem_result:
                content = (r["content"] or "").lower()
                for marker in strong_markers:
                    if marker in content:
                        # Extract nearby words as topic names (simplified)
                        import re
                        words = re.findall(r'\b[a-z]+(?:\s+[a-z]+)?\b', content)
                        strong.update(w for w in words if len(w) > 3)

            return strong
    except Exception:
        return set()


def _user_knows_topic(topic: str, strong_topics: set, embedder=None, faiss_mgr=None, username: str = "") -> bool:
    """Check if user knows a topic via graph strong-topics or FAISS semantic match."""
    topic_lower = topic.lower()

    # Direct match
    if topic_lower in strong_topics:
        return True
    # Partial match (e.g. "dp" matches "dynamic programming")
    for s in strong_topics:
        if topic_lower in s or s in topic_lower:
            return True

    # Semantic match via FAISS
    if embedder and faiss_mgr and username:
        try:
            vec  = embedder.embed(topic)
            hits = faiss_mgr.search(user_id=username, query_vector=vec, top_k=1)
            if hits and hits[0]["cosine_similarity"] >= 0.72:
                return True
        except Exception:
            pass

    return False


# ── Intent detection (called by main.py chat endpoint) ───────────────────────

# Delivery-intent phrases — user wants OUTPUT, not interrogation.
# These BYPASS backtracking entirely regardless of study triggers.
_DELIVERY_TRIGGERS = re.compile(
    r"^(give me|create|generate|make me|show me|build me|write me|"
    r"just give|give a|give the|make a|make the|create a|create the|"
    r"i want a|i need a|i want the|i need the)|"
    r"\b(roadmap$|the plan|my plan|the roadmap|my roadmap|"
    r"just (show|tell|give)|straight(forwardly)?|directly)\b",
    re.I,
)

# Study-intent trigger phrases
_STUDY_TRIGGERS = re.compile(
    r"\b(learn|study|understand|prepare|prep|practise|practice|review|"
    r"start|begin|get into|work on|focus on|improve|master|cover|"
    r"teach me|explain|how do i|help me with|roadmap for|plan for)\b",
    re.I,
)

# Goal-intent trigger phrases
_GOAL_TRIGGERS = re.compile(
    r"\b(want to|trying to|goal is|aiming for|preparing for|target|"
    r"interview at|job at|crack|land|get into|apply to)\b",
    re.I,
)

# Gap-answer markers — signals that the user is replying to a prerequisite question
_GAP_ANSWER_TRIGGERS = re.compile(
    r"\b(yes|no|kind of|sort of|a bit|not really|never|barely|somewhat|"
    r"i know|i don't know|i do|i don't|comfortable|uncomfortable|"
    r"familiar|unfamiliar|weak|strong|good at|bad at|practiced|"
    r"haven't|have not|need to|should|i think|i guess|i feel)\b",
    re.I,
)


def detect_intent(text: str, entities: List[str]) -> Dict:
    """
    Lightweight keyword-based intent classifier for backtracking decisions.

    Called synchronously by the main.py chat endpoint — no LLM cost.

    Returns
    -------
    {
        "is_study_request": bool,  # user wants to learn/prepare a topic
        "is_gap_answer":    bool,  # user is replying to a prerequisite question
        "has_goal":         bool,  # user stated an external goal (company, job)
        "topic":            str,   # best-guess primary topic (first entity or "")
    }
    """
    text_lower = text.lower().strip()

    # Delivery requests bypass backtracking — user wants output, not questions
    is_delivery_request = bool(_DELIVERY_TRIGGERS.search(text_lower))

    is_study_request = (
        bool(_STUDY_TRIGGERS.search(text_lower))
        and not is_delivery_request
    )
    has_goal = bool(_GOAL_TRIGGERS.search(text_lower))

    # A gap answer is short (< 30 words) and contains an acknowledgement marker,
    # OR the user is clearly answering a yes/no knowledge-check question.
    word_count    = len(text_lower.split())
    is_gap_answer = (
        word_count < 30
        and bool(_GAP_ANSWER_TRIGGERS.search(text_lower))
    )

    # Primary topic: prefer the first entity, fall back to empty string
    topic = entities[0] if entities else ""

    return {
        "is_study_request":    is_study_request,
        "is_delivery_request": is_delivery_request,
        "is_gap_answer":       is_gap_answer,
        "has_goal":            has_goal,
        "topic":               topic,
    }


# ── Synchronous gap computation (called by main.py after prereq resolution) ───

def compute_gaps_for_topic(
    graph_engine,
    username: str,
    topic: str,
    llm_requirements: List[str],
    embedder=None,
    faiss_mgr=None,
) -> List[str]:
    """
    Given a pre-resolved list of prerequisites (from curriculum graph or Gemini),
    cross-check against what the user already knows and return only the gaps.

    This is the *synchronous* counterpart to analyse_and_set_gaps().
    main.py calls this after it has already fetched prerequisites, so we skip
    the async Gemini fetch step here and go straight to gap detection.

    Parameters
    ----------
    graph_engine      : GraphEngine  — to look up STRONG_IN / memory edges
    username          : str
    topic             : str          — the topic being studied
    llm_requirements  : list[str]    — prerequisites already resolved by caller
    embedder          : Embedder | None
    faiss_mgr         : FAISSManager | None

    Returns
    -------
    List of gap topic strings, ordered by prerequisite importance (preserves
    the order of llm_requirements, which curriculum_graph returns depth-first).
    """
    if not llm_requirements:
        return []

    strong = _get_strong_topics(graph_engine, username)
    gaps   = [
        prereq for prereq in llm_requirements
        if not _user_knows_topic(prereq, strong, embedder, faiss_mgr, username)
    ]
    return gaps


async def analyse_and_set_gaps(
    session_id: str,
    graph_engine,
    username: str,
    topic: str,
    goal: str = "",
    embedder=None,
    faiss_mgr=None,
) -> Optional[str]:
    """
    Main entry point for backtracking.

    1. Try to get prerequisites from Neo4j graph
    2. If Neo4j has nothing, fetch from Gemini dynamically
    3. Cross-check with user's memory
    4. Set the gap queue (one at a time)
    5. Return the first question to ask, or None if no gaps

    Returns the question to ask the user about the first gap,
    or None if no gaps found.
    """
    # Step 1: Graph-based prerequisites
    chain = get_prerequisite_chain_from_graph(graph_engine, username, topic)
    graph_prerequisites = [item["topic"] for item in chain]

    # Step 2: If graph has no edges, use Gemini to fetch requirements dynamically
    if not graph_prerequisites:
        try:
            from requirement_fetcher import fetch_requirements
            search_query = f"{goal} {topic}".strip() if goal else topic
            graph_prerequisites = await fetch_requirements(search_query)
        except Exception as e:
            print(f"[backtracker] fetch_requirements failed: {e}")
            graph_prerequisites = []

    if not graph_prerequisites:
        return None

    # Step 3: Check what user already knows
    strong = _get_strong_topics(graph_engine, username)
    gaps   = [
        prereq for prereq in graph_prerequisites
        if not _user_knows_topic(prereq, strong, embedder, faiss_mgr, username)
    ]

    if not gaps:
        return None

    # Step 4: Set gap queue (one at a time model)
    set_gap_queue(session_id, gaps, topic, goal)

    # Step 5: Return natural question for first gap
    return _natural_question(gaps[0], topic)


def _natural_question(gap: str, topic: str) -> str:
    """
    Generates a natural, conversational question about a prerequisite gap.
    NOT: "Prerequisite gap detected: recursion"
    YES: "DP builds heavily on recursion — how comfortable are you with it?"
    """
    questions = {
        "recursion":           f"Since {topic} builds heavily on recursion, how comfortable are you with it? Have you solved recursive problems before?",
        "arrays":              f"Before we get into {topic}, quick check — how solid are you with arrays and basic operations on them?",
        "dynamic programming": f"{topic} overlaps a lot with DP thinking — do you have a feel for memoization and optimal substructure?",
        "graphs":              f"Some of {topic} connects to graph concepts. How confident are you with graph traversal — BFS, DFS?",
        "trees":               f"How are you with trees? {topic} often comes up in tree-based problems.",
        "linked lists":        f"Are linked lists solid for you? They come up when studying {topic}.",
        "sorting":             f"How comfortable are you with sorting algorithms? They're foundational for {topic}.",
        "big-o notation":      f"When you look at a solution, can you reason about its time complexity? {topic} requires that thinking.",
        "system design":       f"How much have you dug into system design? It's a big part of senior-level {topic} prep.",
        "os concepts":         f"How is your operating systems knowledge? Things like processes, threads, memory management?",
        "networking":          f"How solid are you on networking fundamentals — TCP/IP, HTTP, how the web works?",
        "sql":                 f"Do you have SQL experience? Databases come up a lot in {topic} contexts.",
        "object-oriented programming": f"How comfortable are you with OOP principles? Encapsulation, inheritance, polymorphism?",
    }

    # Check for a direct match
    gap_lower = gap.lower()
    for key, question in questions.items():
        if key in gap_lower or gap_lower in key:
            return question

    # Generic fallback — still natural
    return (
        f"One thing that comes up a lot when you're working on {topic} is {gap}. "
        f"How well do you know that area? Be honest — I'd rather know now so we can plan around it."
    )


def get_next_gap_question(session_id: str) -> Optional[str]:
    """
    If there's a gap queue and it's time to ask the next one, returns the question.
    Otherwise returns None.
    """
    if not should_ask_next_gap(session_id):
        return None
    next_gap = advance_gap(session_id)
    if not next_gap:
        return None
    state = get_state(session_id)
    topic = state.get("current_topic", "this topic")
    return _natural_question(next_gap, topic)


def get_active_gap_question(session_id: str) -> Optional[str]:
    """
    If there's currently an active gap being asked about, return its question
    to remind the LLM to follow up.
    """
    active = get_active_gap(session_id)
    if not active:
        return None
    state = get_state(session_id)
    topic = state.get("current_topic", "this topic")
    return _natural_question(active, topic)