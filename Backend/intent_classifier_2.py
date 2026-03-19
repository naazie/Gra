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



def _deterministic_intent_override(text: str):
    """
    Fast rule-based overrides before Ollama.
    Prevents LLM misclassifying clear requests/questions as memory ingestion.
    """
    t = text.strip().lower()
    REQUEST_STARTERS = [
        "give me", "create", "make me", "generate", "show me",
        "what is", "what are", "how do", "how can", "explain",
        "roadmap", "study plan", "plan for", "help me", "suggest",
        "list ", "what should", "can you", "please ", "i need",
        "teach me", "walk me through", "tell me about", "summarise",
        "summarize", "compare", "difference between",
    ]
    if any(t.startswith(p) or (" " + p) in t for p in REQUEST_STARTERS):
        return {"is_query": True, "is_memory": False, "query_profile": "FACTUAL"}
    if "?" in text:
        return {"is_query": True, "is_memory": False, "query_profile": "FACTUAL"}
    return None


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
    # Fast deterministic check before Ollama to prevent misclassification
    override = _deterministic_intent_override(text)

    def _blocking_call_with_entity_extract():
        """Run Ollama to get entities even when intent is overridden."""
        return ollama.chat(
            model="llama3.1",
            format="json",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Input: {text}"},
            ],
            options={"temperature": 0},
        )

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
        response    = await asyncio.to_thread(_blocking_call_with_entity_extract)
        intent_data = json.loads(response["message"]["content"])
        # Apply deterministic override if applicable (keeps entities from LLM)
        if override:
            intent_data.update(override)
        return intent_data
    except Exception as e:
        print(f"[intent_classifier] Fallback triggered: {e}")
        fallback = {
            "is_memory":          True,
            "is_query":           "?" in text,
            "entities":           [],
            "query_profile":      "FACTUAL",
            "potential_conflict": False,
            "sentiment":          "NEUTRAL",
        }
        if override:
            fallback.update(override)
        return fallback