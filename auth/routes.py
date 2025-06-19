from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from database import SessionLocal
from .schemas import User
from .models import RegisterRequest, TokenResponse, UserInfo
from .auth_utils import hash_password, verify_password, create_access_token, SECRET_KEY, ALGORITHM

from sqlalchemy.future import select

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
    if db.query(User).filter((User.username == data.username) | (User.email == data.email)).first():
        raise HTTPException(status_code=400, detail="Username or email already exists")

    user = User(
        username=data.username,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        company=data.company,
        position=data.position,
        hashed_password=hash_password(data.password)
    )
    db.add(user)
    db.commit()
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
