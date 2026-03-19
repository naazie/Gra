"""
GraphMind — Interview Simulator v11.0

Full mock interview mode. The system becomes the interviewer.
NOT just a Q&A — it probes, challenges, and evaluates like a real interviewer.

Features:
  - Generates questions based on user's weak spots from memory
  - Difficulty calibration: scales based on past performance
  - Turn-by-turn interviewer dialogue
  - Detects when user is struggling and probes appropriately
  - End-of-session scorecard via Gemini
  - Stores attempt with ATTEMPTED / CORRECT_IN / MISTAKE_IN edges
  - Misconception detection: catches subtly wrong mental models
  - Continuity: "last time you tried X, you got stuck on Y"
"""

import os
import re
import json
import asyncio
import requests
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Interview session state (in-memory, per session_id)
_interview_sessions: Dict[str, Dict] = {}


# ── Interview question bank categories ────────────────────────────────────────

QUESTION_TYPES = {
    "coding":        "LeetCode-style algorithmic problem",
    "system_design": "System design problem",
    "behavioral":    "Behavioral / STAR format question",
    "concept":       "Conceptual CS question",
}


def start_interview(
    session_id: str,
    username: str,
    target_company: str = "",
    target_role: str = "Software Engineer",
    weak_topics: List[str] = [],
    past_attempts: List[Dict] = [],
) -> Dict:
    """
    Initialises an interview session.
    Returns the interview state dict.
    """
    _interview_sessions[session_id] = {
        "username":       username,
        "company":        target_company or "a top tech company",
        "role":           target_role,
        "weak_topics":    weak_topics or [],
        "past_attempts":  past_attempts or [],
        "turn":           0,
        "max_turns":      12,   # ~45 min interview
        "current_q":      None,
        "current_topic":  None,
        "difficulty":     _calibrate_difficulty(past_attempts or []),
        "transcript":     [],
        "started_at":     __import__("time").time(),
        "active":         True,
    }
    return _interview_sessions[session_id]


def get_interview_state(session_id: str) -> Optional[Dict]:
    return _interview_sessions.get(session_id)


def is_interview_active(session_id: str) -> bool:
    state = _interview_sessions.get(session_id)
    return bool(state and state.get("active"))


def end_interview(session_id: str):
    state = _interview_sessions.get(session_id)
    if state:
        state["active"] = False


def _calibrate_difficulty(past_attempts: List[Dict]) -> int:
    """
    Returns difficulty level 1-5 based on past performance.
    1 = easy, 3 = medium, 5 = hard
    """
    if not past_attempts:
        return 2  # Start easy-medium

    correct = sum(1 for a in past_attempts if a.get("correct", False))
    total   = len(past_attempts)
    rate    = correct / total if total > 0 else 0.5

    if rate >= 0.8:   return min(5, 4)   # Doing very well → hard
    elif rate >= 0.6: return 3            # Decent → medium
    elif rate >= 0.4: return 2            # Struggling → easy-medium
    else:             return 1            # Struggling a lot → easy


async def generate_interview_question(
    session_id: str,
    question_type: str = "coding",
    user_memories: str = "",
    difficulty_override: int = 0,
) -> str:
    """
    Generates a fresh interview question appropriate to:
    - The user's weak spots
    - Their demonstrated difficulty level
    - The target company style
    - What they haven't been asked yet this session
    """
    state = _interview_sessions.get(session_id)
    if not state:
        return "Let's start with a classic: reverse a linked list."

    diff      = difficulty_override or state["difficulty"]
    company   = state["company"]
    weak      = state["weak_topics"]
    past_qs   = [t["question"][:50] for t in state["transcript"] if "question" in t]

    diff_labels = {1: "easy", 2: "easy-medium", 3: "medium", 4: "medium-hard", 5: "hard"}
    diff_label  = diff_labels.get(diff, "medium")

    weak_str = ", ".join(weak[:3]) if weak else "general algorithms"
    past_str = "; ".join(past_qs[-3:]) if past_qs else "none yet"

    prompt = f"""You are a {company} interviewer conducting a {question_type} interview for a {state['role']} role.

Generate ONE {diff_label} difficulty {question_type} interview question.
Focus on the candidate's weak areas: {weak_str}
Don't repeat these recent questions: {past_str}

User context: {user_memories[:300] if user_memories else 'No specific context'}

Requirements:
- Ask the question directly as the interviewer would
- For coding: give a clear problem statement with an example
- For system design: give a realistic scenario (e.g. "Design Twitter's feed")
- For behavioral: use STAR-format prompting
- For concept: ask something that reveals depth of understanding
- Keep it to 3-5 sentences max
- Don't give hints or the answer

Just the question, nothing else."""

    result = await _ollama_call(prompt, temperature=0.7, max_tokens=300)
    if result:
        state["current_q"]    = result
        state["current_topic"] = question_type
        state["transcript"].append({"role": "interviewer", "question": result, "type": question_type})
        return result

    # Fallback questions by type
    fallbacks = {
        "coding":        "Given an array of integers, find the two numbers that sum to a target. Return their indices.",
        "system_design": "Design a URL shortening service like bit.ly. Walk me through your approach.",
        "behavioral":    "Tell me about a time you had to debug a particularly difficult problem. What was your approach?",
        "concept":       "Explain the difference between BFS and DFS. When would you choose one over the other?",
    }
    q = fallbacks.get(question_type, fallbacks["coding"])
    state["current_q"]    = q
    state["current_topic"] = question_type
    state["transcript"].append({"role": "interviewer", "question": q, "type": question_type})
    return q


async def respond_as_interviewer(
    session_id: str,
    user_answer: str,
    user_memories: str = "",
) -> Tuple[str, bool, str]:
    """
    Responds to a user's answer as the interviewer would.
    Returns (response, is_done, feedback_hint)

    Interviewer behaviour:
    - Probes weak spots ("interesting, but what about edge cases?")
    - Asks follow-up when answer is good ("how would you scale this?")
    - Redirects when completely wrong (without giving the answer)
    - Moves on when question is thoroughly answered
    """
    state = _interview_sessions.get(session_id)
    if not state:
        return "Let's continue.", False, ""

    state["turn"] += 1
    state["transcript"].append({"role": "candidate", "answer": user_answer})

    is_done       = state["turn"] >= state["max_turns"]
    company       = state["company"]
    current_q     = state.get("current_q", "the previous question")
    question_type = state.get("current_topic", "coding")

    prompt = f"""You are a {company} interviewer. The candidate just answered.

QUESTION ASKED: {current_q}

CANDIDATE'S ANSWER: {user_answer}

CANDIDATE CONTEXT: {user_memories[:200] if user_memories else ''}

Respond as the interviewer would NATURALLY:
- If the answer is correct and thorough: acknowledge it briefly and ask ONE follow-up to go deeper
- If the answer is partially correct: acknowledge what's right, then probe the gap with ONE question
- If the answer is wrong: don't say "wrong" — say "interesting approach, but consider..." and redirect
- If they seem stuck: give a SMALL hint, not the answer
- After turn {min(state['turn']+2, state['max_turns'])}, wrap up this question and move on

Keep it to 2-3 sentences. Sound like a real person, not a grading rubric.
{'This is the final question — after their answer, end the interview.' if is_done else ''}"""

    response = await _ollama_call(prompt, temperature=0.5, max_tokens=200)
    if not response:
        response = "Interesting. Can you walk me through the time complexity of your approach?"

    state["transcript"].append({"role": "interviewer", "response": response})
    return response, is_done, ""


async def detect_misconception(
    user_explanation: str,
    topic: str,
) -> Optional[str]:
    """
    Checks if the user's explanation of a concept contains a subtle misconception.
    Returns a natural correction if found, None if the explanation is sound.

    This is what separates a great tutor from a good one — catching almost-right
    mental models before they calcify.
    """
    prompt = f"""A student explained this about {topic}:

"{user_explanation}"

Is there a subtle misconception or imprecision in their understanding?
Look for:
- Confusing similar concepts (e.g. "memoization IS dynamic programming")
- Missing nuance (e.g. "greedy always works" — it doesn't)
- Edge cases they're ignoring
- Terminology used slightly wrong

If the explanation is essentially correct: respond with exactly "CORRECT"
If there's a misconception: respond with ONE sentence correcting it naturally,
like a tutor would say it. Don't be harsh. Be specific about what's subtly wrong.
Keep it under 40 words."""

    result = await _ollama_call(prompt, temperature=0.2, max_tokens=100)
    if result and result.strip().upper() != "CORRECT" and result.strip():
        return result.strip()
    return None


async def generate_scorecard(session_id: str, user_memories: str = "") -> Dict:
    """
    End-of-interview scorecard generated by Gemini.
    Returns structured dict with scores and specific feedback.
    """
    state = _interview_sessions.get(session_id)
    if not state:
        return {}

    transcript_str = "\n".join([
        f"[{t['role'].upper()}]: {t.get('question') or t.get('answer') or t.get('response', '')}"
        for t in state["transcript"][-20:]  # Last 20 turns
    ])

    duration_min = int(((__import__("time").time() - state["started_at"]) / 60))

    prompt = f"""You are evaluating a mock {state['company']} interview for a {state['role']} role.

TRANSCRIPT:
{transcript_str}

Rate the candidate on each dimension (1-10) and give specific feedback.
Return ONLY valid JSON:
{{
  "overall": <1-10>,
  "problem_solving": <1-10>,
  "communication": <1-10>,
  "technical_depth": <1-10>,
  "strongest_moment": "<one specific thing they did well>",
  "biggest_gap": "<one specific thing to work on>",
  "would_pass": <true/false>,
  "next_steps": "<one concrete action they should take>",
  "summary": "<2-3 sentence honest assessment>"
}}"""

    raw = await _ollama_call(prompt, temperature=0.2, max_tokens=400)

    scorecard = {
        "overall": 5, "problem_solving": 5, "communication": 5,
        "technical_depth": 5, "would_pass": False,
        "strongest_moment": "Showed willingness to work through the problem",
        "biggest_gap":      "Needs more practice with edge cases",
        "next_steps":       "Practice 2 medium LeetCode problems per day",
        "summary":          "Good effort. Keep practicing.",
        "duration_min":     duration_min,
        "turns":            state["turn"],
    }

    if raw:
        try:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                scorecard.update(parsed)
        except Exception:
            pass

    scorecard["duration_min"] = duration_min
    scorecard["turns"]        = state["turn"]
    return scorecard


# ── Ollama helper ─────────────────────────────────────────────────────────────

def _ollama_call_sync(prompt: str, temperature: float = 0.5, max_tokens: int = 300) -> str:
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
        print(f"[interview_simulator] Ollama error: {e}")
        return ""


async def _ollama_call(prompt: str, temperature: float = 0.5, max_tokens: int = 300) -> str:
    return await asyncio.to_thread(_ollama_call_sync, prompt, temperature, max_tokens)