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

def get_pagespeed_score_and_screenshot(url: str, strategy: str) -> tuple[int | None, str | None]:
    try:
        api = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}&key={GOOGLE_API_KEY}"
        res = requests.get(api).json()
        score = res["lighthouseResult"]["categories"]["performance"]["score"]

        screenshot_data_uri = res["lighthouseResult"]["audits"]["final-screenshot"]["details"]["data"]
        img_data = base64.b64decode(screenshot_data_uri.split(",")[1])

        domain = sanitize_domain(url)
        folder = os.path.join(STATIC_DIR, domain)
        os.makedirs(folder, exist_ok=True)

        filename = f"{domain}_{strategy}.png"
        filepath = os.path.join(folder, filename)

        with open(filepath, "wb") as f:
            f.write(img_data)

        return int(score * 100), f"/{filepath}"
    except Exception as e:
        print(f"Error testing {url} ({strategy}): {e}")
        return None, None

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

        web_score, desktop_screenshot = get_pagespeed_score_and_screenshot(lead.website_url, "desktop")
        mob_score, mobile_screenshot = get_pagespeed_score_and_screenshot(lead.website_url, "mobile")

        if web_score is not None:
            lead.website_speed_web = web_score
        if mob_score is not None:
            lead.website_speed_mobile = mob_score

        # Save one of the screenshots, or both if you create separate fields
        if desktop_screenshot:
            lead.screenshot_url = desktop_screenshot

        if web_score is not None or mob_score is not None:
            db.commit()
            count += 1
            print(f"{lead.website_url} → W-{web_score}, M-{mob_score}, Screenshot: {desktop_screenshot}")
    db.close()
    return count

def refresh_speed_for_lead(lead_id: int) -> tuple[int | None, int | None]:
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
    if not lead or not lead.website_url:
        db.close()
        return None, None

    web_score, desktop_screenshot = get_pagespeed_score_and_screenshot(lead.website_url, "desktop")
    mob_score, mobile_screenshot = get_pagespeed_score_and_screenshot(lead.website_url, "mobile")

    if web_score is not None:
        lead.website_speed_web = web_score
    if mob_score is not None:
        lead.website_speed_mobile = mob_score
    if desktop_screenshot:
        lead.screenshot_url = desktop_screenshot

    if web_score is not None or mob_score is not None:
        db.commit()
    db.close()
    return web_score, mob_score
