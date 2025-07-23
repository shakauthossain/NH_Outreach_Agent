import os
import httpx
from fastapi import APIRouter, HTTPException

GHL_API_BASE = "https://services.leadconnectorhq.com"
GoHighLevel_key = os.getenv("GOHIGHLEVEL_KEY")
LOCATION_ID = os.getenv("GOHIGHLEVEL_LOCATION_ID")
headers = {
    "Authorization": f"Bearer {GoHighLevel_key}",
    "Version": "2021-07-28",
    "Content-Type": "application/json"
}

router = APIRouter(prefix="/emails", tags=["Inbox"])

@router.get("/inbox")
async def get_inbox_conversations():
    url = f"{GHL_API_BASE}/conversations/"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # Filter to email-type messages
            emails = [c for c in data.get("conversations", []) if c.get("type") == "Email"]
            return {"inbox": emails}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)


@router.get("/{conversation_id}")
async def get_conversation_detail(conversation_id: str):
    url = f"{GHL_API_BASE}/conversations/{conversation_id}/messages"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return {"messages": resp.json().get("messages", [])}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)


from fastapi import APIRouter, HTTPException, Query
import os
import httpx

@router.get("/search")
async def search_conversation(contact_id: str = Query(..., alias="contactId")):
    url = f"{GHL_API_BASE}/conversations/search"
    params = {
        "locationId": LOCATION_ID,
        "contactId": contact_id
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
