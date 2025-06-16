from fastapi import FastAPI, Query, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import pandas as pd
import time

from apollo import fetch_apollo_leads, get_person_details
from models import Lead
from database import SessionLocal, LeadDB
from pagespeed import test_all_unspeeded_leads, refresh_speed_for_lead

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "NH Outreach Agent API is running"}

@app.get("/import/apollo", response_model=List[Lead])
def import_apollo_leads(
    industry: str = None,
    functions: str = None,
    seniority: str = None,
    per_page: int = 10  # <-- get this from frontend
):
    return fetch_apollo_leads(
        industry=industry,
        functions=functions,
        seniority=seniority,
        desired_count=per_page,  # <-- now using frontend's value
        per_page=per_page         # optional, but keeps request page size
    )

@app.get("/leads", response_model=List[Lead])
def get_saved_leads(limit: int = 100):
    db = SessionLocal()
    try:
        db_leads = db.query(LeadDB).limit(limit).all()
        leads = [
            Lead(
                first_name=l.first_name,
                last_name=l.last_name,
                email=l.email,
                title=l.title,
                company=l.company,
                website_url=l.website_url,
                linkedin_url=l.linkedin_url,
                website_speed_web=l.website_speed_web,
                website_speed_mobile=l.website_speed_mobile,
                id=l.id
            )
            for l in db_leads
        ]
        db.close()
        return leads
    except Exception as e:
        db.close()
        print(f"Error fetching leads: {e}")
        raise HTTPException(status_code=500, detail="Error fetching leads")

@app.post("/enrich-leads")
def enrich_all_leads():
    db = SessionLocal()
    leads = db.query(LeadDB).all()
    updated = 0

    for lead in leads:
        if not lead.email.startswith("locked_"):
            continue

        person_id = lead.email.replace("locked_", "").split("@")[0]
        enriched = get_person_details(person_id)

        real_email = enriched.get("email")
        title = enriched.get("title")

        # Update if unlocked email is available
        if real_email and not real_email.startswith("email_not_unlocked"):
            lead.email = real_email

        # Update title if available
        if title:
            lead.title = title

        if real_email or title:
            db.commit()
            updated += 1
            print(f"✅ Updated {lead.first_name} {lead.last_name}: email={real_email}, title={title}")

    db.close()
    return {"message": f"Enriched and updated {updated} leads"}


@app.post("/speedtest")
def run_bulk_speedtest():
    count = test_all_unspeeded_leads()
    return {"message": f"Tested {count} websites"}

@app.post("/speedtest/{lead_id}")
def refresh_one_speed(lead_id: int):
    web, mob = refresh_speed_for_lead(lead_id)
    if web is None and mob is None:
        return {"error": "Speed test failed or lead not found"}
    return {"message": f"Updated: W-{web}, M-{mob}"}