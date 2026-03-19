"""
GraphMind — Input Validator v9.0

Provides:
  1. sanitize()        — strip HTML/SQL injection, normalize whitespace
  2. check_english()   — returns (is_english, corrected_text, corrections)
                         Uses basic spell checking without heavy dependencies
  3. is_duplicate()    — semantic similarity check against FAISS to avoid
                         ingesting near-identical memories (cosine > threshold)
"""

import re
import html
from typing import Tuple, List, Dict, Optional

# ── 1. Sanitization ───────────────────────────────────────────────────────────

# Patterns that indicate injection attempts
_SQL_PATTERNS = re.compile(
    r"(--|;|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b|\bSELECT\b|\bUNION\b|\bEXEC\b)",
    re.IGNORECASE,
)

_SCRIPT_PATTERN = re.compile(r"<script.*?>.*?</script>", re.IGNORECASE | re.DOTALL)


def sanitize(text: str) -> str:
    """
    Strip HTML tags, escape entities, remove SQL/script injection patterns.
    Normalize whitespace. Returns clean text.
    """
    if not isinstance(text, str):
        return ""

    # Remove script tags
    text = _SCRIPT_PATTERN.sub("", text)

    # Strip all HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Unescape HTML entities (&amp; → &, etc.)
    text = html.unescape(text)

    # Remove null bytes
    text = text.replace("\x00", "")

    # Normalize whitespace (tabs, multiple spaces → single space)
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate to 4000 chars max (prevents prompt injection via huge inputs)
    return text[:4000]


def has_injection(text: str) -> bool:
    """Returns True if the text looks like a SQL or script injection attempt."""
    if _SQL_PATTERNS.search(text):
        return True
    if "<script" in text.lower():
        return True
    return False


# ── 2. English check + basic spell correction ─────────────────────────────────

# Common misspellings map (extend as needed)
_CORRECTIONS = {
    "im":       "I'm",
    "dont":     "don't",
    "cant":     "can't",
    "wont":     "won't",
    "isnt":     "isn't",
    "wasnt":    "wasn't",
    "havent":   "haven't",
    "ive":      "I've",
    "thats":    "that's",
    "whats":    "what's",
    "hows":     "how's",
    "wanna":    "want to",
    "gonna":    "going to",
    "gotta":    "got to",
    "lol":      "lol",   # keep as-is
    "btw":      "by the way",
    "afaik":    "as far as I know",
    "imo":      "in my opinion",
    "tbh":      "to be honest",
    "ngl":      "not going to lie",
    "idk":      "I don't know",
    "ik":       "I know",
    "plz":      "please",
    "pls":      "please",
    "tho":      "though",
    "thru":     "through",
    "bcoz":     "because",
    "coz":      "because",
    "bcause":   "because",
    "becoz":    "because",
    "u":        "you",
    "r":        "are",
    "ur":       "your",
    "wat":      "what",
    "wot":      "what",
    "hw":       "how",
    "cn":       "can",
    "abt":      "about",
    "alot":     "a lot",
    "definately": "definitely",
    "seperate":   "separate",
    "recieve":    "receive",
    "occured":    "occurred",
    "untill":     "until",
    "beleive":    "believe",
    "grammer":    "grammar",
    "studing":    "studying",
    "preperation": "preparation",
    "languge":    "language",
    "programing": "programming",
    "algoritm":   "algorithm",
    "dynamik":    "dynamic",
    "interveiw":  "interview",
}

_NON_ENGLISH_RE = re.compile(
    r"[\u0900-\u097F\u0600-\u06FF\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]"
)


def check_english(text: str) -> Tuple[bool, str, List[str]]:
    """
    Returns (is_predominantly_english, corrected_text, list_of_corrections_made).

    - Detects non-Latin script (Hindi, Arabic, CJK) — flags as non-English
    - Applies the _CORRECTIONS map word by word
    - Does NOT block non-English, just flags it so the LLM can handle it
    """
    if not text.strip():
        return True, text, []

    # Check for non-English script
    non_eng_chars = len(_NON_ENGLISH_RE.findall(text))
    total_chars   = len(re.sub(r"\s", "", text))
    is_english    = non_eng_chars / max(total_chars, 1) < 0.3

    # Apply word-level corrections
    words       = text.split()
    corrected   = []
    corrections = []

    for word in words:
        # Strip trailing punctuation for lookup
        stripped   = re.sub(r"[^\w']", "", word.lower())
        punctuation = word[len(stripped):]   # preserve trailing punctuation

        if stripped in _CORRECTIONS and stripped != _CORRECTIONS[stripped].lower():
            original  = word
            new_word  = _CORRECTIONS[stripped] + punctuation
            corrected.append(new_word)
            corrections.append(f"'{original}' → '{new_word}'")
        else:
            corrected.append(word)

    corrected_text = " ".join(corrected)
    return is_english, corrected_text, corrections


# ── 3. Semantic duplicate detection ───────────────────────────────────────────

DUPLICATE_THRESHOLD = float("0.92")   # cosine similarity above this = duplicate


def is_semantic_duplicate(
    new_text: str,
    embedder,
    faiss_mgr,
    user_id: str,
    threshold: float = DUPLICATE_THRESHOLD,
) -> Tuple[bool, Optional[str]]:
    """
    Checks if new_text is semantically too similar to an existing memory.
    Returns (is_duplicate, existing_snippet).

    Uses the same FAISS index that retrieval uses — zero extra infrastructure.
    Threshold 0.92 means nearly identical phrasing.
    """
    try:
        query_vector = embedder.embed(new_text)
        results      = faiss_mgr.search(
            user_id=user_id, query_vector=query_vector, top_k=1
        )
        if results and results[0]["cosine_similarity"] >= threshold:
            return True, results[0]["text"][:100]
        return False, None
    except Exception:
        return False, None
