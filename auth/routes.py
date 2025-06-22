from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from .utils import send_email

from database import SessionLocal
from .schemas import User
from .models import RegisterRequest, TokenResponse, UserInfo, OTPVerifyRequest, ResendOTPRequest
from .auth_utils import hash_password, verify_password, create_access_token, SECRET_KEY, ALGORITHM

from sqlalchemy.future import select
import random
from datetime import datetime, timedelta
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    print("Incoming data:", data.dict())
    if db.query(User).filter((User.username == data.username) | (User.email == data.email)).first():
        raise HTTPException(status_code=400, detail="Username or email already exists")

    otp = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=10)

    user = User(
        username=data.username,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        company=data.company,
        position=data.position,
        hashed_password=hash_password(data.password),
        is_verified=False,
        otp_code=otp,
        otp_expires_at=expiry
    )
    db.add(user)
    db.commit()
    otp_body = (
        f"Your OTP is: {otp}\n\n"
        "It will expire in 10 minutes.\n"
        "Do not share this code with anyone."
    )
    send_email(
        to=user.email,
        subject="Your OTP Code",
        body=otp_body
    )
    return {"message": "Registered successfully. Check your email for the OTP to verify your account."}
    return {"msg": "User registered successfully", "user_id": user.user_id}

@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.email == form_data.username) | (User.username == form_data.username)
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/profile", response_model=UserInfo)
def get_me(user: User = Depends(get_current_user)):
    return user
@router.post("/logout")
def logout():
    # Token blacklisting should go here in real apps
    return {"msg": "Logout successful"}


@router.post("/verify-otp")
def verify_otp(data: OTPVerifyRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_verified:
        return {"message": "User already verified"}

    if user.otp_code != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    if user.otp_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP has expired")

    # Mark user as verified
    user.is_verified = True
    user.otp_code = None
    user.otp_expires_at = None
    db.commit()

    return {"message": "Email verified successfully"}


@router.post("/resend-otp")
def resend_otp(data: ResendOTPRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_verified:
        return {"message": "User is already verified"}

    otp = str(random.randint(100000, 999999))
    expiry = datetime.utcnow() + timedelta(minutes=10)

    user.otp_code = otp
    user.otp_expires_at = expiry
    db.commit()

    otp_body = (
        f"Your new OTP is: {otp}\n\n"
        "It will expire in 10 minutes.\n"
        "Do not share this code with anyone."
    )

    send_email(
        to=user.email,
        subject="Your New OTP Code",
        body=otp_body
    )

    return {"message": "A new OTP has been sent to your email"}