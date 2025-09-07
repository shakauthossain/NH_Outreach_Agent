from celery_worker import celery_app
from pagespeed import refresh_speed_for_lead
from database import SessionLocal, LeadDB
from scraping import scrape_and_extract
from punchline import generate_punchlines

@celery_app.task
def run_speed_test(lead_id: int):
    web, mob = refresh_speed_for_lead(lead_id)
    if web is None and mob is None:
        return {"error": "Speed test failed or lead not found"}
    print(f"[Celery] Updated lead {lead_id}: web={web}, mob={mob}")
    return {"message": f"Updated: W-{web}, M-{mob}"}

@celery_app.task
def process_punchlines_for_lead(lead_id: int):
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
    if not lead or not lead.website_url:
        db.close()
        return {"error": "Lead not found or missing website_url"}
    try:
        # Scrape and extract signals
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        pages, signals, evidence = loop.run_until_complete(
            scrape_and_extract(lead.website_url, firecrawl_base="https://api.firecrawl.dev", firecrawl_key="fc-135574cccbe141b5bcfe6c1a40d17cb9")
        )
        if not evidence:
            db.close()
            return {"error": "No evidence found"}
        company = lead.company if lead.company else "Unknown"
        ranked_punchlines = generate_punchlines(company, evidence)
        lead.punchline1 = ranked_punchlines[0]["line"] if len(ranked_punchlines) > 0 else None
        lead.punchline2 = ranked_punchlines[1]["line"] if len(ranked_punchlines) > 1 else None
        lead.punchline3 = ranked_punchlines[2]["line"] if len(ranked_punchlines) > 2 else None
        db.commit()
        db.close()
        return {"lead_id": lead_id, "status": "success"}
    except Exception as e:
        db.close()
        return {"error": str(e)}

@celery_app.task
def process_punchlines_for_all_leads():
    db = SessionLocal()
    leads = db.query(LeadDB).filter(LeadDB.website_url != None).all()
    processed = 0
    errors = []
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for lead in leads:
        try:
            pages, signals, evidence = loop.run_until_complete(
                scrape_and_extract(lead.website_url, firecrawl_base="https://api.firecrawl.dev", firecrawl_key="fc-135574cccbe141b5bcfe6c1a40d17cb9")
            )
            if not evidence:
                errors.append({"lead_id": lead.id, "reason": "No evidence found"})
                continue
            company = lead.company if lead.company else "Unknown"
            ranked_punchlines = generate_punchlines(company, evidence)
            lead.punchline1 = ranked_punchlines[0]["line"] if len(ranked_punchlines) > 0 else None
            lead.punchline2 = ranked_punchlines[1]["line"] if len(ranked_punchlines) > 1 else None
            lead.punchline3 = ranked_punchlines[2]["line"] if len(ranked_punchlines) > 2 else None
            processed += 1
        except Exception as e:
            errors.append({"lead_id": lead.id, "reason": str(e)})
    db.commit()
    db.close()
    return {"processed": processed, "errors": errors}
