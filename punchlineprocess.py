# main.py
import os, re, json, argparse, pandas as pd, tldextract
from typing import List, Tuple
from nhscraper import scrape_and_extract, pick_evidence, company_from_url
from punchline_llm import generate_punchlines

# ENV for Firecrawl
FIRECRAWL_BASE_URL = os.environ.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY  = "fc-135574cccbe141b5bcfe6c1a40d17cb9"
FIRECRAWL_PATH     = os.environ.get("FIRECRAWL_CRAWL_PATH", "/v1/crawl")

# In punchlineprocess.py

async def run_single(url: str, company: str = ""):
    # Await the asynchronous function scrape_and_extract
    pages, signals, path_used = await scrape_and_extract(
        url,
        firecrawl_base=FIRECRAWL_BASE_URL,
        firecrawl_key=FIRECRAWL_API_KEY,
        firecrawl_path=FIRECRAWL_PATH,
    )

    # Pick the evidence for LLM generation
    evidence = pick_evidence(signals, max_items=5)

    # If evidence is empty (site inaccessible), immediately return fallback lines
    if not evidence:
        return path_used, [
            {"line": "Couldn’t access website—manual review needed.", "used_kind": "generic", "score": 0.0},
            {"line": "Couldn’t access website—manual review needed.", "used_kind": "generic", "score": 0.0},
            {"line": "Couldn’t access website—manual review needed.", "used_kind": "generic", "score": 0.0}
        ]

    # If there's evidence, process through LLM with specific kinds
    if not company:
        company = company_from_url(url)

    # Specify the kinds you want to focus on
    kinds = ["news", "services", "blog"]  # Define the kinds you want

    # Pass the kinds to generate_punchlines
    ranked = generate_punchlines(company, evidence, k=3, kinds=kinds)  # Now it will generate punchlines with varied kinds

    return path_used, ranked



def main():
    parser = argparse.ArgumentParser(description="Main entry: scrape with Firecrawl/Playwright, then LLM punch lines via Groq.")
    parser.add_argument("--urls", nargs="*", help="One or more URLs to test.")
    parser.add_argument("--csv", help="CSV with columns: Company Name, First Name, Website, Customization")
    parser.add_argument("--out", help="Optional output CSV path (fills Customization with BEST line).")
    args = parser.parse_args()

    if args.urls:
        for u in args.urls:
            path_used, ranked = run_single(u)
            print(f"\n=== {u} ===")
            print(f"Path: {path_used}")
            for i, r in enumerate(ranked, 1):
                print(f"{i}) {r['line']}   [score={r['score']}, kind={r['used_kind']}]")
        return

    if args.csv:
        df = pd.read_csv(args.csv)
        required = ["Company Name", "First Name", "Website", "Customization"]
        for c in required:
            if c not in df.columns:
                raise ValueError(f"Missing required column: {c}")
        
        best_lines, alt1, alt2, paths = [], [], [], []
        for _, row in df.iterrows():
            url = str(row["Website"]).strip()
            company = str(row["Company Name"]).strip()
            if not url:
                best_lines.append("Couldn’t access website—manual review needed.")
                alt1.append("")
                alt2.append("")
                paths.append("N/A")
                continue
            path_used, ranked = run_single(url, company=company)
            paths.append(path_used)
            best_lines.append(ranked[0]["line"])
            alt1.append(ranked[1]["line"] if len(ranked) > 1 else "")
            alt2.append(ranked[2]["line"] if len(ranked) > 2 else "")
        
        df["Customization"] = best_lines
        df["Alt Line 1"] = alt1
        df["Alt Line 2"] = alt2
        df["Scrape Path"] = paths
        out_path = args.out or re.sub(r"\.csv$", "", args.csv) + "_out.csv"
        df.to_csv(out_path, index=False)
        print(f"Wrote: {out_path}")
        return

    parser.print_help()

if __name__ == "__main__":
    main()
