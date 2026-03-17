import os
import json
import requests
from typing import List, Dict

def generate_answer(query: str, retrieved_context: List[Dict]) -> str:
    """
    Synthesizes a response using local Ollama (Llama 3.1).
    Fulfills Requirement 1.6 (Auditability) with zero API costs.
    """
    # 1. Format context for the local LLM
    context_str = "\n".join([
        f"- Memory [{i+1}]: {item['text']} (Graph Score: {item.get('final_score', 'N/A')})" 
        for i, item in enumerate(retrieved_context)
    ])


    prompt = f"""
        You are GRAPHMIND, an intelligent memory-grounded assistant.

        Strict Rules:
        - Use ONLY the provided Context Memories.
        - Do NOT use outside knowledge.
        - If information is missing, clearly say: "Insufficient memory data."
        - If memories contradict, mention both with citations.
        - Always cite memory indices like [1], [2].

        Your job:
        1. Identify the user's intent (Learning Plan / Interview Practice / Clarification).
        2. Synthesize a concise, structured response grounded in memory.
        3. Prioritize high graph scores and recent memories when relevant.

        If the query is about learning:
        - Generate a clear step-by-step roadmap.
        - Skip topics the user already knows (if indicated).
        - Highlight prerequisites.

        If the query is about interview preparation:
        - Identify weak areas from memory.
        - Generate targeted follow-up questions or drills.
        - Reference past mistakes.

        Context Memories:
        {context_str}

        User Question:
        {query}

        Structured Answer:
        """
    # prompt = f"""
    # You are GRAPHMIND, a personal long-term memory assistant. 
    # Answer the user's question based ONLY on the provided memories below. 
    # If memories contradict, mention both. Always cite the Memory index (e.g., [1]).

    # Context Memories:
    # {context_str}

    # User Question: {query}
    
    # Final Answer:
    # """

    # 2. Local API Request to Ollama
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    url = f"{ollama_base}/api/generate"
    payload = {
        "model": "llama3.1",
        "prompt": prompt,
        "stream": False,  # Set to False for easier JSON parsing
        "options": {
            "temperature": 0.3  # Keep it grounded to the context
        }
    }

    try:
        print("🤖 Generating response locally via Ollama...")
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        return result.get('response', "Error: No response from local model.")

    except requests.exceptions.ConnectionError:
        return "❌ Error: Ollama is not running. Please start Ollama and try again."
    except Exception as e:
        return f"❌ Unexpected Error: {str(e)}"