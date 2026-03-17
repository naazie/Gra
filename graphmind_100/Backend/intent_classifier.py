"""
GraphMind — Intent Classifier v4.0
Uses Llama 3.1 (local Ollama) to extract rich intent profile from user input.

Fix vs v3: ollama.chat is a blocking call. Running it directly inside an
async function blocks the FastAPI event loop. Wrapped in asyncio.to_thread
so the orchestrator's asyncio.gather can run FAISS + Neo4j in parallel.
"""

import ollama
import json
import asyncio


async def get_agentic_intent(text: str) -> dict:
    """
    Classifies user input into a rich intent profile.

    Returns:
    {
        "is_memory":          bool,   # True if user is stating a fact/experience
        "is_query":           bool,   # True if user is asking a question
        "entities":           list,   # Main topics/concepts mentioned (max 5)
        "query_profile":      str,    # "FACTUAL" | "RELATIONAL" | "NONE"
        "potential_conflict": bool,   # True if user may be changing their mind
        "sentiment":          str,    # "POSITIVE" | "NEUTRAL" | "NEGATIVE"
    }
    """
    system_prompt = (
        "You are a Knowledge Graph Controller. Analyze the user's input.\n"
        "Return a JSON object with these EXACT keys:\n"
        "- 'is_memory': boolean (True if stating a fact/experience to be stored)\n"
        "- 'is_query': boolean (True if asking a question)\n"
        "- 'entities': list of strings (The main topics/concepts mentioned, max 5)\n"
        "- 'query_profile': 'FACTUAL', 'RELATIONAL', or 'NONE'\n"
        "- 'potential_conflict': boolean (True if user is correcting/changing a previous stance)\n"
        "- 'sentiment': 'POSITIVE', 'NEUTRAL', or 'NEGATIVE'\n"
        "Return ONLY valid JSON, no explanation."
    )

    def _blocking_call():
        """Runs the synchronous ollama.chat in a thread pool."""
        return ollama.chat(
            model="llama3.1",
            format="json",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Input: {text}"},
            ],
            options={"temperature": 0},
        )

    try:
        # asyncio.to_thread prevents blocking the FastAPI event loop
        response    = await asyncio.to_thread(_blocking_call)
        intent_data = json.loads(response["message"]["content"])
        return intent_data
    except Exception as e:
        print(f"[intent_classifier] Fallback triggered: {e}")
        return {
            "is_memory":          True,
            "is_query":           "?" in text,
            "entities":           [],
            "query_profile":      "FACTUAL",
            "potential_conflict": False,
            "sentiment":          "NEUTRAL",
        }
