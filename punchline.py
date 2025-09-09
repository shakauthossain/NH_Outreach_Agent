# punchline.py
import os, re, json, argparse
from typing import List, Tuple, Dict, Any
import random
from dotenv import load_dotenv
from llm_provider import get_chat_groq
import time


load_dotenv()

# -------------------------
# Config
# -------------------------
MAX_WORDS = int(os.environ.get("PUNCHLINE_MAX_WORDS", "35"))

PROVENANCE_NATURAL: Dict[str, List[str]] = {
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

EXAMPLES = [
    "Impressed by how you highlight sustainability on your homepage—it’s rare to see an agency tie green practices directly into their service offering.",
    "Your case study with Shopify brands stood out—it’s clear you’ve carved a strong niche in eCommerce growth.",
    "Loved your blog on AI in marketing—practical tips like that show how tuned-in you are to what SMBs need today."
]

GOOD_EXAMPLES = [
    "Impressed by how you highlight sustainability on your homepage—it’s rare to see an agency tie green practices directly into their service offering.",
    "Your case study with Shopify brands stood out—it’s clear you’ve carved a strong niche in eCommerce growth.",
    "Loved your blog on AI in marketing—practical tips like that show how tuned-in you are to what SMBs need today."
]

BAD_EXAMPLES = [
    "I saw your website and it looks great.",
    "You seem like a good company doing nice work.",
    "I noticed you are an agency in New York."
]

BAD_PHRASES = [
    "i saw your website",
    "came across your website",
    "hope this email finds you",
    "you seem like a good company",
    "you are an agency in",
    "i noticed you are an agency",
    "looks great",
    "nice work",
]

BAD_REGEXES = [
    r"\bi noticed\b",
    r"\bi was browsing\b",
    r"\byour website looks\b",
    r"\byou (?:seem|seems)\b",
    r"\bwe (?:can|could|help)\b",
]

SYSTEM_RULES = (
    "You write the opening line for a cold email. Do not use clichés starting like I see, I like, I appreciate something like that.\n"
    f"Write ONE punchy, human line (1–2 sentences, max {MAX_WORDS} words).\n"
    "Be specific, flattering, and focused on THEM (not us). No clichés.\n"
    "Paraphrase; do not copy snippets. Mention WHERE naturally if useful (e.g., on your homepage, in your case study, on your blog).\n"
    "Prefer recency > case/results > awards/clients > hero.\n"
    "Vary style; do not sound templated. Output only the line.\n\n"
    "Good examples to emulate (tone/structure only):\n"
    f"- {GOOD_EXAMPLES[0]}\n- {GOOD_EXAMPLES[1]}\n- {GOOD_EXAMPLES[2]}\n\n"
    "Bad examples to avoid (do not produce anything similar):\n"
    f"- {BAD_EXAMPLES[0]}\n- {BAD_EXAMPLES[1]}\n- {BAD_EXAMPLES[2]}"
)

# -------------------------
# Helpers
# -------------------------
def word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s))

def ngram_overlap(a: str, b: str, n: int = 4) -> float:
    def grams(s):
        toks = re.findall(r"\w+", s.lower())
        return set(tuple(toks[i:i+n]) for i in range(len(toks)-n+1))
    A, B = grams(a), grams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / float(len(A))

def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def format_as_examples(lines: List[str]) -> str:
    styled = []
    for ln in lines:
        ln = _normalize(ln)
        if ln and not ln.endswith((".", "!", "?")):
            ln += "."
        styled.append(f"“{ln}”")
    return "\n\n".join(styled)

def passes_qc(line: str, snippets: List[str]) -> bool:
    if not line:
        return False
    if word_count(line) > MAX_WORDS:
        return False

    low = line.lower()

    if any(p in low for p in BAD_PHRASES):
        return False
    if any(re.search(rx, low) for rx in BAD_REGEXES):
        return False

    if "website" in low and not re.search(r"\b(homepage|blog|case|portfolio|clients|services|about|news)\b", low):
        return False

    for s in snippets:
        if ngram_overlap(line, s, n=4) > 0.30:
            return False

    has_specificity = (
        re.search(r"\b\d{4}\b|\b\d+%|\b\d+\b", line) or
        re.search(r"[A-Z][a-z]{2,}\s[A-Z][a-z]{2,}", line) or
        any(p in low for v in PROVENANCE_NATURAL.values() for p in [x.lower() for x in v])
    )
    if not has_specificity:
        return False

    return True

def where_labels_from_evidence(evidence: List[Tuple[str, str]]) -> List[str]:
    kinds = {k for (k, _) in evidence}
    labels: List[str] = []
    for k in kinds:
        labels.extend(PROVENANCE_NATURAL.get(k, PROVENANCE_NATURAL["generic"])[:1])
    seen, out = set(), []
    for l in labels:
        low = l.lower()
        if low not in seen:
            out.append(l); seen.add(low)
        if len(out) >= 2:
            break
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
    if 10 <= wc <= MAX_WORDS:
        score += 1.5
    elif wc <= MAX_WORDS:
        score += 1.0
    if re.search(r"\b\d{4}\b|\b\d+%|\b\d+\b", line):
        score += 0.6
    if re.search(r"[A-Z][a-z]{2,}\s[A-Z][a-z]{2,}", line):
        score += 0.6
    if any(p in line.lower() for v in PROVENANCE_NATURAL.values() for p in [x.lower() for x in v]):
        score += 0.6
    priority = {"news": 1.2, "blog": 1.1, "cases": 1.0, "clients": 0.8, "services": 0.6, "home": 0.5, "about": 0.3, "generic": 0.2}
    score += priority.get(used_kind, 0.0)
    if re.search(r"\b(seems|maybe|probably|kind of|sort of)\b", line.lower()):
        score -= 0.3
    return score

def _chat(temperature: float):
    # ✅ Same model & API via shared provider
    return get_chat_groq(temperature=temperature)

def normalize_evidence(evidence: Any) -> List[Tuple[str, str]]:
    norm: List[Tuple[str, str]] = []
    if not evidence:
        return norm
    for item in evidence:
        kind, text = None, None
        if isinstance(item, (list, tuple)):
            if len(item) >= 2:
                kind, text = item[0], item[1]
            elif len(item) == 1:
                kind, text = "generic", item[0]
        elif isinstance(item, dict):
            kind = item.get("kind") or item.get("k") or item.get("type") or "generic"
            text = (
                item.get("text") or item.get("t") or item.get("snippet")
                or item.get("content") or item.get("title") or ""
            )
        elif isinstance(item, str):
            kind, text = "generic", item

        kind = (kind or "generic")
        if isinstance(kind, str):
            kind = kind.strip().lower()
        else:
            kind = "generic"

        text = (text or "")
        if isinstance(text, str):
            text = text.strip()
        else:
            text = ""

        if text:
            norm.append((kind, text))
    return norm

def build_messages_with_kinds(company: str, where_labels: List[str], evidence: List[Tuple[str, str]], kinds: List[str]) -> list:
    examples = "\n".join(f"- {e}" for e in EXAMPLES)
    ev_lines = "\n".join(f"- [{k}] {t}" for (k, t) in evidence) if evidence else "- [generic] (no reliable snippets)"
    where_str = ", ".join(where_labels) if where_labels else "on your site"

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

# -------------------------
# Core
# -------------------------
def generate_punchlines(
    company: str,
    evidence: List[Any],
    k: int = 3,
    kinds: List[str] = None,
    return_format: str = "list"  # "list" | "examples_block"
) -> Any:
    norm_evidence: List[Tuple[str, str]] = normalize_evidence(evidence)
    where_labels = where_labels_from_evidence(norm_evidence)

    if kinds is None:
        kinds = ["news", "blog", "cases", "clients", "services", "home", "about", "generic"]
    else:
        random.shuffle(kinds)

    snippets = [txt for (_k, txt) in norm_evidence]
    messages = build_messages_with_kinds(company, where_labels, norm_evidence, kinds)

    temps = [0.8, 0.6, 1.0, 0.7, 0.9]
    raw: List[str] = []
    i = 0
    
    while len(raw) < k and i < len(temps) * 2:
        chat = _chat(temperature=temps[i % len(temps)])
        out = chat.invoke(messages)
        line = _normalize(out.content or "")
        if line and not line.endswith((".", "!", "?")):
            line += "."
        if passes_qc(line, snippets) and all(line.lower() != r.lower() for r in raw):
            raw.append(line)
        i += 1
        time.sleep(10)

    while len(raw) < k:
        raw.append("Couldn’t access website—manual review needed.")

    scored = []
    for line in raw:
        used_kind = detect_used_kind(line, "generic")
        scored.append({"line": line, "used_kind": used_kind, "score": round(score_line(line, used_kind), 3)})
    scored.sort(key=lambda x: x["score"], reverse=True)

    if return_format == "examples_block":
        return format_as_examples([x["line"] for x in scored[:k]])
    return scored