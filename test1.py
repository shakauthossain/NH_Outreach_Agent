import os
import requests
import time
from dotenv import load_dotenv
from typing import List
from sqlalchemy.orm import Session
from models import Lead
from database import SessionLocal, LeadDB

load_dotenv()

# Load credentials from .env
GoHighLevel_key = os.getenv("GOHIGHLEVEL_KEY")  # Make sure this is an agency-level key
Location_ID = os.getenv("GOHIGHLEVEL_LOCATION_ID")  # Must be copied from GHL URL (location slug)

CUSTOM_FIELDS_MAP = {
    "designation": "designation",
    "website_url": "website_url"
}

def extract_custom_field(contact, field_key):
    custom_fields = contact.get("customField", {})
    return custom_fields.get(field_key, "")

def fetch_gohighlevel_leads(desired_count: int = 20, per_page: int = 20) -> List[Lead]:
    url = "https://services.leadconnectorhq.com/contacts/"
    headers = {
        "Authorization": f"Bearer {GoHighLevel_key}",
        "Version": "2021-07-28",
        "Content-Type": "application/json"
    }

    db: Session = SessionLocal()
    leads: List[Lead] = []
    seen_ids = set()
    start_after_id = None
    max_attempts = 100
    attempts = 0

    while len(leads) < desired_count and attempts < max_attempts:
        params = {
            "locationId": Location_ID,
            "limit": per_page
        }
        if start_after_id:
            params["startAfterId"] = start_after_id

        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print("❌ GHL API error:", response.status_code, response.text)
            break

        data = response.json()
        contacts = data.get("contacts", [])

        if not contacts:
            print("🚫 No more contacts returned by API.")
            break

        for contact in contacts:
            contact_id = contact["id"]
            if contact_id in seen_ids:
                continue
            seen_ids.add(contact_id)

            first_name = contact.get("firstName", "")
            last_name = contact.get("lastName", "")
            email = contact.get("email", "")
            company = contact.get("companyName", "")
            title = extract_custom_field(contact, CUSTOM_FIELDS_MAP["designation"])
            website_url = contact.get("website", "")
            linkedin_url = ""

            if not website_url:
                print(f"⏭️ Skipping {first_name} {last_name} - Missing website.")
                continue

            existing_lead = db.query(LeadDB).filter(
                (LeadDB.email == email) |
                (LeadDB.website_url == website_url)
            ).first()

            if existing_lead:
                print(f"🔁 Skipping duplicate: {first_name} {last_name}")
                continue

            # Save to database
            lead_db = LeadDB(
                first_name=first_name,
                last_name=last_name,
                email=email,
                title=title,
                company=company,
                website_url=website_url,
                linkedin_url=linkedin_url
            )
            db.add(lead_db)
            db.commit()

            # Add to result list
            leads.append(Lead(
                id=lead_db.id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                title=title,
                company=company,
                website_url=website_url,
                linkedin_url=linkedin_url,
                website_speed_web=None,
                website_speed_mobile=None
            ))

            print(f"✅ Added: {first_name} {last_name} ({email})")

        if len(leads) >= desired_count:
            db.close()
            print(f"🎯 Final count: {len(leads)} leads added.")
            return leads

        start_after_id = contacts[-1]["id"]
        attempts += 1
        time.sleep(0.5)

    db.close()
    print(f"🎯 Final count: {len(leads)} leads added.")
    return leads
