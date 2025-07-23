import os
import re
import httpx
from dotenv import load_dotenv

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser

from database import SessionLocal, LeadDB
from contextlib import contextmanager

# Load environment variables
load_dotenv()
Groq_API = os.getenv("GROQ_API_KEY")
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
        Write a cold outbound sales email for the following lead:

        - First Name: {first_name}
        - Job Title: {title}
        - Company: {company}
        - Website URL: {website_url}
        - Desktop PageSpeed Score: {desktop_score}
        - Mobile PageSpeed Score: {mobile_score}
        - Screenshot Link: {screenshot_url}

        This email should:
        - Address the lead by name and reference their job role
        - Highlight their website's low PageSpeed score (mention both desktop and mobile)
        - Reference real-world impact of slow websites (e.g., "a 1s delay can drop conversions by X%")
        - Mention that a performance audit screenshot is available (use {screenshot_url})
        - Offer a quick, no-pressure consultation to improve performance
        - Keep the tone confident, friendly, and brief
        - Include a clear call-to-action to book a short call
        - Do not add regards or ending of the mail
        '''

        prompt = PromptTemplate(
            input_variables=[
                "first_name", "title", "company", "website_url",
                "desktop_score", "mobile_score", "screenshot_url"
            ],
            template=template,
        )

        llm = ChatGroq(
            model_name="llama-3.3-70b-versatile",
            temperature=0.7,
            groq_api_key=Groq_API
        )

        chain = prompt | llm | StrOutputParser()

        variables = {
            "first_name": lead.first_name,
            "title": lead.title or "",
            "company": lead.company,
            "website_url": lead.website_url,
            "desktop_score": lead.website_speed_web or 0,
            "mobile_score": lead.website_speed_mobile or 0,
            "screenshot_url": lead.screenshot_url or "N/A"
        }

        result = chain.invoke(variables).strip()

        match = re.search(r"Subject:\s*(.*)", result, re.IGNORECASE)
        subject_line = match.group(1).strip() if match else ""
        body = re.sub(r"Subject:.*\n?", "", result, flags=re.IGNORECASE).strip()

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
            print(f"📤 Sending email to {recipient_email} via LeadConnector Conversations API...")
            response = httpx.post(send_url, headers=headers, json=payload)
            response.raise_for_status()
            print("✅ LeadConnector email sent successfully.")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"❌ GHL email send failed: {e.response.text}")

        lead.mail_sent = True
        db.commit()
