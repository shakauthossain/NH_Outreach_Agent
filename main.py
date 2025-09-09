from fastapi import FastAPI, Query, UploadFile, File, HTTPException, Request, Depends, Form, Response, Body
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from fastapi.staticfiles import StaticFiles
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import csv
from io import StringIO
import os
from urllib.parse import urlparse
import re
import json
import datetime
import io

from auth.routes import router as auth_router
from apollo import fetch_apollo_leads, get_person_details
from models import Lead, MailBody
from database import SessionLocal, LeadDB
from pagespeed import test_all_unspeeded_leads, refresh_speed_for_lead
from mail_gen import generate_email_from_lead, send_email_to_lead
from pagespeed import get_pagespeed_score_and_screenshot
from GoHighLevel import fetch_gohighlevel_leads
from ghl_inbox import router as inbox_router
from redis_cache import get_cached_lead_list, cache_lead_list
from scraping import scrape_and_extract  # Import scraping logic from scraping.py
from punchline import generate_punchlines  
from background_tasks import process_punchlines_for_lead, process_punchlines_for_all_leads
from celery.result import AsyncResult

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://outreach.hellonotionhive.com"],  # Only allow your frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def sanitize_domain(domain: str) -> str:
    """Sanitize the domain to replace invalid characters like dots and colons."""
    return domain.replace(".", "_").replace(":", "_")


@app.get("/{domain}-{strategy}-pagespeed.png")
async def get_screenshot(domain: str, strategy: str):
    # Sanitize the domain to match the file storage structure
    sanitized_domain = sanitize_domain(domain)
    
    # Construct the file path
    file_path = os.path.join(STATIC_DIR, sanitized_domain, f"{sanitized_domain}-{strategy}-pagespeed.png")
    
    # Check if the file exists
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        raise HTTPException(status_code=404, detail="Screenshot not found")


# Mount the static files directory to serve other static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth_router)
app.include_router(inbox_router)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body,
        },
    )

ALLOWED_FIELDS = {
    "first_name", "last_name", "email", "title",
    "company", "website_url", "linkedin_url"
}

def normalize_url(raw: str | None) -> str | None:
    """
    Normalize a company domain/url to canonical https://host
    - Adds https:// if missing
    - Strips www., port, creds, and trailing slash
    """
    if not raw:
        return None
    s = raw.strip()
    if not re.match(r"^[a-z][a-z0-9+\-.]*://", s.lower()):
        s = "https://" + s
    p = urlparse(s)
    host = p.netloc or p.path
    if "@" in host:
        host = host.split("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    host = re.sub(r"[^a-z0-9\.\-]", "", host.lower())
    return f"https://{host}".rstrip("/") if host else None

UPLOAD_DIR = "uploaded_csvs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/")
def root():
    return {"message": "NH Outreach Agent API is up and running"}



@app.get("/leads", response_model=list[Lead])
async def get_saved_leads(skip: int = 0, limit: int = 10):
    try:
        # Try Redis first
        cached = await get_cached_lead_list(skip, limit)
        if cached:
            print(f"Redis HIT for leads: skip={skip}, limit={limit}")
            return cached
        else:
            print(f"Redis MISS for leads: skip={skip}, limit={limit}")

        db: Session = SessionLocal()
        db_leads = db.query(LeadDB) \
            .filter(LeadDB.email != None, LeadDB.website_url != None) \
            .order_by(LeadDB.id) \
            .offset(skip) \
            .limit(limit) \
            .all()
        db.close()

        # Convert to serializable format
        leads = [Lead.from_orm(l).dict() for l in db_leads]

        # Cache the result
        await cache_lead_list(skip, limit, leads, ttl=300)

        return leads

    except Exception as e:
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/upload-csv")
async def upload_csv_and_ingest(
    file: UploadFile = File(...),
    mapping: str = Form(...),     # JSON string with CSV->DB mapping
    db: Session = Depends(get_db)
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only CSV files are allowed.")

    # Parse mapping JSON
    try:
        mapping_dict: dict[str, str | None] = json.loads(mapping)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid mapping JSON: {e}")

    # Sanitize mapping: keep only allowed DB fields and non-skip values
    cleaned_map: dict[str, str] = {}
    for db_field, csv_col in mapping_dict.items():
        if db_field not in ALLOWED_FIELDS:
            continue
        if not csv_col:
            continue
        if isinstance(csv_col, str) and csv_col.strip().lower() in {"skip column", "skip", "none", "null"}:
            continue
        cleaned_map[db_field] = csv_col.strip()

    if not cleaned_map:
        raise HTTPException(status_code=400, detail="No valid column mappings provided.")

    # Read and save the CSV
    raw = await file.read()
    save_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as f:
        f.write(raw)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV appears to have no header row.")

    # Build a quick (case-insensitive) header resolver
    headers_norm = {h.lower().strip(): h for h in reader.fieldnames}

    def get_val(row: dict, csv_header_name: str):
        # Find the actual CSV column in a case-insensitive way
        actual = headers_norm.get(csv_header_name.lower().strip())
        v = row.get(actual) if actual else None
        return v.strip() if isinstance(v, str) else v

    created = updated = 0
    errors: list[dict] = []

    for i, row in enumerate(reader, start=1):
        try:
            # Build payload from mapping
            payload = {}
            for db_field, csv_col in cleaned_map.items():
                val = get_val(row, csv_col)
                if db_field == "website_url":
                    val = normalize_url(val)
                payload[db_field] = val

            email = payload.get("email")
            company = payload.get("company")
            website_url = payload.get("website_url")

            # Must have at least email OR (company + website_url)
            if not email and not (company and website_url):
                errors.append({"row": i, "reason": "missing unique keys (email or company+website_url)"})
                continue

            # Upsert
            existing = None
            if email:
                existing = db.query(LeadDB).filter(LeadDB.email == email).first()
            if not existing and company and website_url:
                existing = db.query(LeadDB).filter(
                    LeadDB.company == company,
                    LeadDB.website_url == website_url
                ).first()

            if existing:
                for k, v in payload.items():
                    if v not in (None, ""):
                        setattr(existing, k, v)
                updated += 1
            else:
                db.add(LeadDB(**payload))
                created += 1

            if (created + updated) % 100 == 0:
                db.commit()

        except Exception as e:
            db.rollback()
            errors.append({"row": i, "reason": str(e)})

    db.commit()

    # Optional: clear a few cached pages if your cache_delete helper exists
    try:
        for skip in (0, 10, 20, 30, 40):
            await cache_lead_list(skip, 10, None, ttl=0)
    except Exception:
        pass

    return {
        "filename": file.filename,
        "columns_detected": reader.fieldnames,
        "mapping_used": cleaned_map,
        "created": created,
        "updated": updated,
        "errors": errors[:50],
        "total_rows_processed": created + updated + len(errors),
        "saved_path": save_path
    }

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

DEFAULT_EXPORT_COLUMNS = [
    "id", "first_name", "last_name", "email",
    "company", "title", "website_url", "linkedin_url"
]

def _resolve_export_columns(columns_param: Optional[str]) -> List[str]:
    # Get actual columns from SQLAlchemy model
    mapper = inspect(LeadDB)
    all_columns = {col.key for col in mapper.attrs if hasattr(col, "columns") or True}
    if not columns_param:
        return [c for c in DEFAULT_EXPORT_COLUMNS if c in all_columns]

    requested = [c.strip() for c in columns_param.split(",") if c.strip()]
    valid = [c for c in requested if c in all_columns]
    if not valid:
        # fallback to defaults if the user passed only invalid columns
        valid = [c for c in DEFAULT_EXPORT_COLUMNS if c in all_columns]
    return valid

def _serialize_cell(val):
    # Make CSV-safe strings
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)

@app.get("/download-csv")
def download_leads_csv(
    response: Response,
    ids: Optional[List[int]] = Query(None, description="Filter by selected Lead IDs, e.g. ?ids=1&ids=2"),
    columns: Optional[str] = Query(None, description="Comma-separated list of columns to include"),
    db: Session = Depends(get_db),
):
    export_cols = _resolve_export_columns(columns)

    query = db.query(LeadDB)
    if ids:
        query = query.filter(LeadDB.id.in_(ids))

    # Stream as we go for large exports
    def row_generator():
        # header
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(export_cols)
        yield buffer.getvalue()
        buffer.seek(0); buffer.truncate(0)

        # rows
        for lead in query.yield_per(500):
            row = [_serialize_cell(getattr(lead, col, None)) for col in export_cols]
            writer.writerow(row)
            yield buffer.getvalue()
            buffer.seek(0); buffer.truncate(0)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"leads_export_{ts}.csv"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(row_generator(), media_type="text/csv", headers=headers)

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

@app.post("/process-punchlines/{lead_id}")
async def process_punchlines(lead_id: int):
    task = process_punchlines_for_lead.delay(lead_id)
    return {"task_id": task.id, "message": "Punchline processing started in background."}

@app.post("/process-punchlines")
async def process_punchlines_all():
    task = process_punchlines_for_all_leads.delay()
    return {"task_id": task.id, "message": "Bulk punchline processing started in background."}

@app.get("/task-status/{task_id}")
def get_task_status(task_id: str):
    result = AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "result": result.result if result.ready() else None}

@app.get("/lead-punchlines/{lead_id}")
def get_lead_punchlines(lead_id: int):
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
    if not lead:
        db.close()
        raise HTTPException(status_code=404, detail="Lead not found")
    punchlines = {
        "punchline1": lead.punchline1,
        "punchline2": lead.punchline2,
        "punchline3": lead.punchline3
    }
    db.close()
    return {"lead_id": lead_id, "punchlines": punchlines}

@app.post("/download-csv-selected")
def download_selected_leads_csv(
    lead_ids: List[int] = Body(..., embed=True, description="List of lead IDs to export"),
    columns: Optional[str] = None,
    db: Session = Depends(get_db),
):
    export_cols = _resolve_export_columns(columns)

    query = db.query(LeadDB)
    if lead_ids:
        query = query.filter(LeadDB.id.in_(lead_ids))

    def row_generator():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(export_cols)
        yield buffer.getvalue()
        buffer.seek(0); buffer.truncate(0)
        for lead in query.yield_per(500):
            row = [_serialize_cell(getattr(lead, col, None)) for col in export_cols]
            writer.writerow(row)
            yield buffer.getvalue()
            buffer.seek(0); buffer.truncate(0)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"leads_selected_{ts}.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(row_generator(), media_type="text/csv", headers=headers)