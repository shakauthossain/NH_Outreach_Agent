import os
import requests
import time
from dotenv import load_dotenv
from typing import List
from sqlalchemy.orm import Session
from models import Lead
from database import SessionLocal, LeadDB

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
                print(f"Skipping duplicate: {first_name} {last_name}")
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
                website_speed_mobile=None,
                screenshot_url = None
            ))
            inserted += 1
            print(f"Added: {first_name} {last_name} ({email})")

            if inserted >= desired_count:
                break

        page += 1
        attempts += 1
        time.sleep(1)

    db.close()
    print(f"Final count: {inserted} leads added.")
    return leads


