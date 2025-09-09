from celery_worker import celery_app
from pagespeed import test_all_unspeeded_leads

@celery_app.task
def run_bulk_speedtest_task():
    count = test_all_unspeeded_leads()
    return {"message": f"Tested {count} websites"}
