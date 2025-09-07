from celery import Celery

celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"  # Added result backend for task status/results
)
print(celery_app.conf.result_backend)
import background_tasks