"""
GraphMind — Tutor Engine v11.0

The intelligence layer that makes this feel like a next-level tutor.

Manages:
  1. Learning style detection — how does this person learn?
  2. Spaced repetition surfacing — what needs review right now?
  3. Readiness score — how prepared are they for their goal?
  4. Daily brief — one-sentence synthesis on session start
  5. Study plan generation — week-by-week roadmap from gap analysis
  6. Progress recognition — notices and celebrates real improvement
  7. Active recall mode — tests understanding, doesn't just explain
  8. Forgetting curve with reinforcement count
  9. CONFIRMS / DERIVED_FROM edge creation
"""

import os
import re
import json
import math
import asyncio
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


# ── 1. Learning style detection ────────────────────────────────────────────────

LEARNING_STYLES = {
    "example_first":  "This person learns best from concrete examples before theory.",
    "theory_first":   "This person prefers understanding the why before the how.",
    "visual":         "This person benefits from analogies and visual descriptions.",
    "practice_first": "This person learns best by doing, then reflecting.",
}


def detect_learning_style(messages: List[str]) -> str:
    """
    Heuristic learning style detection from first few messages.
    Updates session state with the detected style.
    """
    combined = " ".join(messages[:6]).lower()

    example_signals = ["example", "show me", "like what", "give me", "for instance", "how would i"]
    theory_signals  = ["why", "how does", "what is", "explain", "understand", "principle"]
    practice_signals = ["let me try", "i'll do", "quiz me", "test me", "practice", "drill"]

    example_count  = sum(1 for s in example_signals  if s in combined)
    theory_count   = sum(1 for s in theory_signals   if s in combined)
    practice_count = sum(1 for s in practice_signals if s in combined)

    if practice_count >= 2:
        return "practice_first"
    elif example_count > theory_count:
        return "example_first"
    elif theory_count > example_count:
        return "theory_first"
    return "example_first"  # Default


def get_style_instruction(style: str) -> str:
    return LEARNING_STYLES.get(style, LEARNING_STYLES["example_first"])


# ── 2. Spaced repetition — improved forgetting curve ──────────────────────────

def improved_decay_score(days_since_reinforced: float, reinforcement_count: int) -> float:
    """
    Improved Ebbinghaus forgetting curve that accounts for reinforcement count.

    Standard:   decay = e^(-λ * days)
    Improved:   decay = e^(-λ * days / (1 + reinforcement_count * 0.3))

    The more times a memory has been reinforced, the slower it decays.
    This models human memory correctly — spaced repetition works.

    At 0 reinforcements: half-life ~14 days (λ=0.05)
    At 5 reinforcements: half-life ~35 days
    At 10 reinforcements: half-life ~56 days
    """
    LAMBDA = float(os.getenv("DECAY_LAMBDA", "0.05"))
    effective_lambda = LAMBDA / (1 + reinforcement_count * 0.3)
    return round(math.exp(-effective_lambda * max(0, days_since_reinforced)), 6)


def get_topics_needing_review(graph_engine, username: str, threshold_days: int = 5) -> List[Dict]:
    """
    Returns topics the user hasn't reviewed in threshold_days days,
    ordered by importance (graph_score * inverse_decay = most urgent first).
    """
    try:
        with graph_engine.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                WHERE (m.archived IS NULL OR m.archived = false)
                  AND m.decay_score IS NOT NULL
                  AND m.decay_score < 0.7
                RETURN m.content     AS content,
                       m.decay_score AS decay,
                       m.graph_score AS importance,
                       m.usage_count AS reinforced
                ORDER BY (m.graph_score * (1.0 - m.decay_score)) DESC
                LIMIT 5
                """,
                username=username,
            )
            return [
                {
                    "content":   r["content"][:80],
                    "decay":     round(r["decay"] or 1.0, 2),
                    "importance": round(r["importance"] or 0.0, 2),
                    "reinforced": r["reinforced"] or 0,
                    "freshness_pct": int((r["decay"] or 1.0) * 100),
                }
                for r in result
            ]
    except Exception:
        return []


# ── 3. Readiness score ─────────────────────────────────────────────────────────

async def compute_readiness_score(
    graph_engine,
    username: str,
    goal: str,
    requirements: List[str],
    embedder,
    faiss_mgr,
) -> Dict:
    """
    Computes a readiness percentage for a specific goal.

    Scoring:
    - Stated knowledge (user mentioned it): 0.5 points
    - Demonstrated knowledge (CONFIRMS edge, correct drill): 1.0 points
    - Inferred knowledge (DERIVED_FROM, high-confidence memory): 0.75 points

    Returns percentage + top 3 gaps + strengths.
    """
    if not requirements:
        return {"score": 0, "gaps": [], "strengths": [], "goal": goal}

    scores: Dict[str, float] = {}
    THRESHOLD = 0.60

    # Get confirmed topics (drill successes)
    confirmed = _get_confirmed_topics(graph_engine, username)
    # Get derived/inferred topics
    derived   = _get_derived_topics(graph_engine, username)

    for topic in requirements:
        if not topic or not isinstance(topic, str):
            continue
        topic_lower = topic.lower()
        best_score  = 0.0

        # Check CONFIRMS edge (demonstrated = full credit)
        if topic_lower in confirmed:
            best_score = 1.0
        # Check DERIVED_FROM (inferred = 75%)
        elif topic_lower in derived:
            best_score = 0.75
        else:
            # Check FAISS memory (stated = 50%)
            try:
                vec  = embedder.embed(topic)
                hits = faiss_mgr.search(user_id=username, query_vector=vec, top_k=1)
                if hits and hits[0]["cosine_similarity"] >= THRESHOLD:
                    best_score = 0.5
            except Exception:
                pass

        scores[topic] = best_score

    total    = sum(scores.values())
    max_poss = len(requirements)
    pct      = round((total / max_poss) * 100) if max_poss > 0 else 0

    gaps      = [t for t, s in scores.items() if s < 0.5][:5]
    strengths = [t for t, s in scores.items() if s >= 0.75][:5]

    return {
        "score":     pct,
        "gaps":      gaps,
        "strengths": strengths,
        "goal":      goal,
        "breakdown": {t: round(s, 2) for t, s in scores.items()},
    }


def _get_confirmed_topics(graph_engine, username: str) -> set:
    """Topics with CONFIRMS edges (drill successes)."""
    try:
        with graph_engine.driver.session() as session:
            r = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                      -[:CONFIRMS]->(c:Concept)
                RETURN DISTINCT toLower(c.name) AS topic
                """,
                username=username,
            )
            return {row["topic"] for row in r}
    except Exception:
        return set()


def _get_derived_topics(graph_engine, username: str) -> set:
    """Topics the system inferred the user knows via DERIVED_FROM."""
    try:
        with graph_engine.driver.session() as session:
            r = session.run(
                """
                MATCH (u:User {username: $username})-[:REMEMBERS]->(m:Memory)
                      -[:DERIVED_FROM]->(c:Concept)
                RETURN DISTINCT toLower(c.name) AS topic
                """,
                username=username,
            )
            return {row["topic"] for row in r}
    except Exception:
        return set()


# ── 4. Daily brief ─────────────────────────────────────────────────────────────

async def generate_daily_brief(
    username: str,
    goal: str,
    readiness_pct: int,
    top_gap: str,
    days_since_last: int,
    review_needed: List[Dict],
) -> str:
    """
    One-sentence synthesis of the user's situation.
    Generated on session start when they haven't been seen in >8 hours.
    """
    review_topic = review_needed[0]["content"][:40] if review_needed else ""

    prompt = f"""Write ONE sentence (max 30 words) that a mentor would say to greet {username} at the start of a session.

Facts:
- Their goal: {goal or 'prepare for software engineering interviews'}
- Readiness: {readiness_pct}%
- Biggest gap: {top_gap or 'unknown'}
- Days since last session: {days_since_last}
- Topic needing review: {review_topic or 'none urgent'}

Be warm and specific. Reference their actual situation. Not generic encouragement.
Example: "You're at 67% for Google — DP is still the gap, and recursion is getting stale. Let's tackle both today."
Just the sentence, no quotes."""

    result = await _gemini_call_simple(prompt, temperature=0.6, max_tokens=60)
    if result:
        return result

    # Fallback
    return (
        f"You're {readiness_pct}% ready for your goal"
        + (f" — {top_gap} is the next thing to tackle" if top_gap else "")
        + ". Let's make progress today."
    )


# ── 5. Study plan generation ───────────────────────────────────────────────────

async def generate_study_plan(
    username: str,
    goal: str,
    gaps: List[str],
    weeks_available: int,
    hours_per_day: float,
    strengths: List[str],
) -> str:
    """
    Generates a week-by-week study plan grounded in the user's actual gaps.
    """
    if not gaps:
        return f"Great news — based on what I know, you don't have major gaps for {goal}. Focus on mock interviews and review."

    gaps_str      = ", ".join(gaps[:6])
    strengths_str = ", ".join(strengths[:4]) if strengths else "not yet assessed"

    prompt = f"""Create a concrete {weeks_available}-week study plan for {username}.

Goal: {goal}
Hours available per day: {hours_per_day}
Known strengths: {strengths_str}
Topics to cover (gaps): {gaps_str}

Format the plan as:
Week 1: [topic] - [specific daily tasks]
Week 2: [topic] - [specific daily tasks]
...

Include specific LeetCode problem numbers or resources where possible.
Be realistic about what can be covered in {hours_per_day} hours/day.
Keep each week's plan to 2 sentences max.
End with one sentence about mock interviews."""

    result = await _gemini_call_simple(prompt, temperature=0.3, max_tokens=500)
    return result if result else f"Focus on {gaps[0]} this week, then {gaps[1] if len(gaps) > 1 else 'mock interviews'} next week."


# ── 6. Progress recognition ────────────────────────────────────────────────────

def detect_progress(
    current_message: str,
    past_memories: List[str],
) -> Optional[str]:
    """
    Checks if the current message shows improvement on something
    the user previously struggled with.

    Returns a specific praise string if improvement detected, None otherwise.
    """
    lower = current_message.lower()

    # Look for signals of successful understanding
    success_signals = [
        "i got it", "i understand", "makes sense", "i solved", "figured out",
        "i know how", "i can explain", "finally", "clicked", "got it working",
    ]
    if not any(s in lower for s in success_signals):
        return None

    # Check if any past memory mentioned struggling with related topics
    struggle_signals = ["weak", "struggle", "can't", "don't understand",
                        "confused", "difficult", "hard for me", "keep failing"]

    for memory in past_memories[:10]:
        mem_lower = memory.lower()
        if any(s in mem_lower for s in struggle_signals):
            # Extract the struggling topic from the memory
            topic_hints = [w for w in mem_lower.split() if len(w) > 4
                          and w not in {"that", "this", "with", "have", "been", "very"}]
            for hint in topic_hints[:3]:
                if hint in lower:
                    return f"Worth noting — you used to struggle with {hint}, and this answer shows real progress."

    return None


# ── 7. Active recall instruction ───────────────────────────────────────────────

ACTIVE_RECALL_INSTRUCTION = """
After your explanation, use active recall: ask the user to explain it back in their own words,
or apply it to a specific example. Say something like "Now you try — can you explain [concept]
back to me as if you're teaching it to someone?" This is more valuable than a longer explanation.
"""

FEYNMAN_INSTRUCTION = """
After explaining, use the Feynman technique: ask them to explain it back simply.
Say "Forget everything I just said — explain [concept] like you're teaching a 10-year-old.
If you can do that, you truly understand it."
"""


# ── 8. Ollama helper ──────────────────────────────────────────────────────────

def _ollama_call_sync(prompt: str, temperature: float = 0.4, max_tokens: int = 300) -> str:
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":   "llama3.1",
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"[tutor_engine] Ollama error: {e}")
        return ""


async def _gemini_call_simple(prompt: str, temperature: float = 0.4, max_tokens: int = 300) -> str:
    # Kept as alias so callers don't need renaming — now uses Ollama
    return await asyncio.to_thread(_ollama_call_sync, prompt, temperature, max_tokens)