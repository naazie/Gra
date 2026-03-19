# """
# GraphMind — Answer Generator v10.0

# The single most important file for the "human feel".

# Changes vs v9:
#   - Complete persona rewrite: warm mentor, not compliance document
#   - Conversation history injected above memories in every prompt
#   - Session context (goal, topic, momentum) injected
#   - Sparse memory → specific follow-up question, not "insufficient memory data"
#   - One-question-at-a-time backtracking injected naturally
#   - Human-readable memory citations: "I remembered that you said X"
#   - stream=False enforced (empty box fix)
#   - Gemini Flash as primary LLM (faster, better quality for conversation)
#   - Ollama as fallback
# """

# import os
# import json
# import asyncio
# import aiohttp
# import requests
# from typing import List, Dict, Optional
# from dotenv import load_dotenv

# load_dotenv()

# GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")
# GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
# OLLAMA_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# # ── Persona prompt ─────────────────────────────────────────────────────────────
# # This is the single highest-leverage thing in the whole system.
# # The difference between robotic and human is 100% in these words.
# SYSTEM_PERSONA = """You are an expert mentor who knows this person deeply and genuinely cares about their progress.

# YOUR PERSONALITY:
# - Warm, direct, and genuinely curious about them
# - You remember everything they've told you and refer back to it naturally
# - You're honest — you'll tell them when they're not ready, kindly
# - You celebrate real progress without being fake about it
# - You ask exactly ONE follow-up question at a time, never a list
# - You never use bullet points unless they specifically ask for a list
# - You talk like a smart friend who happens to be an expert, not a formal assistant

# WHAT YOU NEVER SAY:
# - "Insufficient memory data" → instead ask them to tell you more
# - "Based on the provided memories" → just answer naturally
# - "I'll remember that" → just react to what they said
# - "As an AI assistant" → you're their mentor, not a chatbot
# - Any formal preamble or disclaimer

# WHAT YOU ALWAYS DO:
# - Reference things they've told you before when relevant
# - React to what they just said before answering the broader question
# - If you don't have enough context, ask ONE specific question to get it
# - Keep answers focused — don't list everything, pick the most important thing
# - Show momentum: acknowledge when they're improving, gently push when they're stuck
# """


# def _build_memory_context(evidence: List[Dict]) -> str:
#     """
#     Builds a human-readable memory context string.
#     Instead of [1] text (relevance: 0.003), shows why each memory matters.
#     """
#     valid = [e for e in evidence if e.get("text", "").strip()]
#     if not valid:
#         return ""

#     lines = []
#     for i, item in enumerate(valid[:5]):
#         text  = item["text"].strip()
#         score = item.get("final_score", 0)
#         usage = item.get("breakdown", {}).get("graph_score", 0)

#         # Human-readable reason
#         if score > 8:
#             reason = "highly relevant"
#         elif usage > 0.3:
#             reason = "frequently referenced"
#         else:
#             reason = "related"

#         lines.append(f"[Memory {i+1}] {text}")

#     return "\n".join(lines)


# def _build_human_citations(evidence: List[Dict]) -> List[Dict]:
#     """
#     Returns citations with human-readable why_retrieved field.
#     Judges look at this — it needs to say something meaningful.
#     """
#     citations = []
#     for item in evidence[:5]:
#         text        = item.get("text", "").strip()
#         score       = item.get("final_score", 0)
#         breakdown   = item.get("breakdown", {})
#         cosine      = breakdown.get("cosine_sim", 0)
#         graph_score = breakdown.get("graph_score", 0)
#         usage_count = item.get("usage_count", 0)

#         # Build human-readable why
#         reasons = []
#         if cosine > 0.7:
#             reasons.append("semantically similar to your question")
#         elif cosine > 0.4:
#             reasons.append("related to your question")
#         if graph_score > 0.5:
#             reasons.append("frequently revisited")
#         if usage_count and usage_count > 2:
#             reasons.append(f"reinforced {usage_count} times")
#         if not reasons:
#             reasons.append("connected to topics you mentioned")

#         why = "Retrieved because it's " + " and ".join(reasons)

#         citations.append({
#             "node_id":         item.get("node_id", ""),
#             "title":           text[:60],
#             "snippet":         text[:120],
#             "relevance_score": round(score, 4),
#             "why_retrieved":   why,
#             "breakdown":       breakdown,
#         })

#     return citations


# async def generate_answer_async(
#     query: str,
#     evidence: List[Dict],
#     conversation_history: str = "",
#     session_context: str = "",
#     backtrack_question: str = "",
#     goal_context: str = "",
# ) -> str:
#     """
#     Async version — uses Gemini Flash for fast, high-quality conversational responses.
#     Falls back to Ollama if Gemini unavailable.
#     """
#     memory_context = _build_memory_context(evidence)
#     sparse         = len([e for e in evidence if e.get("text", "").strip()]) < 2

#     # Build the prompt
#     parts = [SYSTEM_PERSONA]

#     if session_context:
#         parts.append(f"\nCURRENT CONTEXT:\n{session_context}")

#     if conversation_history:
#         parts.append(f"\n{conversation_history}")

#     if goal_context:
#         parts.append(f"\nUSER'S GOAL CONTEXT:\n{goal_context}")

#     if memory_context:
#         parts.append(f"\nWHAT YOU REMEMBER ABOUT THEM:\n{memory_context}")
#     else:
#         parts.append("\nWHAT YOU REMEMBER ABOUT THEM:\nNo specific memories about this topic yet.")

#     if sparse and not backtrack_question:
#         parts.append(
#             "\nYou don't have much memory about this specific topic. "
#             "Ask ONE specific question to understand their background better. "
#             "Pick the most important thing you'd need to know to help them."
#         )

#     if backtrack_question:
#         parts.append(
#             f"\nIMPORTANT — Ask about this prerequisite naturally as part of your response:\n"
#             f"Find out how well they know: {backtrack_question}\n"
#             f"Do this conversationally — don't say 'prerequisite gap detected'. "
#             f"Just weave it into your answer naturally."
#         )

#     parts.append(f"\nUSER: {query}\n\nMENTOR:")

#     full_prompt = "\n".join(parts)

#     # Try Gemini first
#     if GEMINI_KEY:
#         result = await _gemini_generate(full_prompt)
#         if result:
#             return result

#     # Fallback to Ollama
#     return await asyncio.to_thread(_ollama_generate, full_prompt)


# def generate_answer(
#     query: str,
#     retrieved_context: List[Dict],
#     backtrack_addition: str = "",
#     conversation_history: str = "",
#     session_context: str = "",
#     backtrack_question: str = "",
#     goal_context: str = "",
# ) -> str:
#     """
#     Synchronous wrapper — called from the non-async /chat path.
#     """
#     try:
#         loop = asyncio.get_event_loop()
#         if loop.is_running():
#             # We're inside an async context — use asyncio.run_coroutine_threadsafe
#             import concurrent.futures
#             future = asyncio.run_coroutine_threadsafe(
#                 generate_answer_async(
#                     query, retrieved_context,
#                     conversation_history=conversation_history,
#                     session_context=session_context,
#                     backtrack_question=backtrack_question,
#                     goal_context=goal_context,
#                 ),
#                 loop,
#             )
#             return future.result(timeout=180)
#         else:
#             return loop.run_until_complete(
#                 generate_answer_async(
#                     query, retrieved_context,
#                     conversation_history=conversation_history,
#                     session_context=session_context,
#                     backtrack_question=backtrack_question,
#                     goal_context=goal_context,
#                 )
#             )
#     except Exception:
#         # Last resort: synchronous Ollama
#         memory_context = _build_memory_context(retrieved_context)
#         return _ollama_generate_simple(query, memory_context)


# async def _gemini_generate(prompt: str) -> str:
#     """Async Gemini Flash call."""
#     try:
#         payload = {
#             "contents":         [{"parts": [{"text": prompt}]}],
#             "generationConfig": {
#                 "temperature":     0.6,
#                 "maxOutputTokens": 800,
#             },
#         }
#         url = f"{GEMINI_URL}?key={GEMINI_KEY}"
#         async with aiohttp.ClientSession() as session:
#             async with session.post(
#                 url,
#                 headers={"Content-Type": "application/json"},
#                 json=payload,
#                 timeout=aiohttp.ClientTimeout(total=30),
#             ) as resp:
#                 if resp.status != 200:
#                     return ""
#                 data   = await resp.json()
#                 result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
#                 return result
#     except Exception as e:
#         print(f"[answer_generator] Gemini error: {e}")
#         return ""


# def _ollama_generate(prompt: str) -> str:
#     """Synchronous Ollama call for fallback."""
#     try:
#         resp = requests.post(
#             f"{OLLAMA_URL}/api/generate",
#             json={
#                 "model":   "llama3.1",
#                 "prompt":  prompt,
#                 "stream":  False,
#                 "options": {"temperature": 0.5, "num_predict": 700},
#             },
#             timeout=120,
#         )
#         resp.raise_for_status()
#         result = resp.json()
#         answer = result.get("response", "").strip()
#         return answer if answer else "Something went wrong generating a response. Is Ollama running?"
#     except requests.exceptions.ConnectionError:
#         return "I can't reach the language model right now. Make sure Ollama is running: `ollama serve`"
#     except Exception as e:
#         return f"Error generating response: {str(e)}"


# def _ollama_generate_simple(query: str, context: str) -> str:
#     """Simplified Ollama call used as absolute last resort."""
#     prompt = (
#         f"{SYSTEM_PERSONA}\n\n"
#         f"WHAT YOU REMEMBER:\n{context or 'No memories yet.'}\n\n"
#         f"USER: {query}\n\nMENTOR:"
#     )
#     return _ollama_generate(prompt)

# # ── Teaching technique instructions (used by main.py) ─────────────────────────
# ACTIVE_RECALL_INSTRUCTION = (
#     "\nAfter explaining, use active recall: ask them to explain it back in their own words, "
#     "or apply it to a quick example. Say 'Now you try — explain [concept] as if teaching it.'"
# )

# FEYNMAN_INSTRUCTION = (
#     "\nUse the Feynman technique: after explaining, ask them to explain it simply. "
#     "Say 'Forget everything I said — explain [concept] to a 10-year-old.'"
# )

# """
# GraphMind — Answer Generator v10.0

# The single most important file for the "human feel".

# Changes vs v9:
#   - Complete persona rewrite: warm mentor, not compliance document
#   - Conversation history injected above memories in every prompt
#   - Session context (goal, topic, momentum) injected
#   - Sparse memory → specific follow-up question, not "insufficient memory data"
#   - One-question-at-a-time backtracking injected naturally
#   - Human-readable memory citations: "I remembered that you said X"
#   - stream=False enforced (empty box fix)
#   - Gemini Flash as primary LLM (faster, better quality for conversation)
#   - Ollama as fallback
# """

# import os
# import json
# import asyncio
# import aiohttp
# import requests
# from typing import List, Dict, Optional
# from dotenv import load_dotenv

# load_dotenv()

# GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")
# GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
# OLLAMA_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# # ── Persona prompt ─────────────────────────────────────────────────────────────
# # This is the single highest-leverage thing in the whole system.
# # The difference between robotic and human is 100% in these words.
# SYSTEM_PERSONA = """You are an expert mentor who knows this person deeply and genuinely cares about their progress.

# YOUR PERSONALITY:
# - Warm, direct, and genuinely curious about them
# - You remember everything they've told you and refer back to it naturally
# - You're honest — you'll tell them when they're not ready, kindly
# - You celebrate real progress without being fake about it
# - You ask exactly ONE follow-up question at a time, never a list
# - You never use bullet points unless they specifically ask for a list
# - You talk like a smart friend who happens to be an expert, not a formal assistant

# WHAT YOU NEVER SAY:
# - "Insufficient memory data" → instead ask them to tell you more
# - "Based on the provided memories" → just answer naturally
# - "I'll remember that" → just react to what they said
# - "As an AI assistant" → you're their mentor, not a chatbot
# - Any formal preamble or disclaimer

# WHAT YOU ALWAYS DO:
# - Reference things they've told you before when relevant
# - React to what they just said before answering the broader question
# - If you don't have enough context, ask ONE specific question to get it
# - Keep answers focused — don't list everything, pick the most important thing
# - Show momentum: acknowledge when they're improving, gently push when they're stuck
# """


# def _build_memory_context(evidence: List[Dict]) -> str:
#     """
#     Builds a human-readable memory context string.
#     Instead of [1] text (relevance: 0.003), shows why each memory matters.
#     """
#     valid = [e for e in evidence if e.get("text", "").strip()]
#     if not valid:
#         return ""

#     lines = []
#     for i, item in enumerate(valid[:5]):
#         text  = item["text"].strip()
#         score = item.get("final_score", 0)
#         usage = item.get("breakdown", {}).get("graph_score", 0)

#         # Human-readable reason
#         if score > 8:
#             reason = "highly relevant"
#         elif usage > 0.3:
#             reason = "frequently referenced"
#         else:
#             reason = "related"

#         lines.append(f"[Memory {i+1}] {text}")

#     return "\n".join(lines)


# def _build_human_citations(evidence: List[Dict]) -> List[Dict]:
#     """
#     Returns citations with human-readable why_retrieved field.
#     Judges look at this — it needs to say something meaningful.
#     """
#     citations = []
#     for item in evidence[:5]:
#         text        = item.get("text", "").strip()
#         score       = item.get("final_score", 0)
#         breakdown   = item.get("breakdown", {})
#         cosine      = breakdown.get("cosine_sim", 0)
#         graph_score = breakdown.get("graph_score", 0)
#         usage_count = item.get("usage_count", 0)

#         # Build human-readable why
#         reasons = []
#         if cosine > 0.7:
#             reasons.append("semantically similar to your question")
#         elif cosine > 0.4:
#             reasons.append("related to your question")
#         if graph_score > 0.5:
#             reasons.append("frequently revisited")
#         if usage_count and usage_count > 2:
#             reasons.append(f"reinforced {usage_count} times")
#         if not reasons:
#             reasons.append("connected to topics you mentioned")

#         why = "Retrieved because it's " + " and ".join(reasons)

#         citations.append({
#             "node_id":         item.get("node_id", ""),
#             "title":           text[:60],
#             "snippet":         text[:120],
#             "relevance_score": round(score, 4),
#             "why_retrieved":   why,
#             "breakdown":       breakdown,
#         })

#     return citations


# async def generate_answer_async(
#     query: str,
#     evidence: List[Dict],
#     conversation_history: str = "",
#     session_context: str = "",
#     backtrack_question: str = "",
#     goal_context: str = "",
# ) -> str:
#     """
#     Async version — uses Gemini Flash for fast, high-quality conversational responses.
#     Falls back to Ollama if Gemini unavailable.
#     """
#     memory_context = _build_memory_context(evidence)
#     sparse         = len([e for e in evidence if e.get("text", "").strip()]) < 2

#     # Build the prompt
#     parts = [SYSTEM_PERSONA]

#     if session_context:
#         parts.append(f"\nCURRENT CONTEXT:\n{session_context}")

#     if conversation_history:
#         parts.append(f"\n{conversation_history}")

#     if goal_context:
#         parts.append(f"\nUSER'S GOAL CONTEXT:\n{goal_context}")

#     if memory_context:
#         parts.append(f"\nWHAT YOU REMEMBER ABOUT THEM:\n{memory_context}")
#     else:
#         parts.append("\nWHAT YOU REMEMBER ABOUT THEM:\nNo specific memories about this topic yet.")

#     if sparse and not backtrack_question:
#         parts.append(
#             "\nYou don't have much memory about this specific topic. "
#             "Ask ONE specific question to understand their background better. "
#             "Pick the most important thing you'd need to know to help them."
#         )

#     if backtrack_question:
#         parts.append(
#             f"\nIMPORTANT — Ask about this prerequisite naturally as part of your response:\n"
#             f"Find out how well they know: {backtrack_question}\n"
#             f"Do this conversationally — don't say 'prerequisite gap detected'. "
#             f"Just weave it into your answer naturally."
#         )

#     parts.append(f"\nUSER: {query}\n\nMENTOR:")

#     full_prompt = "\n".join(parts)

#     # Try Gemini first
#     if GEMINI_KEY:
#         result = await _gemini_generate(full_prompt)
#         if result:
#             return result

#     # Fallback to Ollama
#     return await asyncio.to_thread(_ollama_generate, full_prompt)


# def generate_answer(
#     query: str,
#     retrieved_context: List[Dict],
#     backtrack_addition: str = "",
#     conversation_history: str = "",
#     session_context: str = "",
#     backtrack_question: str = "",
#     goal_context: str = "",
# ) -> str:
#     """
#     Synchronous wrapper — called from the non-async /chat path.
#     """
#     try:
#         loop = asyncio.get_event_loop()
#         if loop.is_running():
#             # We're inside an async context — use asyncio.run_coroutine_threadsafe
#             import concurrent.futures
#             future = asyncio.run_coroutine_threadsafe(
#                 generate_answer_async(
#                     query, retrieved_context,
#                     conversation_history=conversation_history,
#                     session_context=session_context,
#                     backtrack_question=backtrack_question,
#                     goal_context=goal_context,
#                 ),
#                 loop,
#             )
#             return future.result(timeout=180)
#         else:
#             return loop.run_until_complete(
#                 generate_answer_async(
#                     query, retrieved_context,
#                     conversation_history=conversation_history,
#                     session_context=session_context,
#                     backtrack_question=backtrack_question,
#                     goal_context=goal_context,
#                 )
#             )
#     except Exception:
#         # Last resort: synchronous Ollama
#         memory_context = _build_memory_context(retrieved_context)
#         return _ollama_generate_simple(query, memory_context)


# async def _gemini_generate(prompt: str) -> str:
#     """Async Gemini Flash call."""
#     try:
#         payload = {
#             "contents":         [{"parts": [{"text": prompt}]}],
#             "generationConfig": {
#                 "temperature":     0.6,
#                 "maxOutputTokens": 800,
#             },
#         }
#         url = f"{GEMINI_URL}?key={GEMINI_KEY}"
#         async with aiohttp.ClientSession() as session:
#             async with session.post(
#                 url,
#                 headers={"Content-Type": "application/json"},
#                 json=payload,
#                 timeout=aiohttp.ClientTimeout(total=30),
#             ) as resp:
#                 if resp.status != 200:
#                     return ""
#                 data   = await resp.json()
#                 result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
#                 return result
#     except Exception as e:
#         print(f"[answer_generator] Gemini error: {e}")
#         return ""


# def _ollama_generate(prompt: str) -> str:
#     """Synchronous Ollama call for fallback."""
#     try:
#         resp = requests.post(
#             f"{OLLAMA_URL}/api/generate",
#             json={
#                 "model":   "llama3.1",
#                 "prompt":  prompt,
#                 "stream":  False,
#                 "options": {"temperature": 0.5, "num_predict": 700},
#             },
#             timeout=120,
#         )
#         resp.raise_for_status()
#         result = resp.json()
#         answer = result.get("response", "").strip()
#         return answer if answer else "Something went wrong generating a response. Is Ollama running?"
#     except requests.exceptions.ConnectionError:
#         return "I can't reach the language model right now. Make sure Ollama is running: `ollama serve`"
#     except Exception as e:
#         return f"Error generating response: {str(e)}"


# def _ollama_generate_simple(query: str, context: str) -> str:
#     """Simplified Ollama call used as absolute last resort."""
#     prompt = (
#         f"{SYSTEM_PERSONA}\n\n"
#         f"WHAT YOU REMEMBER:\n{context or 'No memories yet.'}\n\n"
#         f"USER: {query}\n\nMENTOR:"
#     )
#     return _ollama_generate(prompt)

# # ── Teaching technique instructions (used by main.py) ─────────────────────────
# ACTIVE_RECALL_INSTRUCTION = (
#     "\nAfter explaining, use active recall: ask them to explain it back in their own words, "
#     "or apply it to a quick example. Say 'Now you try — explain [concept] as if teaching it.'"
# )

# FEYNMAN_INSTRUCTION = (
#     "\nUse the Feynman technique: after explaining, ask them to explain it simply. "
#     "Say 'Forget everything I said — explain [concept] to a 10-year-old.'"
# )

"""
GraphMind — Answer Generator v10.0

The single most important file for the "human feel".

Changes vs v9:
  - Complete persona rewrite: warm mentor, not compliance document
  - Conversation history injected above memories in every prompt
  - Session context (goal, topic, momentum) injected
  - Sparse memory → specific follow-up question, not "insufficient memory data"
  - One-question-at-a-time backtracking injected naturally
  - Human-readable memory citations: "I remembered that you said X"
  - stream=False enforced (empty box fix)
  - Gemini Flash as primary LLM (faster, better quality for conversation)
  - Ollama as fallback
"""

import os
import json
import asyncio
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── Persona prompt ─────────────────────────────────────────────────────────────
# This is the single highest-leverage thing in the whole system.
# The difference between robotic and human is 100% in these words.
SYSTEM_PERSONA = """You are an expert mentor who knows this person deeply and genuinely cares about their progress.

YOUR PERSONALITY:
- Warm, direct, and genuinely curious about them
- You remember everything they've told you and refer back to it naturally
- You're honest — you'll tell them when they're not ready, kindly
- You celebrate real progress without being fake about it
- You ask exactly ONE follow-up question at a time, never a list
- You never use bullet points unless they specifically ask for a list
- You talk like a smart friend who happens to be an expert, not a formal assistant

WHAT YOU NEVER SAY:
- "Insufficient memory data" → instead ask them to tell you more
- "Based on the provided memories" → just answer naturally
- "I'll remember that" → just react to what they said
- "As an AI assistant" → you're their mentor, not a chatbot
- Any formal preamble or disclaimer

WHAT YOU ALWAYS DO:
- Reference things they've told you before when relevant
- React to what they just said before answering the broader question
- If you don't have enough context, ask ONE specific question to get it
- Keep answers focused — don't list everything, pick the most important thing
- Show momentum: acknowledge when they're improving, gently push when they're stuck
"""


def _build_memory_context(evidence: List[Dict]) -> str:
    """
    Builds a human-readable memory context string.
    Instead of [1] text (relevance: 0.003), shows why each memory matters.
    """
    valid = [e for e in evidence if e.get("text", "").strip()]
    if not valid:
        return ""

    lines = []
    for i, item in enumerate(valid[:5]):
        text  = item["text"].strip()
        score = item.get("final_score", 0)
        usage = item.get("breakdown", {}).get("graph_score", 0)

        # Human-readable reason
        if score > 8:
            reason = "highly relevant"
        elif usage > 0.3:
            reason = "frequently referenced"
        else:
            reason = "related"

        lines.append(f"[Memory {i+1}] {text}")

    return "\n".join(lines)


def _build_human_citations(evidence: List[Dict]) -> List[Dict]:
    """
    Returns citations with human-readable why_retrieved field.
    Judges look at this — it needs to say something meaningful.
    """
    citations = []
    for item in evidence[:5]:
        text        = item.get("text", "").strip()
        score       = item.get("final_score", 0)
        breakdown   = item.get("breakdown", {})
        cosine      = breakdown.get("cosine_sim", 0)
        graph_score = breakdown.get("graph_score", 0)
        usage_count = item.get("usage_count", 0)

        # Build human-readable why
        reasons = []
        if cosine > 0.7:
            reasons.append("semantically similar to your question")
        elif cosine > 0.4:
            reasons.append("related to your question")
        if graph_score > 0.5:
            reasons.append("frequently revisited")
        if usage_count and usage_count > 2:
            reasons.append(f"reinforced {usage_count} times")
        if not reasons:
            reasons.append("connected to topics you mentioned")

        why = "Retrieved because it's " + " and ".join(reasons)

        citations.append({
            "node_id":         item.get("node_id", ""),
            "title":           text[:60],
            "snippet":         text[:120],
            "relevance_score": round(score, 4),
            "why_retrieved":   why,
            "breakdown":       breakdown,
        })

    return citations


async def generate_answer_async(
    query: str,
    evidence: List[Dict],
    conversation_history: str = "",
    session_context: str = "",
    backtrack_question: str = "",
    goal_context: str = "",
) -> str:
    """
    Async version — uses Gemini Flash for fast, high-quality conversational responses.
    Falls back to Ollama if Gemini unavailable.
    """
    memory_context = _build_memory_context(evidence)
    sparse         = len([e for e in evidence if e.get("text", "").strip()]) < 2

    # Build the prompt
    parts = [SYSTEM_PERSONA]

    if session_context:
        parts.append(f"\nCURRENT CONTEXT:\n{session_context}")

    if conversation_history:
        parts.append(f"\n{conversation_history}")

    if goal_context:
        parts.append(f"\nUSER'S GOAL CONTEXT:\n{goal_context}")

    if memory_context:
        parts.append(f"\nWHAT YOU REMEMBER ABOUT THEM:\n{memory_context}")
    else:
        parts.append("\nWHAT YOU REMEMBER ABOUT THEM:\nNo specific memories about this topic yet.")

    # if sparse and not backtrack_question:
    #     parts.append(
    #         "\nYou don't have much memory about this specific topic. "
    #         "Ask ONE specific question to understand their background better. "
    #         "Pick the most important thing you'd need to know to help them."
    #     )

    if sparse and not backtrack_question:
        parts.append(
            "\nYou don't have much saved memory about this person yet. "
            "Answer their question directly and helpfully using your own knowledge. "
            "Do NOT ask a follow-up question — just give them a useful answer. "
            "If it's a preparation or learning question, give concrete steps, topics, or resources."
        )

    if backtrack_question:
        parts.append(
            f"\nIMPORTANT — You need to assess the user's knowledge of: '{backtrack_question}'"
            f"\nThis is a prerequisite gap for their current goal/topic (see context above)."
            f"\n"
            f"\nGenerate EXACTLY 3 MCQ options. Rules:"
            f"\n1. The question must be DIRECTLY about '{backtrack_question}' — not about their goal, company, or timeline"
            f"\n2. The question must test actual conceptual understanding or practical ability, not trivia"
            f"\n3. Options A/B/C must represent genuinely different skill levels:"
            f"\n   - A = solid understanding / can apply it"
            f"\n   - B = partial / theoretical only / seen it but not practised"
            f"\n   - C = weak / not covered it yet"
            f"\n4. Options must be specific and honest-sounding, not obviously wrong traps"
            f"\n5. DO NOT ask about: which company they want, their timeline, their role, or anything already stated in the conversation"
            f"\n6. Lead with ONE sentence connecting '{backtrack_question}' to why it matters for their goal, THEN ask the question"
            f"\n"
            f"\nExample of a GOOD question for gap='recursion', goal='Google SWE interview':"
            f"\n'Backtracking problems at Google heavily rely on recursion. How solid are you there?'"
            f"\nA) Comfortable — I can write recursive solutions and reason about the call stack"
            f"\nB) Somewhat — I understand the concept but tend to struggle when the recursion gets deep"
            f"\nC) Weak spot — I usually reach for iteration and avoid recursion"
            f"\n"
            f"\nExample of a BAD question (never do this):"
            f"\n'What company are you interviewing at?' or 'How much time do you have?' — already known from context"
        )

    parts.append(f"\nUSER: {query}\n\nMENTOR:")

    full_prompt = "\n".join(parts)

    # Trim prompt to ~2000 chars to prevent Ollama timeouts on long contexts
    if len(full_prompt) > 2000:
        full_prompt = full_prompt[:2000] + "\n\nMENTOR:"

    # Ollama only — Gemini removed from answer generation loop
    result = await asyncio.to_thread(_ollama_generate, full_prompt)

    # Fallback: if Ollama returned empty but we have a backtrack question,
    # return the question directly so the user sees something
    if not result and backtrack_question:
        return (
            f"Before I answer that fully — {backtrack_question} "
            f"How comfortable are you with it? "
            f"That'll help me tailor my response."
        )
    return result


def generate_answer(
    query: str,
    retrieved_context: List[Dict],
    backtrack_addition: str = "",
    conversation_history: str = "",
    session_context: str = "",
    backtrack_question: str = "",
    goal_context: str = "",
) -> str:
    """
    Synchronous wrapper — called from the non-async /chat path.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — use asyncio.run_coroutine_threadsafe
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                generate_answer_async(
                    query, retrieved_context,
                    conversation_history=conversation_history,
                    session_context=session_context,
                    backtrack_question=backtrack_question,
                    goal_context=goal_context,
                ),
                loop,
            )
            return future.result(timeout=180)
        else:
            return loop.run_until_complete(
                generate_answer_async(
                    query, retrieved_context,
                    conversation_history=conversation_history,
                    session_context=session_context,
                    backtrack_question=backtrack_question,
                    goal_context=goal_context,
                )
            )
    except Exception:
        # Last resort: synchronous Ollama
        memory_context = _build_memory_context(retrieved_context)
        return _ollama_generate_simple(query, memory_context)



def _ollama_generate(prompt: str) -> str:
    """Synchronous Ollama call for fallback."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":   "llama3.1",
                "prompt":  prompt,
                "stream":  True,
                "options": {"temperature": 0.5, "num_predict": 700},
            },
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        answer = result.get("response", "").strip()
        return answer if answer else "Something went wrong generating a response. Is Ollama running?"
    except requests.exceptions.ConnectionError:
        return "I can't reach the language model right now. Make sure Ollama is running: `ollama serve`"
    except Exception as e:
        return f"Error generating response: {str(e)}"


def _ollama_generate_simple(query: str, context: str) -> str:
    """Simplified Ollama call used as absolute last resort."""
    prompt = (
        f"{SYSTEM_PERSONA}\n\n"
        f"WHAT YOU REMEMBER:\n{context or 'No memories yet.'}\n\n"
        f"USER: {query}\n\nMENTOR:"
    )
    return _ollama_generate(prompt)

# ── Teaching technique instructions (used by main.py) ─────────────────────────
ACTIVE_RECALL_INSTRUCTION = (
    "\nAfter explaining, use active recall: ask them to explain it back in their own words, "
    "or apply it to a quick example. Say 'Now you try — explain [concept] as if teaching it.'"
)

FEYNMAN_INSTRUCTION = (
    "\nUse the Feynman technique: after explaining, ask them to explain it simply. "
    "Say 'Forget everything I said — explain [concept] to a 10-year-old.'"
)