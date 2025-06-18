from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional

class RegisterRequest(BaseModel):
    username: str
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    password: str
    confirm_password: str

    @validator("confirm_password")
    def passwords_match(cls, v, values):
        if "password" in values and v != values["password"]:
            raise ValueError("Passwords do not match")
        return v

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserInfo(BaseModel):
    user_id: int
    username: str
    full_name: str
    email: EmailStr
    phone: Optional[str]
    company: Optional[str]
    position: Optional[str]

    class Config:
        orm_mode = True
