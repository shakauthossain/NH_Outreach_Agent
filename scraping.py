# scraping.py
import os
import re
import json
from typing import List, Tuple, Dict, Optional
from playwright.async_api import async_playwright
import requests

# Scraping service constants
FOLLOW_PATHS = [
    r"/about", r"/team", r"/leadership",
    r"/services", r"/capabilities", r"/what-we-do",
    r"/work", r"/case-studies", r"/portfolio",
    r"/blog", r"/news", r"/press"
]
MAX_PAGES_PER_DOMAIN = 8
PLAYWRIGHT_TIMEOUT_MS = 15000

# Normalize URL for uniformity
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

# Signal classification based on URL path
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

# Firecrawl client for scraping
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

# Scrape website and extract data, signals, and evidence
async def scrape_and_extract(url: str, firecrawl_base: str, firecrawl_key: str = None, firecrawl_path: str = "/v1/crawl") -> Tuple[Dict[str, str], List[str], List[Tuple[str, str]]]:
    """Scrapes the website and extracts relevant data and signals."""
    # Using Playwright or Firecrawl to scrape the pages
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=PLAYWRIGHT_TIMEOUT_MS)
        content = await page.content()

        # Example: Get links on the page
        links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        links = [normalize_url(l) for l in links if l]
        links = unique_lines(links)

        await browser.close()

    # Extract signals (e.g., what section the content belongs to)
    signals = [classify_kind(link) for link in links]  # Classify content by URL path

    # Picking evidence from the signals and URLs, ensuring the correct tuple format
    evidence = [(signal, link) for signal, link in zip(signals, links)]  # Ensure it's a list of (signal, link)

    return {"url": url, "content": content}, signals, evidence