from typing import Optional
from pydantic import BaseModel

class Lead(BaseModel):
    id: Optional[int]
    first_name: str
    last_name: Optional[str]
    email: str
    title: Optional[str] = None
    company: str
    website_url: Optional[str]
    linkedin_url: Optional[str]
    website_speed_web: Optional[int]
    website_speed_mobile: Optional[int]
    screenshot_url: Optional[str]
    mail_sent: Optional[bool] = False
    generated_email: Optional[str] = None
    final_email: Optional[str] = None

    class Config:
        orm_mode = True

class MailBody(BaseModel):
    email_body: str