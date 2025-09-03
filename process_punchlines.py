
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from nhscraper import scrape_and_extract, pick_evidence, company_from_url
from punchline_llm import generate_punchlines
import os

app = FastAPI()

class PunchlineRequest(BaseModel):
    url: str
    company: str = None
    kinds: list = ["news", "blog", "cases", "clients", "services", "home", "about", "generic"]

@app.post("/process_punchline/")
async def process_punchline(request: PunchlineRequest):
    try:
        url = request.url
        company = request.company or company_from_url(url)

        # Scrape and extract signals
        pages, signals, path_used = scrape_and_extract(
            url,
            firecrawl_base=os.environ.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev"),
            firecrawl_key=os.environ.get("FIRECRAWL_API_KEY"),
            firecrawl_path=os.environ.get("FIRECRAWL_CRAWL_PATH", "/v1/crawl"),
        )

        # Pick evidence for LLM generation
        evidence = pick_evidence(signals, max_items=5)

        if not evidence:
            return {"message": "Couldn't fetch sufficient evidence for punchline generation."}

        # Generate punchlines
        ranked = generate_punchlines(company, evidence, k=3, kinds=request.kinds)

        return {"punchlines": ranked}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))