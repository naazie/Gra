"""
GraphMind — Requirement Fetcher v11.0
Uses Ollama (llama3.1) directly — no Gemini dependency.
Cached per goal string to avoid repeated LLM calls.
"""

import os
import re
import json
import asyncio
import requests
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── In-memory cache — LLM called once per topic per server lifetime ───────────
_requirements_cache: Dict[str, List[str]] = {}
_company_cache:      Dict[str, Dict]      = {}


def _ollama_call(prompt: str) -> str:
    """Synchronous Ollama call — wrapped in asyncio.to_thread by callers."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":   "llama3.1",
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": 0.1, "num_predict": 300},
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"[requirement_fetcher] Ollama error: {e}")
        return ""


async def fetch_requirements(goal: str, use_cache: bool = True) -> List[str]:
    """
    Returns prerequisite topics for any goal. Cached per goal string.
    """
    cache_key = goal.lower().strip()[:100]

    if use_cache and cache_key in _requirements_cache:
        print(f"[requirement_fetcher] Cache hit: {cache_key[:40]}")
        return _requirements_cache[cache_key]

    prompt = f"""A person wants to: "{goal}"

List the key prerequisite knowledge areas they need.
Be specific and practical. Focus on CS/software engineering skills.
Return ONLY a JSON array of strings, max 10 items. No explanation, no markdown.

Example output: ["arrays", "recursion", "big-O notation", "dynamic programming"]

JSON array:"""

    raw = await asyncio.to_thread(_ollama_call, prompt)
    if not raw:
        return []

    try:
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            items  = json.loads(match.group())
            result = [
                str(i).strip().lower() for i in items
                if i is not None and str(i).strip()
            ]
            _requirements_cache[cache_key] = result
            return result
    except Exception:
        pass
    return []


async def fetch_company_requirements(company: str) -> Dict:
    """
    Fetches company-specific interview requirements. Cached per company.
    """
    cache_key = company.lower().strip()

    if cache_key in _company_cache:
        return _company_cache[cache_key]

    prompt = f"""What does {company} typically look for in software engineering interviews?

Return ONLY valid JSON, no markdown, no explanation:
{{"topics": ["topic1", "topic2"], "focus": "one sentence about their style", "tip": "one practical preparation tip"}}

JSON:"""

    raw    = await asyncio.to_thread(_ollama_call, prompt)
    default = {"topics": [], "focus": "", "tip": ""}

    if raw:
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                result = json.loads(match.group())
                _company_cache[cache_key] = result
                return result
        except Exception:
            pass

    return default


def cross_check_with_memory(
    required_topics: List[str],
    embedder,
    faiss_mgr,
    user_id: str,
    threshold: float = 0.60,
) -> Dict[str, bool]:
    """
    For each required topic, checks if the user has relevant memory via FAISS.
    """
    result = {}
    for topic in required_topics:
        if not topic or not isinstance(topic, str):
            result[topic] = False
            continue
        try:
            vec  = embedder.embed(topic)
            hits = faiss_mgr.search(user_id=user_id, query_vector=vec, top_k=1)
            result[topic] = bool(hits and hits[0]["cosine_similarity"] >= threshold)
        except Exception:
            result[topic] = False
    return result


def build_gap_context(
    goal: str,
    requirements: List[str],
    memory_check: Dict[str, bool],
) -> Dict:
    covered = [t for t in requirements if memory_check.get(t, False)]
    gaps    = [t for t in requirements if not memory_check.get(t, False)]
    return {
        "goal": goal, "requirements": requirements,
        "covered": covered, "gaps": gaps,
        "next_question": gaps[0] if gaps else None,
    }


def get_cache_stats() -> Dict:
    return {
        "requirements_cached": len(_requirements_cache),
        "companies_cached":    len(_company_cache),
    }