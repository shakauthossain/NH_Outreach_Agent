#!/bin/bash
uvicorn main:app --host 0.0.0.0 --port 8000 &
celery -A celery_worker.celery_app worker --loglevel=info &
wait