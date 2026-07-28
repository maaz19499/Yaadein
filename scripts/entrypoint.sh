#!/bin/sh
set -e

echo "Starting Celery worker in background..."
export C_FORCE_ROOT=1
celery -A src.workers.app.celery_app worker --loglevel=info &

echo "Starting Uvicorn web server on port ${PORT:-8000}..."
exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
