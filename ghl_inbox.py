import os
import httpx
from fastapi import APIRouter, HTTPException, Request
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import List, Optional

GHL_API_BASE = "https://services.leadconnectorhq.com"
GoHighLevel_key = os.getenv("GOHIGHLEVEL_KEY")
LOCATION_ID = os.getenv("GOHIGHLEVEL_LOCATION_ID")

HEADERS = {
    "Authorization": f"Bearer {GoHighLevel_key}",
    "Version": "2021-04-15",
    "Accept": "application/json"
}

router = APIRouter(prefix="/emails", tags=["Inbox"])

class Message(BaseModel):
    sender: str  # "agent" or "user"
    content: str

class RegenerateEmailRequest(BaseModel):
    contact_id: int
    conversation_id: Optional[str] = None
    previous_messages: List[Message]

class RegenerateEmailResponse(BaseModel):
    regenerated_email: str

@router.get("/inbox")
async def get_inbox_conversations(limit: int = 20, startAfter: str = None):
    url = f"{GHL_API_BASE}/conversations/?locationId={LOCATION_ID}&limit={limit}"
    if startAfter:
        url += f"&startAfter={startAfter}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
            raw_conversations = data.get("conversations", [])

            email_conversations = []
            for convo in raw_conversations:
                if convo.get("lastMessageType") == "TYPE_EMAIL":
                    email_conversations.append({
                        "conversation_id": convo.get("id"),
                        "contact_id": convo.get("contactId"),
                        "contact_name": convo.get("contact", {}).get("name"),
                        "last_message_snippet": convo.get("lastMessageText"),
                        "last_updated": convo.get("updatedAt")
                    })

            return {"inbox": email_conversations}

    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)

@router.get("/{conversation_id}")
async def get_conversation_messages(conversation_id: str):
    messages_url = f"{GHL_API_BASE}/conversations/{conversation_id}/messages"

    def purge_html(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(messages_url, headers=HEADERS)
            resp.raise_for_status()
            message_metadata = resp.json().get("messages", {}).get("messages", [])

            full_messages = []
            for msg in message_metadata:
                msg_id = msg.get("id")
                if not msg_id:
                    continue

                detail_url = f"{GHL_API_BASE}/conversations/messages/{msg_id}"
                detail_resp = await client.get(detail_url, headers=HEADERS)
                detail_resp.raise_for_status()

                # FIXED: message is nested under "message"
                detail_response = detail_resp.json().get("message", {})

                raw_body = detail_response.get("body", "")
                clean_body = purge_html(raw_body)

                full_messages.append({
                    "id": msg_id,
                    "type": msg.get("messageType"),
                    "direction": msg.get("direction"),
                    "body": clean_body,
                    "date": msg.get("dateAdded")
                })

            # Sort messages by date
            full_messages.sort(key=lambda x: x["date"])

            return {"conversation_id": conversation_id, "messages": full_messages}

    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)

@router.post("/regenerate", response_model=RegenerateEmailResponse)
async def regenerate_email(payload: RegenerateEmailRequest, request: Request):
    body = await request.body()
    print("Raw request body:\n", body.decode("utf-8"))
    contact_id = payload.contact_id
    conversation_id = payload.conversation_id
    messages = payload.previous_messages

    # Find the last agent and user messages
    last_agent_msg = next((m.content for m in reversed(messages) if m.sender == "agent"), "")
    last_user_msg = next((m.content for m in reversed(messages) if m.sender == "user"), None)

    if last_user_msg:
        # Respin previous agent message as a clarification or gentle reminder
        regenerated = (
            f"{last_agent_msg}\n\nJust following up in case you missed my previous message. "
            "Happy to answer any questions or provide more info!"
        )
    else:
        # No user response → follow-up email
        regenerated = (
            "Hi again,\n\nJust reaching out to follow up on my earlier email regarding your website’s performance. "
            "I'd love to help you optimize your speed and improve results.\n\n"
            "Would you be open to a quick chat?\n\nBest,\n[Your Name]"
        )

    return RegenerateEmailResponse(regenerated_email=regenerated)