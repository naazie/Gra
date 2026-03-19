"""
GraphMind — Conversation Manager v10.0

Maintains the last N messages of each session in memory.
These are injected into every LLM prompt so the model knows
what was just said — the core of conversational continuity.

Without this, every message is answered in isolation.
With this, the model can say "you mentioned earlier that DP was clicking..."
"""

from typing import List, Dict, Optional
from collections import deque

# In-memory store: {session_id: deque of {role, content}}
_sessions: Dict[str, deque] = {}

HISTORY_WINDOW = 6  # last 6 turns (3 user + 3 assistant) injected into every prompt


def add_message(session_id: str, role: str, content: str):
    """
    Add a message to the session history.
    role: 'user' | 'assistant'
    """
    if session_id not in _sessions:
        _sessions[session_id] = deque(maxlen=HISTORY_WINDOW)
    _sessions[session_id].append({"role": role, "content": content})


def get_recent(session_id: str, n: int = HISTORY_WINDOW) -> List[Dict]:
    """Returns the last n messages for this session."""
    if session_id not in _sessions:
        return []
    return list(_sessions[session_id])[-n:]


def format_for_prompt(session_id: str) -> str:
    """
    Returns a formatted string of recent conversation to inject into the LLM prompt.
    Format:
        [You]: I am weak in dynamic programming
        [Mentor]: Got it. How long have you been practicing DSA?
        [You]: About 3 months...
    """
    messages = get_recent(session_id)
    if not messages:
        return ""

    lines = []
    for msg in messages:
        role_label = "You" if msg["role"] == "user" else "Mentor"
        # Truncate long messages to avoid bloating the prompt
        content = msg["content"][:200].strip()
        if len(msg["content"]) > 200:
            content += "…"
        lines.append(f"[{role_label}]: {content}")

    return "RECENT CONVERSATION:\n" + "\n".join(lines)


def clear_session(session_id: str):
    """Clear conversation history for a session (called on New Chat)."""
    if session_id in _sessions:
        del _sessions[session_id]


def get_session_count() -> int:
    return len(_sessions)
