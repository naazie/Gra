# import json
# import os
# from typing import List, Dict
# from google import genai
# from dotenv import load_dotenv 

# load_dotenv()


# client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# def extract_relationships(text: str) -> List[Dict]:
#     """
#     Uses an LLM to extract structured nodes and edges from raw text.
#     Supports dynamic relationship types beyond hardcoded regex.
#     """
#     prompt = f"""
#         You are an Intelligent Skill & Interview Graph Extractor.

#         Your task is to extract structured knowledge for a personalized learning path planner 
#         and interview preparation memory system.

#         Focus on identifying:

#         1. Skills and Topics
#         2. Prerequisite relationships (Topic A required before Topic B)
#         3. Learning Resources (courses, books, platforms)
#         4. User knowledge state (knows, learning, weak, mastered)
#         5. Interview Questions and User Answers
#         6. Mistakes or incorrect attempts
#         7. Company-specific preparation notes
#         8. Goals (e.g., "prepare for Google interview", "learn Machine Learning")

#         Allowed Relationship Types:
#         PREREQUISITE_OF
#         REQUIRES
#         COVERS
#         LEARNING_GOAL
#         HAS_RESOURCE
#         ATTEMPTED
#         ANSWERED
#         WEAK_IN
#         STRONG_IN
#         RELATED_TO
#         TARGETS_COMPANY
#         IMPROVES
#         CONTRADICTS

#         Instructions:
#         - Extract relationships relevant to learning paths or interview preparation.
#         - Infer prerequisite chains when clearly implied.
#         - Mark weak concepts if user expresses confusion, mistakes, or low confidence.
#         - Mark strong concepts if user shows mastery.
#         - Assign confidence score between 0.0 and 1.0.
#         - Do NOT hallucinate information not present in text.
#         - If nothing relevant exists, return an empty list.

#         Return ONLY valid JSON:
#         [
#         {{
#             "subj": "NodeA",
#             "rel": "RELATION_TYPE",
#             "obj": "NodeB",
#             "confidence": 0.85
#         }}
#         ]

#         Text: "{text}"
#         """

#     try:
#         # Fulfills requirement 1.2-B: structured extraction
#         response = client.models.generate_content(
#             model="gemini-2.5-flash",
#             contents=prompt,
#             config={"response_mime_type": "application/json"}
#         )
        
#         raw_text = response.text
#         if not raw_text:
#             print("LLM Error: Response text is empty/None")
#             return []

#         # 2. Now it's safe to use .replace()
#         clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        
#         triples = json.loads(clean_json)
#         return triples

#     except Exception as e:
#         print(f"LLM Extraction Error: {e}")
#         return []

import json
import os
import requests
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def extract_relationships(text: str) -> List[Dict]:
    """
    Uses Ollama (llama3.1) to extract structured knowledge graph triples.
    Returns list of {subj, rel, obj, confidence} dicts.
    """
    prompt = f"""You are a knowledge graph extractor for a learning path and interview prep system.

Extract relationships from the text below.

Allowed relationship types:
PREREQUISITE_OF, REQUIRES, COVERS, LEARNING_GOAL, HAS_RESOURCE,
ATTEMPTED, ANSWERED, WEAK_IN, STRONG_IN, RELATED_TO,
TARGETS_COMPANY, IMPROVES, CONTRADICTS

Rules:
- Only extract what is clearly stated in the text
- Do NOT hallucinate
- If nothing relevant exists, return []
- Assign confidence 0.0-1.0

Return ONLY a valid JSON array, no explanation, no markdown:
[{{"subj": "NodeA", "rel": "RELATION_TYPE", "obj": "NodeB", "confidence": 0.85}}]

Text: "{text}"

JSON:"""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":   "llama3.1",
                "prompt":  prompt,
                "stream":  False,
                "options": {"temperature": 0.0, "num_predict": 400},
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        if not raw:
            return []
        clean = raw.replace("```json", "").replace("```", "").strip()
        # Find the JSON array even if model adds preamble
        start = clean.find("[")
        end   = clean.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        triples = json.loads(clean[start:end])
        return triples if isinstance(triples, list) else []
    except Exception as e:
        print(f"[relation_extractor] Error: {e}")
        return []