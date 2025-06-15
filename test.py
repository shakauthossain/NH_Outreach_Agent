from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, LeadDB
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# SQLite (source) setup
sqlite_engine = create_engine("sqlite:///./leads.db", connect_args={"check_same_thread": False})
SQLiteSession = sessionmaker(bind=sqlite_engine)
sqlite_db = SQLiteSession()

# PostgreSQL (destination - NeonDB) setup
postgres_url = os.getenv("DATABASE_URL")
postgres_engine = create_engine(postgres_url)
PostgresSession = sessionmaker(bind=postgres_engine)
postgres_db = PostgresSession()

# Make sure tables exist in PostgreSQL
Base.metadata.create_all(bind=postgres_engine)

# Read leads from SQLite
leads = sqlite_db.query(LeadDB).all()

print(f"Found {len(leads)} leads to migrate.")

migrated = 0
for lead in leads:
    # Check for duplicates by email in Neon
    existing = postgres_db.query(LeadDB).filter_by(email=lead.email).first()
    if existing:
        continue

    try:
        new_lead = LeadDB(
            first_name=lead.first_name,
            last_name=lead.last_name,
            email=lead.email,
            title=lead.title,
            company=lead.company,
            website_url=lead.website_url,
            linkedin_url=lead.linkedin_url
        )
        postgres_db.add(new_lead)
        postgres_db.commit()
        migrated += 1
    except Exception as e:
        postgres_db.rollback()
        print("Error:", e)

print(f"✅ Migration complete: {migrated} leads added to NeonDB.")
