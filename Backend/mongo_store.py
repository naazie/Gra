"""
GraphMind — MongoDB Chat History Store

Stores per-user chat sessions in MongoDB.
Each session is a document with messages array.
Falls back gracefully if MONGO_URI is not set.
"""

import os
from datetime import datetime, timezone
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

_client = None
_db     = None

def _get_db():
    global _client, _db
    if _db is not None:
        return _db
    uri = os.getenv("MONGO_URI")
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        _client.server_info()          # test connection
        _db = _client["graphmind"]
        print("[mongo] Connected to MongoDB")
        return _db
    except Exception as e:
        print(f"[mongo] Connection failed (chat history disabled): {e}")
        return None


def save_message(username: str, session_id: str, role: str, content: str,
                 metadata: dict = None):
    """
    Append a single message to the user's active session.
    role: 'user' | 'assistant'
    metadata: retrieval_ms, citations, entities, etc.
    """
    db = _get_db()
    if db is None:
        return

    doc = {
        "role":       role,
        "content":    content,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "metadata":   metadata or {},
    }

    try:
        db.sessions.update_one(
            {"username": username, "session_id": session_id},
            {
                "$push":        {"messages": doc},
                "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
                "$set":         {"updated_at": datetime.now(timezone.utc).isoformat()},
            },
            upsert=True,
        )
    except Exception as e:
        print(f"[mongo] save_message error: {e}")


def get_sessions(username: str, limit: int = 20) -> List[Dict]:
    """Return list of session summaries for the sidebar."""
    db = _get_db()
    if db is None:
        return []
    try:
        cursor = db.sessions.find(
            {"username": username},
            {"session_id": 1, "created_at": 1, "updated_at": 1,
             "messages": {"$slice": 1}},   # only first message for preview
        ).sort("updated_at", -1).limit(limit)
        sessions = []
        for s in cursor:
            first_msg = s.get("messages", [{}])[0]
            sessions.append({
                "session_id":  s["session_id"],
                "created_at":  s.get("created_at", ""),
                "updated_at":  s.get("updated_at", ""),
                "preview":     first_msg.get("content", "")[:80],
            })
        return sessions
    except Exception as e:
        print(f"[mongo] get_sessions error: {e}")
        return []


def get_session_messages(username: str, session_id: str) -> List[Dict]:
    """Return all messages for a specific session."""
    db = _get_db()
    if db is None:
        return []
    try:
        doc = db.sessions.find_one(
            {"username": username, "session_id": session_id},
            {"messages": 1}
        )
        return doc.get("messages", []) if doc else []
    except Exception as e:
        print(f"[mongo] get_session_messages error: {e}")
        return []


def delete_session(username: str, session_id: str) -> bool:
    """Delete a specific chat session."""
    db = _get_db()
    if db is None:
        return False
    try:
        result = db.sessions.delete_one(
            {"username": username, "session_id": session_id}
        )
        return result.deleted_count > 0
    except Exception as e:
        print(f"[mongo] delete_session error: {e}")
        return False


def is_available() -> bool:
    return _get_db() is not None
