import os
from celery import Celery
from dotenv import load_dotenv
import ssl

# Load environment variables from .env file
load_dotenv()

# Fetch the Redis URL from environment variables
REDIS_URL = os.getenv("REDIS_URL", "rediss://default:Ae_SAAIjcDE0ZWRmNzU2OWM4MDc0ZmM2OTg4MjU1NjBjOTliNDVhYXAxMA@expert-dinosaur-61394.upstash.io:6379/0?ssl_cert_reqs=CERT_NONE")

# Initialize Celery with Redis as broker and backend
celery_app = Celery(
    "tasks", 
    broker=REDIS_URL,  # Broker URL
    backend=REDIS_URL   # Result backend URL
)

# Configure the Celery app to use SSL
celery_app.conf.update(
    broker_use_ssl=True,  # Use SSL for the broker connection
    result_backend_use_ssl=True,  # Use SSL for the backend connection
    broker_transport_options={"ssl_cert_reqs": ssl.CERT_NONE},  # Disable SSL verification (for Upstash)
    result_backend_transport_options={"ssl_cert_reqs": ssl.CERT_NONE},  # Same for result backend
)

# Ensure configuration is correct
print(f"Celery Result Backend: {celery_app.conf.result_backend}")

# Import background tasks (ensure these modules are correctly implemented)
import background_speedtest
import background_tasks
