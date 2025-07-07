import os
import requests
import time
from dotenv import load_dotenv
from typing import List
from models import Lead
from database import SessionLocal, LeadDB
from pagespeed import test_all_unspeeded_leads, refresh_speed_for_lead

load_dotenv()

API_KEY = os.getenv("APOLLO_API_KEY")
EnrichAPI_KEY = os.getenv("EnrichAPOLLO_API_KEY")
GoHighLevel_key = os.getenv("GOHIGHLEVEL_KEY")
Location_ID = os.getenv("GOHIGHLEVEL_LOCATION_ID")

def get_person_details(person_id: str) -> dict:
    url = f"https://api.apollo.io/v1/people/match?id={person_id}"
    headers = {
        "X-Api-Key": EnrichAPI_KEY,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 429:
            print(f"Rate limit hit for {person_id}, skipping for now.")
            return {}
        response.raise_for_status()
        return response.json().get("person", {})
    except Exception as e:
        print(f"Error unlocking {person_id}: {e}")
        return {}

def fetch_apollo_leads(
    industry: str = None,
    functions: str = None,
    seniority: str = None,
    desired_count: int = 10,
    per_page: int = 25
) -> List[Lead]:
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {
        "X-Api-Key": API_KEY,
        "Content-Type": "application/json"
    }

    db = SessionLocal()
    leads = []
    page = 1
    max_pages = 50

    while len(leads) < desired_count and page <= max_pages:
        print(f"Fetching page {page}...")

        payload = {
            "page": page,
            "per_page": per_page
        }

        if industry:
            payload["industry"] = industry
        if functions:
            payload["functions"] = [functions]
        if seniority:
            payload["seniority_levels"] = [seniority]

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except Exception as e:
            print(f"Apollo API error: {e}")
            break

        data = response.json()
        people = data.get("people", [])

        if not people:
            print("No people found on this page.")
            break

        for person in people:
            person_id = person["id"]
            first_name = person.get("first_name", "")
            last_name = person.get("last_name", "")
            title = person.get("title")
            org = person.get("organization", {})
            email = person.get("email")
            website_url = org.get("website_url", "") or ""
            linkedin_url = person.get("linkedin_url", "") or ""

            if not website_url:
                print(f"Skipping {first_name} {last_name} - No website.")
                continue

            if not email or "not_unlocked" in email or not linkedin_url or not title:
                enriched = get_person_details(person_id)
                email = enriched.get("email") or email
                linkedin_url = linkedin_url or enriched.get("linkedin_url")
                title = enriched.get("title") or title

            if not linkedin_url:
                print(f"Skipping {first_name} {last_name} - No LinkedIn after enrichment.")
                continue

            if not email or "not_unlocked" in email:
                email = f"locked_{person_id}@apollo.com"

            existing_lead = db.query(LeadDB).filter(
                (LeadDB.email == email) |
                (LeadDB.website_url == website_url) |
                (LeadDB.linkedin_url == linkedin_url)
            ).first()

            if existing_lead:
                print(f"Skipping duplicate: {first_name} {last_name}")
                continue

            lead_db = LeadDB(
                first_name=first_name,
                last_name=last_name,
                email=email,
                title=title,
                company=org.get("name", ""),
                website_url=website_url,
                linkedin_url=linkedin_url
            )
            db.add(lead_db)
            db.commit()

            # Create the Lead Pydantic model without requiring missing fields
            leads.append(Lead(
                id=lead_db.id,  # Use the generated id from the database
                first_name=first_name,
                last_name=last_name,
                email=email,
                title=lead_db.title,
                company=lead_db.company,
                website_url=lead_db.website_url,
                linkedin_url=lead_db.linkedin_url,
                website_speed_web=None,
                website_speed_mobile=None
            ))

            print(f"Added: {first_name} {last_name} ({email})")

            if len(leads) >= desired_count:
                break

        page += 1

    db.close()
    print(f"Final count: {len(leads)} leads added.")
    return leads
