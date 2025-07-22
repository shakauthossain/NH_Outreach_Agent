import os
import re
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

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
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
ENV = os.getenv("ENV", "prod")
TEST_EMAIL = os.getenv("TEST_EMAIL", None)

# Context manager for DB session
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

        # Email generation prompt
        template = """
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
        
        Make it personalized, relevant, and focused on solving their problem.
        """

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

        # Extract subject line
        subject_line = ""
        body = result

        match = re.search(r"Subject:\s*(.*)", result, re.IGNORECASE)
        if match:
            subject_line = match.group(1).strip()
            body = re.sub(r"Subject:.*\n?", "", result, flags=re.IGNORECASE).strip()

        # Add sign-off
        body = body.strip() + "\n\nBest regards,\nNotionhive Tech Team"

        # Save to DB
        lead.generated_email = body
        lead.final_email = body
        lead.email_subject = subject_line
        db.commit()

        return subject_line, body


def send_email_to_lead(lead_id: int, email_body: str) -> None:
    with get_db() as db:
        lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
        if not lead or not lead.email:
            raise ValueError("Lead not found or email missing")

        # Use test email if in dev
        recipient_email = TEST_EMAIL if ENV == "dev" and TEST_EMAIL else lead.email

        # Save edited email
        lead.final_email = email_body

        # Prepare email
        html_body = email_body.replace('\n', '<br>')
        subject = lead.email_subject or f"Website performance improvements for {lead.company}"

        message = Mail(
            from_email=MAIL_SENDER,
            to_emails=recipient_email,
            subject=subject,
            html_content=f"<html><body><p>{html_body}</p></body></html>"
        )

        # Send email
        try:
            print(f"Sending email to {recipient_email}:\nSubject: {subject}\n---\n{email_body}\n---")
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)

            if response.status_code not in [200, 202]:
                raise RuntimeError(f"SendGrid error: {response.status_code} - {response.body.decode()}")

            print(f"SendGrid Email sent. Status: {response.status_code}, Message ID: {response.headers.get('X-Message-Id')}")

        except Exception as e:
            raise RuntimeError(f"SendGrid mail sending failed: {e}")

        # Mark as sent
        lead.mail_sent = True
        if email_body.strip() != (lead.generated_email or "").strip():
            print("Email was edited before sending.")

        db.commit()