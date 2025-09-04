import os
import requests
import time
from dotenv import load_dotenv
from typing import List
from sqlalchemy.orm import Session
from models import Lead
from database import SessionLocal, LeadDB
from apollo import enrich_lead_with_apollo

load_dotenv()

GoHighLevel_key = os.getenv("GOHIGHLEVEL_KEY")
Location_ID = os.getenv("GOHIGHLEVEL_LOCATION_ID")

def fetch_gohighlevel_leads(desired_count: int = 20, per_page: int = 20) -> List[Lead]:
    url = "https://services.leadconnectorhq.com/contacts/"
    headers = {
        "Authorization": f"Bearer {GoHighLevel_key}",
        "Version": "2021-07-28",
        "Content-Type": "application/json"
    }

    db: Session = SessionLocal()
    leads: List[Lead] = []
    inserted = 0
    page = 1
    max_attempts = 100
    attempts = 0

    while inserted < desired_count and attempts < max_attempts:
        params = {
            "locationId": Location_ID,
            "limit": per_page,
            "page": page
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
        except Exception as e:
            print("GHL API error:", response.status_code, response.text)
            time.sleep(2)
            attempts += 1
            continue

        data = response.json()
        contacts = data.get("contacts", [])

        if not contacts:
            print("No more contacts returned by API.")
            break

        for contact in contacts:
            ghl_contact_id = contact.get("id")
            first_name = contact.get("firstName", "")
            last_name = contact.get("lastName", "")
            email = contact.get("email", "")
            company = contact.get("companyName", "")
            title = contact.get("designation", "")
            raw_website = contact.get("website", "")
            website_url = raw_website.split(",")[0].strip() if raw_website else ""
            linkedin_url = ""

            if not website_url or not email:
                print(f"Skipping {first_name} {last_name} - Missing website or email.")
                continue

            existing_lead = db.query(LeadDB).filter(
                (LeadDB.email == email) |
                (LeadDB.website_url == website_url)
            ).first()

            if existing_lead:
                if existing_lead.ghl_contact_id != ghl_contact_id:
                    print(f"Updating GHL ID for {email}: {existing_lead.ghl_contact_id} → {ghl_contact_id}")
                    existing_lead.ghl_contact_id = ghl_contact_id
                    db.flush()
                    db.commit()

                    # Verify in DB
                    verified = db.query(LeadDB).filter(LeadDB.id == existing_lead.id).first()
                    print(f"Verified saved: {verified.email} → GHL ID: {verified.ghl_contact_id}")
                else:
                    print(f"No update needed for {email}")
                continue

            enriched = enrich_lead_with_apollo(email)
            company = enriched.get("company", company)
            title = enriched.get("title", title)
            linkedin_url = enriched.get("linkedin_url", "")

            lead_db = LeadDB(
                first_name=first_name,
                last_name=last_name,
                email=email,
                title=title,
                company=company,
                website_url=website_url,
                linkedin_url=linkedin_url,
                ghl_contact_id=ghl_contact_id
            )
            db.add(lead_db)
            db.commit()

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
                website_speed_mobile=None,
                screenshot_url_web=None,
                ghl_contact_id=ghl_contact_id
            ))
            print(f"Added: {first_name} {last_name} ({email}) | GHL ID: {ghl_contact_id}")
            inserted += 1

            if inserted >= desired_count:
                break

        page += 1
        attempts += 1
        time.sleep(1)

    print("Final DB Snapshot:")
    for lead in db.query(LeadDB).order_by(LeadDB.id.desc()).limit(5):
        print(f"{lead.id}: {lead.email} | GHL ID: {lead.ghl_contact_id}")

    db.close()
    return leads
