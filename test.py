import requests
import time
import csv

API_KEY = "pit-d9c5edbd-3052-4bf4-bdff-0ac6a7f5ae45"
LOCATION_ID = "rUN95HmRJPwHvhPNFuz0"

BASE_URL = "https://services.leadconnectorhq.com/contacts/"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Version": "2021-07-28",
    "Content-Type": "application/json"
}

def extract_custom_field(contact, field_key):
    """Get a custom field value by field key"""
    custom_fields = contact.get("customField", {})
    return custom_fields.get(field_key, "")

def get_all_contacts():
    all_contacts = []
    seen_ids = set()
    limit = 100
    start_after_id = None

    while True:
        params = {
            "locationId": LOCATION_ID,
            "limit": limit
        }

        if start_after_id:
            params["startAfterId"] = start_after_id

        response = requests.get(BASE_URL, headers=HEADERS, params=params)

        if response.status_code != 200:
            print("❌ Error:", response.status_code, response.text)
            break

        data = response.json()
        contacts = data.get("contacts", [])

        if not contacts:
            break

        last_id = contacts[-1]["id"]
        if last_id in seen_ids:
            print("Duplicate last ID detected — stopping to avoid infinite loop.")
            break

        seen_ids.add(last_id)
        all_contacts.extend(contacts)
        print(f"Fetched {len(contacts)} contacts (Total: {len(all_contacts)})")

        start_after_id = last_id
        time.sleep(0.5)

    return all_contacts

def save_contacts_to_csv(contacts, filename="ghl_leads.csv"):
    fieldnames = ["first_name", "last_name", "designation", "company_name", "email", "website_url"]

    with open(filename, mode="w", newline='', encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for c in contacts:
            writer.writerow({
                "first_name": c.get("firstName", ""),
                "last_name": c.get("lastName", ""),
                "designation": c.get("designation", ""),
                "company_name": c.get("companyName", ""),
                "email": c.get("email", ""),
                "website_url": c.get("website", ""),
            })

    print(f"\nSaved {len(contacts)} contacts to {filename}")


# Run
contacts = get_all_contacts()
save_contacts_to_csv(contacts)