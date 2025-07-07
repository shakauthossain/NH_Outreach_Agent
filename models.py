from typing import Optional, Dict, Any
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
    pagespeed_diagnostics: Optional[Dict[str, Any]] = None
    accessibility_score: Optional[int] = None
    seo_score: Optional[int] = None
    best_practices_score: Optional[int] = None
    pagespeed_metrics_mobile: Optional[Dict[str, Any]] = None
    pagespeed_metrics_desktop: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True

class MailBody(BaseModel):
    email_body: str