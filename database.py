import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, JSON
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
    screenshot_url = Column(String, nullable=True)
    mail_sent = Column(Boolean, default=False)
    generated_email = Column(Text, nullable=True)
    email_subject = Column(String, nullable=True)
    final_email = Column(Text, nullable=True)
    ghl_contact_id = Column(String, nullable=True)
    pagespeed_diagnostics = Column(JSON, nullable=True)
    accessibility_score = Column(Integer, nullable=True)
    seo_score = Column(Integer, nullable=True)
    best_practices_score = Column(Integer, nullable=True)
    pagespeed_metrics_mobile = Column(JSON, nullable=True)
    pagespeed_metrics_desktop = Column(JSON, nullable=True)
    sent_to_salesrobot = Column(Boolean, default=False)


# Base.metadata.drop_all(bind=engine)  # Drop existing tables
Base.metadata.create_all(bind=engine)  # Create the tables again