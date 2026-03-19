"""
GraphMind — Session State v12.0

Tracks per-session state for goal-gated backtracking.

New in v12:
  - MCQ mode: backtracking is a clean dedicated turn, not blended with a normal answer
  - active_mcq stores the full question text + options so answer matching is exact
    (match on "A" / "B" / "C" or the option text itself — no regex guessing)
  - mcq_answers dict accumulates {topic: "B — partial understanding"} for final plan
  - gaps_complete flag fires when queue drains → main.py generates the final plan
  - goal_triggered set prevents re-triggering backtracking for the same goal in the
    same session (fixes the repeated-profile-save bug)
"""

import re
from typing import List, Optional, Dict
from datetime import datetime, timezone

# In-memory store: {session_id: SessionData}
_states: Dict[str, Dict] = {}


def get_state(session_id: str) -> Dict:
    """Returns session state, creating it if it doesn't exist."""
    if session_id not in _states:
        _states[session_id] = {
            # Gap queue
            "active_gap":     None,
            "gap_queue":      [],
            "current_topic":  None,
            "current_goal":   None,
            # MCQ state
            "active_mcq":     None,   # {"gap": str, "question": str, "options": {"A":..,"B":..,"C":..}}
            "all_mcqs":       [],    # full list of all MCQ dicts for batch UI
            "mcq_answers":    {},     # {topic: "A — solid ..."}
            "gaps_complete":  False,  # one-shot flag when queue drains
            "goal_triggered": set(),  # goal keys already run this session
            # Misc
            "momentum":       "unknown",
            "learning_style": "example_first",
            "last_updated":   datetime.now(timezone.utc).isoformat(),
        }
    return _states[session_id]


# ── Goal dedup ─────────────────────────────────────────────────────────────────

def _goal_key(goal: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", goal.lower().strip())[:80]


def goal_already_triggered(session_id: str, goal: str) -> bool:
    """True if we already ran backtracking for this goal this session."""
    return _goal_key(goal) in get_state(session_id).get("goal_triggered", set())


# ── Gap queue ──────────────────────────────────────────────────────────────────

def set_gap_queue(session_id: str, gaps: List[str], topic: str, goal: str = ""):
    state = get_state(session_id)
    if gaps:
        state["active_gap"]    = gaps[0]
        state["gap_queue"]     = gaps[1:]
        state["current_topic"] = topic
        state["current_goal"]  = goal or topic
        state["gaps_complete"] = False
        state["goal_triggered"].add(_goal_key(goal or topic))
    state["last_updated"] = datetime.now(timezone.utc).isoformat()


def get_active_gap(session_id: str) -> Optional[str]:
    return get_state(session_id).get("active_gap")


def advance_gap(session_id: str) -> Optional[str]:
    """
    Move to next gap after an answer is recorded.
    Sets gaps_complete=True when queue empties.
    Returns new active gap or None.
    """
    state = get_state(session_id)
    state["active_mcq"] = None
    queue = state.get("gap_queue", [])
    if queue:
        state["active_gap"]    = queue[0]
        state["gap_queue"]     = queue[1:]
        state["gaps_complete"] = False
        return state["active_gap"]
    else:
        state["active_gap"]    = None
        state["gaps_complete"] = True
        return None


def consume_gaps_complete(session_id: str) -> bool:
    """One-shot read of the gaps_complete flag. Resets it after reading."""
    state = get_state(session_id)
    if state.get("gaps_complete"):
        state["gaps_complete"] = False
        return True
    return False


def clear_gaps(session_id: str):
    state = get_state(session_id)
    state["active_gap"]    = None
    state["gap_queue"]     = []
    state["active_mcq"]    = None
    state["all_mcqs"]      = []
    state["gaps_complete"] = False


# ── Batch MCQ state ───────────────────────────────────────────────────────────────

def set_all_mcqs(session_id: str, mcqs: list):
    """Store the full list of MCQ dicts for batch UI rendering."""
    get_state(session_id)["all_mcqs"] = mcqs


def get_all_mcqs(session_id: str) -> list:
    """Return the full MCQ list (for frontend batch rendering)."""
    return get_state(session_id).get("all_mcqs", [])


# ── MCQ state ──────────────────────────────────────────────────────────────────

def set_active_mcq(session_id: str, gap: str, question: str, options: Dict[str, str]):
    """Store the rendered MCQ. options = {"A": "...", "B": "...", "C": "..."}"""
    get_state(session_id)["active_mcq"] = {
        "gap": gap, "question": question, "options": options
    }


def get_active_mcq(session_id: str) -> Optional[Dict]:
    return get_state(session_id).get("active_mcq")


def record_mcq_answer(session_id: str, gap: str, label: str, text: str):
    """Store answer. label = "A"|"B"|"C", text = full option text."""
    get_state(session_id)["mcq_answers"][gap] = f"{label} — {text}"


def get_mcq_answers(session_id: str) -> Dict[str, str]:
    return get_state(session_id).get("mcq_answers", {})


# ── Context summary ────────────────────────────────────────────────────────────

def get_context_summary(session_id: str) -> str:
    state = get_state(session_id)
    parts = []
    if state.get("current_goal"):
        parts.append(f"User's goal: {state['current_goal']}")
    if state.get("current_topic"):
        parts.append(f"Topic: {state['current_topic']}")
    if state.get("momentum") != "unknown":
        parts.append(f"Progress: {state['momentum']}")
    if state.get("active_gap"):
        parts.append(f"Awaiting answer on: {state['active_gap']}")
    answers = state.get("mcq_answers", {})
    if answers:
        summary = "; ".join(f"{t}: {a}" for t, a in list(answers.items())[-4:])
        parts.append(f"Self-assessed levels: {summary}")
    return " | ".join(parts) if parts else ""


def set_momentum(session_id: str, momentum: str):
    get_state(session_id)["momentum"] = momentum


def clear_session(session_id: str):
    if session_id in _states:
        del _states[session_id]


# ── Legacy compat (main.py calls these) ───────────────────────────────────────

def increment_turns(session_id: str):
    """No longer needed for pacing but kept so existing calls don't break."""
    pass


def should_ask_next_gap(session_id: str) -> bool:
    """Legacy — always False now; main.py controls gap flow directly."""
    return False