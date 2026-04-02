from celery import Celery

from app.config import settings

celery_app = Celery("muefs", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Detroit",
    enable_utc=True,
)
