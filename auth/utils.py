import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import os

load_dotenv()

# Load mail settings
MAIL_PASS = os.getenv("MAIL_PASSWORD")
MAIL_SENDER = os.getenv("MAIL_SENDER")
MAIL_USERNAME = os.getenv("MAIL_USERNAME")  # Add this to your .env
MAILTRAP_MODE = os.getenv("MAILTRAP_MODE", "sandbox")
BASE_DOMAIN = os.getenv("BASE_TRACKING_DOMAIN")

# Choose SMTP host/port based on mode
smtp_host = (
    os.getenv("MAILTRAP_SANDBOX_HOST")
    if MAILTRAP_MODE == "sandbox"
    else os.getenv("MAILTRAP_PROD_HOST")
)
smtp_port = int(
    os.getenv("MAILTRAP_SANDBOX_PORT")
    if MAILTRAP_MODE == "sandbox"
    else os.getenv("MAILTRAP_PROD_PORT")
)

def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = MAIL_SENDER
    msg["To"] = to
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(MAIL_USERNAME, MAIL_PASS)
            smtp.send_message(msg)
    except Exception as e:
        raise RuntimeError(f"Failed to send email: {e}")
