import requests
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal, LeadDB

router = APIRouter()
SALESROBOT_URL = "https://app.salesrobot.co/public/webhooks/5106d918-7ece-46f0-ba70-e1a5420feba7/campaign/addProspect"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/push-to-salesrobot")
def push_leads(db: Session = Depends(get_db)):
    leads = db.query(LeadDB).filter(LeadDB.sent_to_salesrobot == False).all()

    for lead in leads:
        payload = {
            "campaignName": "Default Campaign",  # Change as needed
            "firstName": lead.first_name,
            "lastName": lead.last_name,
            "emailId": lead.email,
            "jobTitle": lead.title,
            "companyName": lead.company,
            "personalWebsite": lead.website_url,
            "profileUrl": lead.linkedin_url,
            "isPremium": False,
            "connectionLevel": "2nd",
            "customColumns": '{"source":"crm"}'
        }

        response = requests.post(SALESROBOT_URL, json=payload)
        if response.status_code == 200:
            lead.sent_to_salesrobot = True
            db.commit()
        else:
            print(f"Failed to push lead {lead.email}: {response.status_code} - {response.text}")

    return {"message": "Lead sync complete"}
