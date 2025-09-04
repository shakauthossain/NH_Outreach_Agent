import os
import re
import json
import time
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import requests
import tldextract
from playwright.async_api import async_playwright

# ---------- Config ----------
FOLLOW_PATHS = [
    r"/about", r"/team", r"/leadership",
    r"/services", r"/capabilities", r"/what-we-do",
    r"/work", r"/case-studies", r"/portfolio",
    r"/blog", r"/news", r"/press"
]
MAX_PAGES_PER_DOMAIN = 8
PLAYWRIGHT_TIMEOUT_MS = 15000

SOURCE_LABELS = {
    "home": "on your homepage",
    "about": "on your About page",
    "services": "on your services page",
    "cases": "in your case study",
    "portfolio": "in your portfolio",
    "clients": "among your client logos",
    "blog": "on your blog",
    "news": "in your news/press",
    "generic": "on your site",
}

# ---------- Utilities ----------
def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if not re.match(r"^https?://", url, flags=re.I):
        url = "https://" + url
    return re.sub(r"/+$", "", url)

def looks_thin(text: str) -> bool:
    return len(text or "") < 500 or len(set((text or ""))) < 50

def unique_lines(lines: List[str]) -> List[str]:
    dedup, seen = [], set()
    for ln in lines:
        key = ln.lower().strip()
        if key and key not in seen:
            dedup.append(ln)
            seen.add(key)
    return dedup

def classify_kind(url: str) -> str:
    path = url.split("://",1)[-1].split("/",1)[-1].lower()
    if path == "" or path in ("index.html",): return "home"
    if any(seg in path for seg in ["about","team","leadership"]): return "about"
    if any(seg in path for seg in ["service","capabilit","what-we-do"]): return "services"
    if any(seg in path for seg in ["case","work","success","story"]): return "cases"
    if any(seg in path for seg in ["portfolio"]): return "portfolio"
    if any(seg in path for seg in ["client","logo","partners"]): return "clients"
    if any(seg in path for seg in ["blog","insight","article"]): return "blog"
    if any(seg in path for seg in ["news","press","media","release"]): return "news"
    return "generic"

# ---------- Firecrawl Client ----------
class FirecrawlClient:
    def __init__(self, base_url: str, api_key: Optional[str], crawl_path: str = "/v1/crawl"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.crawl_path = crawl_path if crawl_path.startswith("/") else "/" + crawl_path

    def crawl(self, root_url: str, follow_paths: List[str], max_pages: int = MAX_PAGES_PER_DOMAIN, timeout_sec: int = 25) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "url": root_url,
            "maxDepth": 2,
            "maxPages": max_pages,
            "includePaths": follow_paths,
            "returnFormat": "markdown",
            "timeout": timeout_sec * 1000
        }
        endpoint = f"{self.base_url}{self.crawl_path}"
        try:
            resp = requests.post(endpoint, headers=headers, data=json.dumps(payload), timeout=timeout_sec+5)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {"__error__": f"firecrawl_error: {e}"}

        out, pages = {}, []
        if isinstance(data, dict):
            if "pages" in data: pages = data["pages"]
            elif "results" in data: pages = data["results"]
        if not pages and isinstance(data, list):
            pages = data
        for p in pages:
            u = p.get("url") or p.get("pageUrl") or root_url
            content = p.get("markdown") or p.get("content") or p.get("text") or ""
            out[u] = content or ""
        if not out: out["__error__"] = "firecrawl_no_pages_returned"
        return out

# ---------- Playwright fallback ----------
async def playwright_scrape_bundle(root_url: str, follow_paths: List[str]) -> Dict[str, str]:
    def should_visit(candidate: str, root: str) -> bool:
        if not candidate.startswith(root): return False
        path = candidate[len(root):]
        return any(re.match(fp + r"($|/)", path, flags=re.I) for fp in follow_paths) or path == ""
    
    extracted = {}
    
    # Use async_playwright instead of sync_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent="Mozilla/5.0")
        page = await ctx.new_page()
        
        async def visit(u: str):
            try:
                await page.goto(u, timeout=PLAYWRIGHT_TIMEOUT_MS, wait_until="load")
            except Exception:
                try: 
                    await page.goto(u, timeout=PLAYWRIGHT_TIMEOUT_MS, wait_until="domcontentloaded")
                except Exception as e:
                    extracted[u] = f"__error__: {e}"; return
            txt = await page.evaluate("""
                () => {
                    function visible(el) { const s = window.getComputedStyle(el); return s && s.visibility !== 'hidden' && s.display !== 'none'; }
                    const blocks = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
                    let n; while ((n = w.nextNode())) { const t = n.nodeValue.replace(/\\s+/g, ' ').trim(); if (t && visible(n.parentElement)) blocks.push(t); }
                    const h = [...document.querySelectorAll('h1,h2,h3')].map(e => e.innerText.trim());
                    return h.join('\\n') + '\\n' + blocks.join('\\n');
                }
            """)
            extracted[u] = txt or ""
        
        root = normalize_url(root_url)
        await visit(root)
        
        try:
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            links = [normalize_url(l) for l in links if l]
            links = unique_lines([l for l in links if should_visit(l, root)])
            for l in links[:MAX_PAGES_PER_DOMAIN-1]:
                await visit(l)
        except Exception:
            pass
        
        await browser.close()
    
    return extracted

# ---------- Hook extraction ----------
@dataclass
class HookSignals:
    hero: Optional[Tuple[str,str,str]] = None
    awards: List[Tuple[str,str,str]] = None
    clients: List[Tuple[str,str,str]] = None
    recency: List[Tuple[str,str,str]] = None
    niche: List[Tuple[str,str,str]] = None
    standout: List[Tuple[str,str,str]] = None

def extract_signals(page_texts: Dict[str, str]) -> HookSignals:
    items = []
    for url, text in page_texts.items():
        if str(text).startswith("__error__"): continue
        items.append((url, classify_kind(url), text))
    all_txt = "\n".join(t for _,_,t in items)
    # hero from homepage headings
    hero = None
    home_items = [(u,k,t) for (u,k,t) in items if k=="home"]
    home_txt = "\n".join(t for _,_,t in home_items) or all_txt
    headings = re.findall(r"(?m)^\s{0,3}(#+\s+.*|[A-Z][^\n]{0,80})$", home_txt)
    if headings:
        h = max(headings, key=lambda x: len(re.findall(r"\w", x)))[:160]
        hurl = home_items[0][0] if home_items else items[0][0]
        hero = (h.strip(), hurl, "home")
    def grab(p,t): return [m.group(0).strip() for m in re.finditer(p,t,flags=re.I)]
    awards, clients, recency, niche, standout = [],[],[],[],[]
    for url, kind, text in items:
        awards  += [(s,url,kind) for s in grab(r".{0,80}\b(?:award|winner|ISO[- ]?\d{4,5}|SOC[- ]?2|Top \d+)\b.{0,120}", text)]
        clients += [(s,url,kind) for s in grab(r".{0,80}\b(?:client|brands?|trusted by|partner)\b.{0,120}", text)]
        recency += [(s,url,kind) for s in grab(r".{0,80}\b(?:202[3-5]|Q[1-4]\s*20[23-5]|launch(?:ed)?|announc(?:e|ed)|releas(?:e|ed)|introduc(?:e|ed))\b.{0,120}", text)]
        niche   += [(s,url,kind) for s in grab(r".{0,80}\b(?:ecommerce|fintech|healthcare|edtech|SaaS|B2B|DTC|nonprofit|hospitality|real estate|logistics|AI|ML)\b.{0,120}", text)]
        standout+= [(s,url,kind) for s in grab(r".{0,80}\b(?:case stud(?:y|ies)|portfolio|results?|ROI|conversion|lift|benchmark)\b.{0,120}", text)]
    def uniq5(lst):
        out, seen = [], set()
        for s,u,k in lst:
            key = (s.lower().strip(), k)
            if key not in seen:
                out.append((s,u,k)); seen.add(key)
            if len(out) >= 5: break
        return out
    return HookSignals(
        hero=hero,
        awards=uniq5(awards),
        clients=uniq5(clients),
        recency=uniq5(recency),
        niche=uniq5(niche),
        standout=uniq5(standout),
    )

# ---------- Evidence picking for LLM ----------
def pick_evidence(signals: HookSignals, max_items: int = 5) -> List[Tuple[str,str]]:
    out = []
    kinds_order = ["recency", "standout", "awards", "niche", "hero"]
    for kind in kinds_order:
        if len(out) >= max_items:
            break
        bucket = getattr(signals, kind, [])
        for item in bucket:
            if len(item) == 3:
                txt, _url, kind_label = item
                out.append((kind_label, txt))
    return out


# ---------- Public API ----------
async def scrape_and_extract(url: str, firecrawl_base: str, firecrawl_key: str = None, firecrawl_path: str = "/v1/crawl") -> Tuple[Dict[str,str], HookSignals, str]:
    url = normalize_url(url)
    fc = FirecrawlClient(firecrawl_base, firecrawl_key, firecrawl_path)
    fc_pages = fc.crawl(url, FOLLOW_PATHS)
    fc_error = fc_pages.get("__error__")
    concat = "\n".join(v for k,v in fc_pages.items() if not k.startswith("__") and v)
    used = "FIRECRAWL_ONLY"
    pages = fc_pages
    if fc_error or looks_thin(concat):
        pw_pages = await playwright_scrape_bundle(url, FOLLOW_PATHS)
        if not looks_thin("\n".join(pw_pages.values())):
            pages = pw_pages
            used = "FIRECRAWL_FALLBACK_PLAYWRIGHT"
    signals = extract_signals(pages)
    return pages, signals, used

def company_from_url(url: str) -> str:
    try:
        ext = tldextract.extract(url)
        return (ext.domain or "company").capitalize()
    except Exception:
        return "Company"
