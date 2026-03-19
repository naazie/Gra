# """
# GraphMind — Memory Acknowledger v10.0

# When a user tells the system something (stores a memory), instead of
# returning the robotic "Memory stored and linked to your knowledge graph",
# this module generates a warm, natural reaction via a fast Gemini call.

# Example:
#   User: "I just finished the DP sheet and solved all 50 problems"
#   Before: "Memory stored and linked to your knowledge graph."
#   After:  "That's real progress — 50 problems is no small thing.
#            How did the harder ones feel? Did knapsack click for you
#            or are you still working through the intuition?"

# This is the difference between talking to a database and talking to a mentor.
# """

# import os
# import asyncio
# import aiohttp
# from typing import Optional
# from dotenv import load_dotenv

# load_dotenv()

# GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
# GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# # Fallback reactions when Gemini is unavailable
# _FALLBACKS = [
#     "Got it, I'll remember that.",
#     "Noted — that's helpful context.",
#     "Good to know. Keep going.",
#     "I've got that. What else is on your mind?",
# ]
# _fallback_idx = 0


# async def generate_acknowledgement(
#     user_text: str,
#     username: str,
#     recent_context: str = "",
#     duplicate: bool = False,
#     duplicate_existing: str = "",
# ) -> str:
#     """
#     Generates a warm, natural 1-2 sentence reaction to what the user just said.
#     Includes a relevant follow-up question when appropriate.
#     """
#     if duplicate:
#         return (
#             f"Sounds like something I already know about you — "
#             f"\"{duplicate_existing[:80]}\" is already in your memory. "
#             f"If this is something new or different, tell me more specifically."
#         )

#     if not GEMINI_KEY:
#         return _get_fallback()

#     prompt = f"""You are a sharp, warm mentor talking to {username}.
# {recent_context}

# The user just told you: "{user_text[:300]}"

# React in 1-2 sentences total. Be warm and genuine, not robotic.
# Acknowledge what they said specifically. Ask ONE relevant follow-up question
# that would help you understand their situation better.
# Do NOT say "I've stored that" or "noted" or "I'll remember" — just react naturally.
# Keep it under 60 words."""

#     try:
#         headers = {"Content-Type": "application/json"}
#         payload = {
#             "contents": [{"parts": [{"text": prompt}]}],
#             "generationConfig": {
#                 "temperature":     0.7,
#                 "maxOutputTokens": 120,
#             },
#         }
#         url = f"{GEMINI_URL}?key={GEMINI_KEY}"
#         async with aiohttp.ClientSession() as session:
#             async with session.post(
#                 url, headers=headers, json=payload,
#                 timeout=aiohttp.ClientTimeout(total=8)
#             ) as resp:
#                 if resp.status != 200:
#                     return _get_fallback()
#                 data  = await resp.json()
#                 reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
#                 return reply if reply else _get_fallback()
#     except Exception as e:
#         print(f"[acknowledger] Error: {e}")
#         return _get_fallback()


# def _get_fallback() -> str:
#     global _fallback_idx
#     reply = _FALLBACKS[_fallback_idx % len(_FALLBACKS)]
#     _fallback_idx += 1
#     return reply
"""
GraphMind — Memory Acknowledger v11.0

Generates a warm, natural reaction when a user stores a memory.
Uses Ollama (llama3.1) directly — no Gemini dependency.
"""

import os
import asyncio
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

_FALLBACKS = [
    "Got it, I'll remember that.",
    "Noted — that's helpful context.",
    "Good to know. Keep going.",
    "I've got that. What else is on your mind?",
]
_fallback_idx = 0


async def generate_acknowledgement(
    user_text: str,
    username: str,
    recent_context: str = "",
    duplicate: bool = False,
    duplicate_existing: str = "",
) -> str:
    if duplicate:
        return (
            f"Sounds like something I already know about you — "
            f"\"{duplicate_existing[:80]}\" is already in your memory. "
            f"If this is something new or different, tell me more specifically."
        )

    prompt = f"""You are a sharp, warm mentor talking to {username}.
{recent_context}

The user just told you: "{user_text[:300]}"

React in 1-2 sentences total. Be warm and genuine, not robotic.
Acknowledge what they said specifically. Ask ONE relevant follow-up question.
Do NOT say "I've stored that" or "noted" — just react naturally.
Keep it under 60 words.

MENTOR:"""

    try:
        result = await asyncio.to_thread(_ollama_call, prompt)
        return result if result else _get_fallback()
    except Exception as e:
        print(f"[acknowledger] Error: {e}")
        return _get_fallback()


def _ollama_call(prompt: str) -> str:
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":   "llama3.1",
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": 0.7, "num_predict": 120},
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"[acknowledger] Ollama error: {e}")
        return ""


def _get_fallback() -> str:
    global _fallback_idx
    reply = _FALLBACKS[_fallback_idx % len(_FALLBACKS)]
    _fallback_idx += 1
    return reply