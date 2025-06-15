import os
import requests
from dotenv import load_dotenv
from database import SessionLocal, LeadDB

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_PAGESPEED_KEY")

def get_pagespeed_score(url: str, strategy: str) -> int | None:
    try:
        api = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}&key={GOOGLE_API_KEY}"
        res = requests.get(api).json()
        score = res["lighthouseResult"]["categories"]["performance"]["score"]
        return int(score * 100)
    except Exception as e:
        print(f"Error testing {url} ({strategy}): {e}")
        return None

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
        web_score = get_pagespeed_score(lead.website_url, "desktop")
        mob_score = get_pagespeed_score(lead.website_url, "mobile")

        if web_score is not None:
            lead.website_speed_web = web_score
        if mob_score is not None:
            lead.website_speed_mobile = mob_score

        if web_score is not None or mob_score is not None:
            db.commit()
            count += 1
            print(f"{lead.website_url} → W-{web_score}, M-{mob_score}")
    db.close()
    return count

def refresh_speed_for_lead(lead_id: int) -> tuple[int | None, int | None]:
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
    if not lead or not lead.website_url:
        db.close()
        return None, None

    web_score = get_pagespeed_score(lead.website_url, "desktop")
    mob_score = get_pagespeed_score(lead.website_url, "mobile")

    if web_score is not None:
        lead.website_speed_web = web_score
    if mob_score is not None:
        lead.website_speed_mobile = mob_score

    if web_score is not None or mob_score is not None:
        db.commit()
    db.close()
    return web_score, mob_score