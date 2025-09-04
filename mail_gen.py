import os
import re
import time
import httpx
from dotenv import load_dotenv

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_core.output_parsers import StrOutputParser

from database import SessionLocal, LeadDB
from contextlib import contextmanager

# NEW: shared LLM provider
from llm_provider import get_chat_groq

# Load env for non-LLM settings used here (idempotent even if llm_provider already loaded it)
load_dotenv()
MAIL_SENDER = os.getenv("MAIL_SENDER")
GHL_API_KEY = os.getenv("GOHIGHLEVEL_KEY")
ENV = os.getenv("ENV", "prod")
TEST_EMAIL = os.getenv("TEST_EMAIL", None)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def generate_email_from_lead(lead_id: int) -> tuple[str, str]:
    with get_db() as db:
        lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
        if not lead:
            raise ValueError("Lead not found")

        template = '''
        Write an awesome cold outbound sales email for the following lead:

        - First Name: {first_name}
        - Job Title: {title}
        - Company: {company}
        - Website URL: {website_url}
        - Desktop PageSpeed Score: {desktop_score}
        - Mobile PageSpeed Score: {mobile_score}
        - Screenshot Link: {screenshot_url_web}

        This email should:
        - Address the lead by name and reference their job role
        - Highlight their website's low PageSpeed score (mention both desktop and mobile)
        - Reference real-world impact of slow websites (e.g., "a 1s delay can drop conversions by X%")
        - Mention that a performance audit screenshot is available (use {screenshot_url_web})
        - Offer a quick, no-pressure consultation to improve performance
        - Keep the tone confident, friendly, and brief
        - Include a clear call-to-action to book a short call
        - Do not add regards or ending of the mail
        - Make it personalized, relevant, and focused on solving their problem.

        Make it personalized, relevant, and focused on solving their problem.
        '''

        prompt = PromptTemplate(
            input_variables=[
                "first_name", "title", "company", "website_url",
                "desktop_score", "mobile_score", "screenshot_url_web"
            ],
            template=template,
        )

        # ✅ Same model & API via shared provider
        llm = get_chat_groq()  # temperature/model come from llm_provider/.env

        chain = prompt | llm | StrOutputParser()

        variables = {
            "first_name": lead.first_name,
            "title": lead.title or "",
            "company": lead.company,
            "website_url": lead.website_url,
            "desktop_score": lead.website_speed_web or 0,
            "mobile_score": lead.website_speed_mobile or 0,
            "screenshot_url_web": lead.screenshot_url_web or "N/A"
        }

        result = chain.invoke(variables).strip()
        print(result)

        match = re.search(r"Subject:\s*(.*)", result, re.IGNORECASE)
        subject_line = match.group(1).strip() if match else ""
        body = re.sub(r"Subject:.*\n?", "", result, flags=re.IGNORECASE).strip()

        # Ensure a sign-off gets added consistently
        body = body.strip() + "\n\nBest regards,\nNotionhive Tech Team"

        lead.generated_email = body
        lead.final_email = body
        lead.email_subject = subject_line
        db.commit()

        return subject_line, body

def send_email_to_lead(lead_id: int, email_body: str) -> None:
    with get_db() as db:
        lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
        if not lead:
            raise ValueError("Lead not found")
        if not lead.email:
            raise ValueError("Lead has no email")
        if not lead.ghl_contact_id:
            raise ValueError("GHL contact ID not set for this lead")

        recipient_email = TEST_EMAIL if ENV == "dev" and TEST_EMAIL else lead.email

        lead.final_email = email_body
        subject = lead.email_subject or f"Website performance improvements for {lead.company}"

        send_url = "https://services.leadconnectorhq.com/conversations/messages"

        payload = {
            "type": "Email",
            "contactId": lead.ghl_contact_id,
            "emailFrom": MAIL_SENDER,
            "emailTo": recipient_email,
            "subject": subject,
            "html": f"<p>{email_body.replace(chr(10), '<br>')}</p>",
            "message": email_body,
            "emailReplyMode": "reply"
        }

        headers = {
            "Authorization": f"Bearer {GHL_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Version": "2021-04-15"
        }

        try:
            print(f"Sending email to {recipient_email} via LeadConnector Conversations API...")
            response = httpx.post(send_url, headers=headers, json=payload)
            response.raise_for_status()
            print("Email sent.")

            # Retry loop to get conversation ID
            search_url = "https://services.leadconnectorhq.com/conversations/search"
            search_params = {
                "locationId": os.getenv("GOHIGHLEVEL_LOCATION_ID"),
                "contactId": lead.ghl_contact_id
            }

            conversation_id = None
            for attempt in range(5):
                search_resp = httpx.get(search_url, headers=headers, params=search_params)
                print(search_params)
                if search_resp.status_code == 200:
                    print(f"Search result: {search_resp.json()}")
                    data = search_resp.json()
                    for convo in data.get("conversations", []):
                        if convo.get("lastMessageType") == "TYPE_EMAIL":
                            conversation_id = convo.get("id")
                            break
                    if conversation_id:
                        print(f"Conversation ID found: {conversation_id}")
                        lead.conversation_id = conversation_id
                        db.commit()
                        break
                print(f"Waiting for conversation (try {attempt + 1}/5)...")
                time.sleep(1.5)

            if not conversation_id:
                print("Conversation ID not found after retries.")

        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"GHL email send failed: {e.response.text}")

        lead.mail_sent = True
        db.commit()
