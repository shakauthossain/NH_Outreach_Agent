import os
import requests
import base64
from urllib.parse import urlparse
from dotenv import load_dotenv
from database import SessionLocal, LeadDB

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_PAGESPEED_KEY")
STATIC_DIR = "static"

def sanitize_domain(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc.replace(".", "_").replace(":", "_")

def get_pagespeed_score_and_screenshot(url: str, strategy: str) -> tuple[dict | None, str | None, dict | None, dict | None]:
    try:
        api = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}&key={GOOGLE_API_KEY}"
        res = requests.get(api).json()

        categories = res["lighthouseResult"]["categories"]
        scores = {
            "performance": int(categories["performance"]["score"] * 100),
            "accessibility": int(categories["accessibility"]["score"] * 100),
            "seo": int(categories["seo"]["score"] * 100),
            "best_practices": int(categories["best-practices"]["score"] * 100)
        }

        audits = res["lighthouseResult"]["audits"]

        # Extract key metrics (FCP, LCP, TBT, Speed Index, CLS)
        metric_keys = [
            "first-contentful-paint",
            "largest-contentful-paint",
            "speed-index",
            "total-blocking-time",
            "cumulative-layout-shift"
        ]
        metrics_data = {
            key: {
                "title": audits[key].get("title"),
                "displayValue": audits[key].get("displayValue"),
                "numericValue": audits[key].get("numericValue")
            }
            for key in metric_keys if key in audits
        }

        # Extract diagnostics
        diagnostics_keys = [
            "diagnostics",
            "network-rtt",
            "mainthread-work-breakdown",
            "bootup-time",
            "uses-rel-preconnect",
            "unminified-css",
            "unminified-javascript",
            "unused-css-rules",
            "uses-webp-images",
            "render-blocking-resources"
        ]
        diagnostics_data = {k: audits[k] for k in diagnostics_keys if k in audits}

        # Save screenshot
        screenshot_data_uri = audits["final-screenshot"]["details"]["data"]
        img_data = base64.b64decode(screenshot_data_uri.split(",")[1])

        domain = sanitize_domain(url)
        folder = os.path.join(STATIC_DIR, domain)
        os.makedirs(folder, exist_ok=True)

        filename = f"{domain}_{strategy}.png"
        filepath = os.path.join(folder, filename)

        with open(filepath, "wb") as f:
            f.write(img_data)

        return scores, f"/{filepath}", diagnostics_data, metrics_data

    except Exception as e:
        print(f"Error testing {url} ({strategy}): {e}")
        return None, None, None, None


def test_all_unspeeded_leads():
    db = SessionLocal()
    leads = db.query(LeadDB).filter(
        LeadDB.website_speed_web == None,
        LeadDB.website_speed_mobile == None
    ).all()
    count = 0

    for lead in leads:
        if not lead.website_url:
            continue

        scores_web, desktop_screenshot, _ = get_pagespeed_score_and_screenshot(lead.website_url, "desktop")
        scores_mob, mobile_screenshot, mob_diagnostics = get_pagespeed_score_and_screenshot(lead.website_url, "mobile")

        if scores_web:
            lead.website_speed_web = scores_web["performance"]
            # Optional: store other scores
            # lead.accessibility_score = scores_web["accessibility"]
            # lead.seo_score = scores_web["seo"]

        if scores_mob:
            lead.website_speed_mobile = scores_mob["performance"]
            # Optional: store other scores
            # lead.accessibility_score = scores_mob["accessibility"]
            # lead.seo_score = scores_mob["seo"]

        if desktop_screenshot:
            lead.screenshot_url = desktop_screenshot

        if mob_diagnostics:
            lead.pagespeed_diagnostics = mob_diagnostics

        if scores_web or scores_mob:
            db.commit()
            count += 1
            print(f"{lead.website_url} → W-{scores_web['performance'] if scores_web else '-'}, "
                  f"M-{scores_mob['performance'] if scores_mob else '-'}")
    db.close()
    return count

def refresh_speed_for_lead(lead_id: int) -> tuple[int | None, int | None]:
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
    if not lead or not lead.website_url:
        db.close()
        return None, None

    scores_web, desktop_screenshot, _ = get_pagespeed_score_and_screenshot(lead.website_url, "desktop")
    scores_mob, mobile_screenshot, mob_diagnostics = get_pagespeed_score_and_screenshot(lead.website_url, "mobile")

    if scores_web:
        lead.website_speed_web = scores_web["performance"]
    if scores_mob:
        lead.website_speed_mobile = scores_mob["performance"]
    if desktop_screenshot:
        lead.screenshot_url = desktop_screenshot
    if mob_diagnostics:
        lead.pagespeed_diagnostics = mob_diagnostics

    if scores_web or scores_mob:
        db.commit()
    db.close()
    return (
        scores_web["performance"] if scores_web else None,
        scores_mob["performance"] if scores_mob else None
    )
