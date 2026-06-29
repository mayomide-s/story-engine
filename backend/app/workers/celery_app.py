from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery("story_engine", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "story-engine"
celery_app.autodiscover_tasks(["app.workers"])

import app.workers.jobs  # noqa: E402,F401
