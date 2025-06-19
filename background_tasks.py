from celery_worker import celery_app
from pagespeed import refresh_speed_for_lead

@celery_app.task
def run_speed_test(lead_id: int):
    web, mob = refresh_speed_for_lead(lead_id)
    if web is None and mob is None:
        return {"error": "Speed test failed or lead not found"}
    print(f"[Celery] Updated lead {lead_id}: web={web}, mob={mob}")
    return {"message": f"Updated: W-{web}, M-{mob}"}
