# punchline_llm.py
import os, re, json, argparse
from typing import List, Tuple, Dict, Any
from langchain_groq import ChatGroq
import random

MAX_WORDS = int(os.environ.get("PUNCHLINE_MAX_WORDS", "35"))
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

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

EXAMPLES = [
    "Impressed by how you highlight sustainability on your homepage—it’s rare to see an agency tie green practices directly into their service offering.",
    "Your case study with Shopify brands stood out—it’s clear you’ve carved a strong niche in eCommerce growth.",
    "Loved your blog on AI in marketing—practical tips like that show how tuned-in you are to what SMBs need today."
]

def word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s))

def ngram_overlap(a: str, b: str, n: int = 4) -> float:
    def grams(s):
        toks = re.findall(r"\w+", s.lower())
        return set(tuple(toks[i:i+n]) for i in range(len(toks)-n+1))
    A, B = grams(a), grams(b)
    if not A or not B: return 0.0
    return len(A & B) / float(len(A))

def passes_qc(line: str, snippets: List[str]) -> bool:
    if not line: return False
    if word_count(line) > MAX_WORDS: return False
    low = line.lower()
    if any(p in low for p in ["i was browsing", "came across your website", "hope this email finds you"]):
        return False
    for s in snippets:
        if ngram_overlap(line, s, n=4) > 0.30:
            return False
    return True

def where_labels_from_evidence(evidence: List[Tuple[str,str]]) -> List[str]:
    kinds = {k for (k, _) in evidence}
    # map to natural phrases (keep max 2)
    labels = []
    for k in kinds:
        labels.extend(PROVENANCE_NATURAL.get(k, PROVENANCE_NATURAL["generic"])[:1])
    # dedupe, keep at most 2
    seen, out = set(), []
    for l in labels:
        low = l.lower()
        if low not in seen:
            out.append(l); seen.add(low)
        if len(out) >= 2: break
    return out

def detect_used_kind(line: str, fallback_kind: str) -> str:
    low = line.lower()
    for kind, phrases in PROVENANCE_NATURAL.items():
        for p in phrases:
            if p.lower() in low:
                return kind
    return fallback_kind

def score_line(line: str, used_kind: str) -> float:
    score = 0.0
    wc = word_count(line)
    if 10 <= wc <= MAX_WORDS: score += 1.5
    elif wc <= MAX_WORDS: score += 1.0
    # specificity
    if re.search(r"\b\d{4}\b|\b\d+%|\b\d+\b", line): score += 0.6
    if re.search(r"[A-Z][a-z]{2,}\s[A-Z][a-z]{2,}", line): score += 0.6
    # provenance mention
    if any(p in line.lower() for v in PROVENANCE_NATURAL.values() for p in [x.lower() for x in v]):
        score += 0.6
    priority = {"news": 1.2, "blog": 1.1, "cases": 1.0, "clients": 0.8, "services": 0.6, "home": 0.5, "about": 0.3, "generic": 0.2}
    score += priority.get(used_kind, 0.0)
    if re.search(r"\b(seems|maybe|probably|kind of|sort of)\b", line.lower()):
        score -= 0.3
    return score

def _groq(temperature: float):
    if not GROQ_API_KEY:
        raise RuntimeError("Set GROQ_API_KEY.")
    return ChatGroq(model_name=GROQ_MODEL, temperature=temperature, groq_api_key=GROQ_API_KEY)

def build_messages_with_kinds(company: str, where_labels: List[str], evidence: List[Tuple[str, str]], kinds: List[str]) -> list:
    examples = "\n".join(f"- {e}" for e in EXAMPLES)
    ev_lines = "\n".join(f"- [{k}] {t}" for (k, t) in evidence)
    where_str = ", ".join(where_labels) if where_labels else "on your site"

    # Use kinds to construct a prompt that asks the model to generate responses based on those kinds
    kinds_str = ", ".join(kinds)

    user = (
        f"Company: {company}\n"
        f"Where to reference (use one naturally if helpful): {where_str}\n\n"
        f"Examples of tone/style (do NOT copy wording):\n{examples}\n\n"
        f"Evidence (use 1–2 items at most, paraphrased):\n{ev_lines}\n\n"
        f"Generate punchlines for the following kinds: {kinds_str}. Ensure the generated punchlines include variety and address different aspects.\n\n"
        f"Return only the final line."
    )

    return [{"role": "system", "content": SYSTEM_RULES}, {"role": "user", "content": user}]


def generate_punchlines(company: str, evidence: List[Tuple[str, str]], k: int = 3, kinds: List[str] = None) -> List[Dict[str, Any]]:
    where_labels = where_labels_from_evidence(evidence)

    # If no kinds are provided, shuffle kinds to introduce variety
    if kinds is None:
        kinds = ["news", "blog", "cases", "clients", "services", "home", "about", "generic"]
    else:
        random.shuffle(kinds)  # Shuffle the provided kinds if needed

    snippets = [txt for (_k, txt) in evidence]

    # Build the system message based on the desired kinds
    messages = build_messages_with_kinds(company, where_labels, evidence, kinds)

    temps = [0.8, 0.6, 1.0, 0.7, 0.9]
    raw = []
    i = 0
    while len(raw) < k and i < len(temps) * 2:
        chat = _groq(temperature=temps[i % len(temps)])
        out = chat.invoke(messages)
        line = (out.content or "").strip()
        if line and not line.endswith((".", "!", "?")):
            line += "."
        line = re.sub(r"\s+", " ", line)
        if passes_qc(line, snippets):
            if all(line.lower() != r.lower() for r in raw):
                raw.append(line)
        i += 1

    while len(raw) < k:
        raw.append("Couldn’t access website—manual review needed.")

    scored = []
    for line in raw:
        used_kind = detect_used_kind(line, "generic")
        scored.append({"line": line, "used_kind": used_kind, "score": round(score_line(line, used_kind), 3)})
    scored.sort(key=lambda x: x["score"], reverse=True)

    return scored
