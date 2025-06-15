import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

class LeadDB(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, unique=True, index=True)
    title = Column(String, nullable=True)
    company = Column(String)
    website_url = Column(String)
    linkedin_url = Column(String)
    website_speed_web = Column(Integer, nullable=True)
    website_speed_mobile = Column(Integer, nullable=True)

# Create the table if it doesn't exist
Base.metadata.create_all(bind=engine)
