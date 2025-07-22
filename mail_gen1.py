import os
from dotenv import load_dotenv
from email.mime.text import MIMEText
import smtplib

from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser

from database import SessionLocal, LeadDB

load_dotenv()
Groq_API=os.getenv("GROQ_API_KEY")
MAIL_UN=os.getenv("MAIL_USERNAME")
MAIL_PASS=os.getenv("MAIL_PASSWORD")
MAIL_SENDER=os.getenv("MAIL_SENDER")
mode = os.getenv("MAILTRAP_MODE")
base_domain = os.getenv("BASE_TRACKING_DOMAIN")

smtp_host = os.getenv("MAILTRAP_SANDBOX_HOST") if mode == "sandbox" else os.getenv("MAILTRAP_PROD_HOST")
smtp_port = int(os.getenv("MAILTRAP_SANDBOX_PORT")) if mode == "sandbox" else int(os.getenv("MAILTRAP_PROD_PORT"))

def generate_email_from_lead(lead_id: int) -> str:
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()

    if not lead:
        raise ValueError("Lead not found")

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
    
    Make it personalized, relevant, and focused on solving their problem.
    """

    prompt = PromptTemplate(
        input_variables=["first_name", "title", "company", "website_url"],
        template=template,
    )

    llm = ChatGroq(
        model_name="llama-3.3-70b-versatile",  # make sure this is the correct model name you intend to use
        temperature=0.7,
        groq_api_key=Groq_API
    )

    chain = prompt | llm | StrOutputParser()

    # Make sure these keys match all placeholder names in the prompt
    variables = {
        "first_name": lead.first_name,
        "title": lead.title or "",
        "company": lead.company,
        "website_url": lead.website_url,
        "desktop_score": lead.website_speed_web or 0,
        "mobile_score": lead.website_speed_mobile or 0,
        "screenshot_url": lead.screenshot_url or "N/A"
    }

    email = chain.invoke(variables)
    if mode != "sandbox":
        pixel = f'<img src="{base_domain}/tracking/open/{lead.id}" width="1" height="1" style="display:none;">'
        email += f"\n\n{pixel}"
    lead.generated_email = email
    lead.final_email = email
    db.commit()
    db.close()
    return email.strip()


def send_email_to_lead(lead_id: int, email_body: str) -> None:
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()

    if not lead or not lead.email:
        db.close()
        raise ValueError("Lead not found or email missing")

    # Save the edited final email
    lead.final_email = email_body

    # Prepare email message
    html_body = email_body.replace('\n', '<br>')
    msg = MIMEText(f"<html><body><p>{html_body}</p></body></html>", "html")
    msg["Subject"] = f"Website performance improvements for {lead.company}"
    msg["From"] = MAIL_SENDER
    msg["To"] = lead.email

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(MAIL_UN, MAIL_PASS)
            server.send_message(msg)
    except Exception as e:
        db.close()
        raise RuntimeError(f"Mail sending failed: {e}")

    # Mark as sent and commit
    lead.mail_sent = True
    if email_body.strip() != (lead.generated_email or "").strip():
        print("Email was edited before sending.")

    db.commit()
    db.close()