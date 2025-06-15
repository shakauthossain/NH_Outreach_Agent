from typing import Optional
from pydantic import BaseModel

class Lead(BaseModel):
    first_name: str
    last_name: Optional[str]
    email: str
    title: Optional[str] = None
    company: str
    website_url: Optional[str]
    linkedin_url: Optional[str]  # ✅ allow nulls from Apollo

    class Config:
        orm_mode = True