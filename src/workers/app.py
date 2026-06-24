from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "yaadein_workers",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=["src.workers.tasks.media", "src.workers.tasks.face"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "daily-face-clustering": {
        "task": "src.workers.tasks.face.cluster_faces_job",
        "schedule": crontab(hour=0, minute=0),
    }
}
