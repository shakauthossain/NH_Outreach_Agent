# punchline.py
import os
import random
import re
from typing import List, Tuple, Dict, Any
from langchain_groq import ChatGroq

# Constants for punchline generation
MAX_WORDS = 35
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "your_groq_api_key")

PROVENANCE_NATURAL = {
    "home":  ["on your homepage", "in your main pitch", "right up front"],
    "about": ["on your About page", "in your story"],
    "services": ["across your services", "in how you position the offer"],
    "cases": ["in your case work", "in your client stories", "across the case studies"],
    "portfolio": ["through the portfolio", "across your work"],
    "clients": ["among your client logos", "in the clientele you show"],
    "blog":  ["in a recent post", "on the blog", "in your writing"],
    "news":  ["in your latest update", "in the recent press", "in news/press"],
    "generic": ["on your site"]
}

SYSTEM_RULES = (
    "You write the opening line for a cold email.\n"
    f"Write ONE punchy, human line (1–2 sentences, max {MAX_WORDS} words).\n"
    "Be specific, flattering, and focused on THEM (not us). No clichés.\n"
    "Paraphrase; do not copy snippets. Mention WHERE naturally if useful (e.g., on your homepage, in your case study, on your blog).\n"
    "Prefer recency > case/results > awards/clients > hero.\n"
    "Vary style; do not sound templated. Output only the line."
)

# Function to generate punchlines
def generate_punchlines(company: str, evidence: List[Tuple[str, str]], k: int = 3, kinds: List[str] = None) -> List[Dict[str, Any]]:
    """Generates punchlines based on evidence and company."""
    
    if kinds is None:
        kinds = ["news", "blog", "cases", "clients", "services", "home", "about", "generic"]

    # Flatten the where_labels list to ensure it's a list of strings
    where_labels = [label for kind in kinds for label in PROVENANCE_NATURAL.get(kind, ["on your site"])]

    # Construct messages for Groq API
    snippets = [txt for (_k, txt) in evidence]  # Unpacking the tuple into _k (signal) and txt (link)
    messages = [{
        "role": "system",
        "content": SYSTEM_RULES
    }, {
        "role": "user",
        "content": f"Company: {company}\nWhere to reference: {', '.join(where_labels)}\nGenerate punchlines for {', '.join(kinds)}."
    }]

    # Use Groq API for punchline generation
    groq_client = ChatGroq(model_name=GROQ_MODEL, temperature=0.8, groq_api_key=GROQ_API_KEY)
    raw = []
    while len(raw) < k:
        out = groq_client.invoke(messages)
        line = (out.content or "").strip()
        if line and not line.endswith((".", "!", "?")):
            line += "."
        if line not in raw:
            raw.append(line)

    return [{"line": line, "score": random.random()} for line in raw]