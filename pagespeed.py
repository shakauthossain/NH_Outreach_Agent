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

        lighthouse = res.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        audits = lighthouse.get("audits", {})

        scores = {
            "performance": int(categories.get("performance", {}).get("score", 0) * 100),
            "accessibility": int(categories.get("accessibility", {}).get("score", 0) * 100),
            "seo": int(categories.get("seo", {}).get("score", 0) * 100),
            "best_practices": int(categories.get("best-practices", {}).get("score", 0) * 100),
        }

        metrics_data = {
            key: {
                "title": audits[key].get("title"),
                "displayValue": audits[key].get("displayValue"),
                "numericValue": audits[key].get("numericValue")
            }
            for key in [
                "first-contentful-paint",
                "largest-contentful-paint",
                "speed-index",
                "total-blocking-time",
                "cumulative-layout-shift"
            ]
            if key in audits
        }

        diagnostics_data = {
            key: audits[key] for key in [
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
            ] if key in audits
        }

        screenshot_data_uri = audits.get("final-screenshot", {}).get("details", {}).get("data")
        screenshot_path = None

        if screenshot_data_uri:
            img_data = base64.b64decode(screenshot_data_uri.split(",")[1])
            domain = sanitize_domain(url)
            folder = os.path.join(STATIC_DIR, domain)
            os.makedirs(folder, exist_ok=True)
            filename = f"{domain}_{strategy}.png"
            filepath = os.path.join(folder, filename)

            with open(filepath, "wb") as f:
                f.write(img_data)

            # ✅ Generate a public URL instead of local file path
            HF_SPACE_URL = "https://notionhive-ai-nh-outreach-agent.hf.space"
            screenshot_path = f"{HF_SPACE_URL}/static/{domain}/{filename}"

        return scores, screenshot_path, diagnostics_data, metrics_data

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

        scores_web, screenshot_web, _, metrics_web = get_pagespeed_score_and_screenshot(lead.website_url, "desktop")
        scores_mob, screenshot_mob, diagnostics_mob, metrics_mob = get_pagespeed_score_and_screenshot(lead.website_url, "mobile")

        if scores_web:
            lead.website_speed_web = scores_web["performance"]
        if scores_mob:
            lead.website_speed_mobile = scores_mob["performance"]
        if screenshot_web:
            lead.screenshot_url = screenshot_web
        if diagnostics_mob:
            lead.pagespeed_diagnostics = diagnostics_mob
        if metrics_web:
            lead.pagespeed_metrics_desktop = metrics_web
        if metrics_mob:
            lead.pagespeed_metrics_mobile = metrics_mob

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

    scores_web, screenshot_web, _, metrics_web = get_pagespeed_score_and_screenshot(lead.website_url, "desktop")
    scores_mob, screenshot_mob, diagnostics_mob, metrics_mob = get_pagespeed_score_and_screenshot(lead.website_url, "mobile")

    if scores_web:
        lead.website_speed_web = scores_web["performance"]
    if scores_mob:
        lead.website_speed_mobile = scores_mob["performance"]
    if screenshot_web:
        lead.screenshot_url = screenshot_web
    if diagnostics_mob:
        lead.pagespeed_diagnostics = diagnostics_mob
    if metrics_web:
        lead.pagespeed_metrics_desktop = metrics_web
        print(f"\n🔍 Desktop metrics for {lead.website_url}:")
        for k, v in metrics_web.items():
            print(f"  {v['title']}: {v['displayValue']} ({v['numericValue']})")
    if metrics_mob:
        lead.pagespeed_metrics_mobile = metrics_mob
        print(f"\n📱 Mobile metrics for {lead.website_url}:")
        for k, v in metrics_mob.items():
            print(f"  {v['title']}: {v['displayValue']} ({v['numericValue']})")

    if scores_web or scores_mob:
        db.commit()
    db.close()
    return (
        scores_web["performance"] if scores_web else None,
        scores_mob["performance"] if scores_mob else None
    )