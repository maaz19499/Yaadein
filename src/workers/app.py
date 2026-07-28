import ssl
from celery import Celery
from celery.schedules import crontab
from src.config import settings

redis_url = settings.REDIS_URL

# Ensure rediss:// (Redis over SSL/TLS) URLs contain ssl_cert_reqs parameter required by Celery
if redis_url.startswith("rediss://") and "ssl_cert_reqs" not in redis_url:
    separator = "&" if "?" in redis_url else "?"
    redis_url = f"{redis_url}{separator}ssl_cert_reqs=CERT_NONE"

celery_app = Celery(
    "yaadein_workers",
    broker=redis_url,
    backend=redis_url,
    include=["src.workers.tasks.media", "src.workers.tasks.face"],
)

if redis_url.startswith("rediss://"):
    celery_app.conf.update(
        broker_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
        redis_backend_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
    )

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
)

celery_app.conf.beat_schedule = {
    "daily-face-clustering": {
        "task": "src.workers.tasks.face.cluster_faces_job",
        "schedule": crontab(hour=0, minute=0),
    }
}
