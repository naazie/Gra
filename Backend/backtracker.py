"""
GraphMind — Backtracker v12.0

New philosophy:
  Backtracking fires ONLY when a request expresses a non-trivial learning/
  achievement goal AND the system lacks sufficient knowledge of the user's
  level on the prerequisites for that goal.

  It does NOT fire for:
    - Single-concept questions  ("what is a transformer?")
    - Document / resource questions ("tell me about this PDF")
    - Conversational / emotional messages
    - Goals the system already has good coverage on for this user
    - Goals already backtracked this session (dedup via session_state)

  When it fires:
    - A dedicated MCQ block is the ENTIRE response for that turn
    - Each MCQ has exactly 3 options (A/B/C): solid / partial / weak
    - The question is about the prerequisite topic, not the user's goal/company/timeline
    - The answer is matched exactly against the stored options — no regex
    - Answers are stored as structured memories
    - When all gaps answered → final personalised plan is generated

Public API used by main.py:
    needs_backtracking(query, entities, username, session_id,
                       graph_engine, embedder, faiss_mgr)
        -> (bool, List[str] gaps, str goal)

    build_mcq(gap, topic, goal) -> {"question": str, "options": {"A":..,"B":..,"C":..}, "rendered": str}

    match_mcq_answer(user_text, mcq) -> ("A"|"B"|"C", option_text) | (None, None)

    build_final_plan_prompt(goal, mcq_answers) -> str
"""

import os
import re
import json
import asyncio
import requests
from typing import List, Dict, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

from session_state import (
    get_state, set_gap_queue, get_active_gap,
    advance_gap, clear_gaps,
    set_active_mcq, get_active_mcq,
    record_mcq_answer, get_mcq_answers,
    goal_already_triggered, consume_gaps_complete,
    get_context_summary,
)

MAX_GAPS = 3          # cap: never ask more than 3 MCQs per backtrack session
COVERAGE_THRESHOLD = 0.60   # FAISS cosine above this = user has relevant memory


# ══════════════════════════════════════════════════════════════════════════════
#  GATE: does this request need backtracking?
# ══════════════════════════════════════════════════════════════════════════════

# Patterns that indicate a non-trivial learning/achievement goal
_GOAL_PATTERNS = re.compile(
    r"\b("
    r"prepare|prep(are)?|preparing|"
    r"learn|learning|want to learn|"
    r"get into|crack|land|apply|applying|"
    r"interview at|interview for|interview prep|"
    r"roadmap|study plan|how (do i|should i|can i) (learn|study|prepare|get|become)|"
    r"become a|get a job|get hired|"
    r"understand deeply|master|deep dive into|"
    r"start (with|learning|studying)|"
    r"teach me (how to|about)?\s*\w+"
    r")\b",
    re.I,
)

# Patterns that disqualify a request from backtracking even if the above matches
_DISQUALIFY_PATTERNS = re.compile(
    r"\b("
    r"what is|what are|what does|what's|"
    r"explain|define|definition of|"
    r"difference between|compare|vs\.?|versus|"
    r"tell me about|show me|summarize|summarise|"
    r"this (pdf|doc|document|paper|article|file)|"
    r"you just|you said|earlier you|"
    r"can you (show|give|write|code|implement)"
    r")\b",
    re.I,
)


def is_learnable_goal(query: str) -> bool:
    """
    Returns True if the query expresses a non-trivial learning/achievement
    goal that likely has prerequisites worth assessing.

    Logic:
      1. Must match a goal pattern
      2. Must NOT be disqualified by a single-concept / document pattern
      3. Must be long enough to be a real goal (>= 5 words)
    """
    q = query.strip()
    if len(q.split()) < 6:
        return False
    if not _GOAL_PATTERNS.search(q):
        return False
    if _DISQUALIFY_PATTERNS.search(q):
        return False
    return True


async def needs_backtracking(
    query: str,
    entities: List[str],
    username: str,
    session_id: str,
    graph_engine,
    embedder,
    faiss_mgr,
) -> Tuple[bool, List[str], str]:
    """
    Main gate. Called once per incoming query in main.py.

    Returns (should_backtrack, gaps, goal_string).
      should_backtrack = True  → main.py returns the MCQ as the full response
      should_backtrack = False → normal answer generation proceeds

    Will return False if:
      - Query is not a learnable goal
      - This goal was already backtracked this session
      - System already has sufficient coverage of prerequisites for this user
    """
    if not is_learnable_goal(query):
        return False, [], ""

    goal = query.strip()

    # Dedup: same goal asked twice in a session → skip
    if goal_already_triggered(session_id, goal):
        return False, [], goal

    # Fetch prerequisites
    prereqs = await _get_prerequisites(goal, entities, graph_engine, username)
    if not prereqs:
        return False, [], goal

    # Check coverage for each prerequisite
    gaps = _find_uncovered_prereqs(prereqs, username, graph_engine, embedder, faiss_mgr)

    # Need backtracking if more than half of prereqs have no user coverage
    coverage_ratio = 1.0 - (len(gaps) / len(prereqs))
    if coverage_ratio >= 0.6:
        # System already knows enough about this user → answer directly
        return False, [], goal

    # Cap at MAX_GAPS to avoid overwhelming the user
    gaps = gaps[:MAX_GAPS]

    return True, gaps, goal


async def _get_prerequisites(
    goal: str,
    entities: List[str],
    graph_engine,
    username: str,
) -> List[str]:
    """
    Fetch prerequisites for this goal.
    Priority: curriculum graph → LLM fetch.
    """
    # 1. Try curriculum graph (fast, reliable for CS topics)
    topic = entities[0] if entities else ""
    if topic:
        try:
            from curriculum_graph import get_curriculum_prerequisites
            curr = get_curriculum_prerequisites(graph_engine, topic)
            if curr:
                return [p["topic"] for p in curr]
        except Exception:
            pass

    # 2. Fall back to LLM-based requirement fetch
    try:
        from requirement_fetcher import fetch_requirements
        return await fetch_requirements(goal)
    except Exception:
        return []


def _find_uncovered_prereqs(
    prereqs: List[str],
    username: str,
    graph_engine,
    embedder,
    faiss_mgr,
) -> List[str]:
    """
    For each prereq, check if the system has meaningful memory about the
    user's level on it. Returns the ones with no coverage.
    """
    uncovered = []
    for topic in prereqs:
        if not _has_user_coverage(topic, username, graph_engine, embedder, faiss_mgr):
            uncovered.append(topic)
    return uncovered


def _has_user_coverage(
    topic: str,
    username: str,
    graph_engine,
    embedder,
    faiss_mgr,
) -> bool:
    """
    Returns True if FAISS or the graph has relevant user memory about this topic.
    """
    # FAISS semantic check
    if embedder and faiss_mgr:
        try:
            vec  = embedder.embed(topic)
            hits = faiss_mgr.search(user_id=username, query_vector=vec, top_k=1)
            if hits and hits[0]["cosine_similarity"] >= COVERAGE_THRESHOLD:
                return True
        except Exception:
            pass

    # Neo4j STRONG_IN / CONFIRMS check
    try:
        with graph_engine.driver.session() as session:
            result = session.run(
                """
                MATCH (u:User {username: $un})-[:REMEMBERS]->(m:Memory)
                WHERE toLower(m.content) CONTAINS toLower($topic)
                  AND NOT m.archived = true
                RETURN count(m) AS cnt
                """,
                un=username, topic=topic,
            )
            record = result.single()
            if record and record["cnt"] > 0:
                return True
    except Exception:
        pass

    return False


# ══════════════════════════════════════════════════════════════════════════════
#  MCQ BUILDER  (LLM-generated, cached per gap+goal)
# ══════════════════════════════════════════════════════════════════════════════

# Cache: (gap_lower, goal_lower) -> mcq dict
# Avoids re-calling Ollama for the same gap in the same server lifetime.
_mcq_cache: Dict[Tuple[str, str], Dict] = {}

_FALLBACK_MCQ_TEMPLATE = (
    "{gap} is a prerequisite for {goal}. How would you rate your current level?",
    "Strong — I understand it well and can apply it confidently",
    "Partial — I know the basics but have meaningful gaps",
    "Weak — I would need to learn this largely from scratch",
)


def _mcq_cache_key(gap: str, goal: str) -> Tuple[str, str]:
    return (gap.lower().strip()[:60], goal.lower().strip()[:80])


def _build_fallback_mcq(gap: str, goal: str) -> Dict:
    """Minimal deterministic MCQ used only when Ollama fails."""
    q_tmpl, a_txt, b_txt, c_txt = _FALLBACK_MCQ_TEMPLATE
    question = q_tmpl.format(gap=gap, goal=goal or gap)
    options  = {"A": a_txt, "B": b_txt, "C": c_txt}
    rendered = f"{question}\n\nA) {a_txt}\nB) {b_txt}\nC) {c_txt}"
    return {"question": question, "options": options, "rendered": rendered}


def _ollama_generate_mcq(gap: str, goal: str) -> str:
    """Synchronous Ollama call — run via asyncio.to_thread."""
    prompt = f"""You are assessing a student's prerequisite knowledge before helping them with their goal.

Goal: "{goal}"
Prerequisite topic to assess: "{gap}"

Write ONE multiple-choice question that tests the student's practical understanding of "{gap}" as it relates to "{goal}".

Rules:
- The question must be about "{gap}" specifically — NOT about the goal, company, timeline, or role
- Test real conceptual understanding or ability to apply the topic, not trivia
- Option A = solid/strong level, Option B = partial/some experience, Option C = weak/unfamiliar
- Each option must be a specific, honest-sounding self-assessment (1 sentence)
- The question should open with ONE sentence explaining why "{gap}" matters for "{goal}", then ask

Return ONLY valid JSON in this exact shape, no markdown, no explanation:
{{"question": "...", "A": "...", "B": "...", "C": "..."}}

JSON:"""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":   "llama3.1",
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": 0.3, "num_predict": 300},
            },
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"[backtracker] Ollama MCQ generation failed: {e}")
        return ""


async def build_mcq(gap: str, goal: str) -> Dict:
    """
    Generate a contextually relevant MCQ for a prerequisite gap using Ollama.
    Cached per (gap, goal) pair — Ollama is only called once per unique combination.

    Returns:
    {
        "question":  str,
        "options":   {"A": str, "B": str, "C": str},
        "rendered":  str,   # full text block ready to send as the response
    }
    """
    key = _mcq_cache_key(gap, goal)
    if key in _mcq_cache:
        return _mcq_cache[key]

    raw = await asyncio.to_thread(_ollama_generate_mcq, gap, goal)

    mcq = None
    if raw:
        try:
            match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                q   = str(data.get("question", "")).strip()
                a   = str(data.get("A", "")).strip()
                b   = str(data.get("B", "")).strip()
                c   = str(data.get("C", "")).strip()
                if q and a and b and c:
                    options  = {"A": a, "B": b, "C": c}
                    rendered = f"{q}\n\nA) {a}\nB) {b}\nC) {c}"
                    mcq = {"question": q, "options": options, "rendered": rendered}
        except Exception as e:
            print(f"[backtracker] MCQ JSON parse failed: {e} | raw: {raw[:120]}")

    if not mcq:
        mcq = _build_fallback_mcq(gap, goal)

    _mcq_cache[key] = mcq
    return mcq


# ══════════════════════════════════════════════════════════════════════════════
#  ANSWER MATCHER
# ══════════════════════════════════════════════════════════════════════════════

def match_mcq_answer(
    user_text: str,
    mcq: Dict,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to match the user's reply to one of the MCQ options.

    Matching strategy (in order):
      1. Exact letter: "A", "B", "C" (case-insensitive, strip punctuation)
      2. Letter with parens/dot: "A)", "B.", etc.
      3. Starts with the option text (first 10 chars)
      4. Contains the option text (first 15 chars)

    Returns (label, option_text) or (None, None) if no match.
    """
    if not mcq:
        return None, None

    options: Dict[str, str] = mcq.get("options", {})
    t = user_text.strip()

    # Strategy 1 & 2: bare letter or letter with punctuation
    clean = re.sub(r"[^a-zA-Z]", "", t[:5]).upper()
    if clean in ("A", "B", "C"):
        return clean, options.get(clean, "")

    # Strategy 3 & 4: option text match
    t_lower = t.lower()
    for label, opt_text in options.items():
        prefix = opt_text[:15].lower()
        if t_lower.startswith(opt_text[:10].lower()) or prefix in t_lower:
            return label, opt_text

    return None, None


# ══════════════════════════════════════════════════════════════════════════════
#  FINAL PLAN PROMPT
# ══════════════════════════════════════════════════════════════════════════════

def build_final_plan_prompt(goal: str, mcq_answers: Dict[str, str]) -> str:
    """
    Build the prompt injected into generate_answer_async when all gaps are answered.
    The LLM receives this instead of a backtrack_question — it generates a plan.
    """
    answers_text = "\n".join(
        f"  - {topic}: {answer}" for topic, answer in mcq_answers.items()
    )

    return (
        f"You have just finished assessing the user's prerequisite knowledge for their goal: '{goal}'.\n"
        f"\nHere is what they told you about their level on each prerequisite:\n{answers_text}\n"
        f"\nNow give them a concrete, personalised preparation plan. Rules:\n"
        f"1. Open with one sentence acknowledging where they stand overall\n"
        f"2. Tell them exactly what to tackle FIRST based on their weakest gaps\n"
        f"3. Tell them what they can move faster through given their stronger areas\n"
        f"4. Give 2-3 specific resource/action recommendations (LeetCode problems, topics, etc.)\n"
        f"5. End with a realistic timeline or weekly structure this plan should be pointwise\n"
        f"6. Write in prose — no bullet dumps. Warm, direct, like a mentor who just interviewed them.\n"
        f"7. Do NOT ask any more questions in this response."
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LEGACY COMPAT (kept so nothing else breaks)
# ══════════════════════════════════════════════════════════════════════════════

def detect_intent(text: str, entities: List[str]) -> Dict:
    """Legacy shim — main.py v12 no longer calls this for backtracking decisions."""
    return {
        "is_study_request": bool(_GOAL_PATTERNS.search(text)),
        "is_gap_answer":    False,
        "has_goal":         bool(_GOAL_PATTERNS.search(text)),
        "topic":            entities[0] if entities else "",
    }


def compute_gaps_for_topic(graph_engine, username, topic, llm_requirements,
                           embedder=None, faiss_mgr=None) -> List[str]:
    """Legacy shim — used by /study-plan endpoint, not the chat flow."""
    return _find_uncovered_prereqs(
        llm_requirements, username, graph_engine, embedder, faiss_mgr
    )