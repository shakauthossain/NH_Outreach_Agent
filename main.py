from fastapi import FastAPI, Query, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from typing import List

from auth.routes import router as auth_router
from apollo import fetch_apollo_leads, get_person_details
from models import Lead, MailBody
from database import SessionLocal, LeadDB
from pagespeed import test_all_unspeeded_leads, refresh_speed_for_lead
from mail_gen import generate_email_from_lead, send_email_to_lead
from pagespeed import get_pagespeed_score_and_screenshot
from GoHighLevel import fetch_gohighlevel_leads
from salesrobot import router as salesrobot_router
from ghl_inbox import router as inbox_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body,
        },
    )

@app.get("/")
def root():
    return {"message": "NH Outreach Agent API is up and running"}

app.include_router(salesrobot_router)
app.include_router(auth_router)
app.include_router(inbox_router)

@app.get("/leads", response_model=list[Lead])
def get_saved_leads(skip: int = 0, limit: int = 10):
    db = SessionLocal()
    try:
        # total = db.query(LeadDB).count()
        db_leads = db.query(LeadDB) \
            .filter(LeadDB.email != None, LeadDB.website_url != None) \
            .order_by(LeadDB.id)\
            .offset(skip)\
            .limit(limit)\
            .all()

        # leads = [
        #     Lead(
        #         id=l.id,
        #         first_name=l.first_name,
        #         last_name=l.last_name,
        #         email=l.email,
        #         title=l.title,
        #         company=l.company,
        #         website_url=l.website_url,
        #         linkedin_url=l.linkedin_url,
        #         website_speed_web=l.website_speed_web,
        #         website_speed_mobile=l.website_speed_mobile,
        #         screenshot_url=l.screenshot_url,
        #         mail_sent=l.mail_sent,
        #         generated_email=l.generated_email,
        #         final_email=l.final_email,
        #         pagespeed_diagnostics=l.pagespeed_diagnostics,
        #         pagespeed_metrics_mobile = l.pagespeed_metrics_mobile,
        #         pagespeed_metrics_desktop = l.pagespeed_metrics_desktop,
        #     )
        #     for l in db_leads
        # ]
        # db.close()
        return db_leads
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

        if "apollo.com" in lead.email:
            source = "apollo"
        elif "gohighlevel.com" in lead.email:
            source = "ghl"
        else:
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
            print(f"Updated {lead.first_name} {lead.last_name}: email={real_email}, title={title}")

    db.close()
    return {"message": f"Enriched and updated {updated} leads"}

@app.get("/import/gohighlevel", response_model=List[Lead])
def import_gohighlevel_leads(per_page: int = 20):
    return fetch_gohighlevel_leads(
        desired_count=per_page,
        per_page=per_page
    )

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

@app.get("/test-pagespeed")
def test_pagespeed_metrics(url: str):
    scores, screenshot, diagnostics, metrics = get_pagespeed_score_and_screenshot(url, "mobile")

    return {
        "scores": scores,
        "screenshot_path": screenshot,
        "diagnostics_keys": list(diagnostics.keys()) if diagnostics else [],
        "metrics": metrics
    }

@app.post("/generate-mail/{lead_id}")
def generate_mail(lead_id: int):
    try:
        email = generate_email_from_lead(lead_id)
        return {"email": email}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation error: {e}")

@app.post("/save-mail/{lead_id}")
def save_mail(lead_id: int, body: MailBody):
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
    if not lead:
        db.close()
        return {"error": "Lead not found"}

    lead.final_email = body.email_body
    lead.subject = lead.email_subject or f"Website performance improvements for {lead.company}"
    db.commit()
    db.close()
    return {"message": "Draft saved successfully."}

@app.get("/mail/{lead_id}")
def serve_mail_editor(lead_id: int):
    return FileResponse("mail_editor.html")

@app.post("/send-mail/{lead_id}")
def send_mail(lead_id: int, body: MailBody):
    send_email_to_lead(lead_id, body.email_body)
    return {"message": "Email sent successfully."}
