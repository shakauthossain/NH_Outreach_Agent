from GoHighLevel import fetch_gohighlevel_leads  # Update to match actual module path

def test_fetch_and_display_leads():
    print("Fetching leads from GoHighLevel...\n")

    try:
        leads = fetch_gohighlevel_leads(desired_count=5)

        if not leads:
            print("No leads returned.")
            return

        for i, lead in enumerate(leads, start=1):
            print(f"Lead #{i}")
            print(f"  ID: {lead.id}")
            print(f"  GHL Contact ID: {lead.ghl_contact_id}")
            print(f"  Name: {lead.first_name} {lead.last_name}")
            print(f"  Email: {lead.email}")
            print(f"  Company: {lead.company}")
            print(f"  Title: {lead.title}")
            print(f"  Website: {lead.website_url}")
            print(f"  LinkedIn: {lead.linkedin_url}")
            print("-" * 40)

    except Exception as e:
        print("Error fetching leads:", e)


if __name__ == "__main__":
    test_fetch_and_display_leads()
