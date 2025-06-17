from langchain.prompts import PromptTemplate
from langchain_groq import ChatGroq
from database import SessionLocal, LeadDB
import os

def generate_email_from_lead(lead_id: int) -> str:
    db = SessionLocal()
    lead = db.query(LeadDB).filter(LeadDB.id == lead_id).first()
    db.close()

    if not lead:
        raise ValueError("Lead not found")

    prompt = PromptTemplate.from_template("""
        Write a personalized cold sales email to {first_name}, who works as {title} at {company}.
        Mention that their website {website_url} has a low performance score and we can help improve it.
        Keep the tone friendly, professional, and focused on booking a short call.
    """)

    llm = ChatGroq(
        model_name="llama3-70b-8192",
        temperature=0.7,
        groq_api_key=os.getenv("GROQ_API_KEY")
    )

    chain = prompt | llm

    # new API: use invoke instead of run()
    result = chain.invoke({
        "first_name": lead.first_name,
        "title": lead.title or "",
        "company": lead.company,
        "website_url": lead.website_url
    })

    return result.strip()
