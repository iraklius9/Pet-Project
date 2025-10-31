import os
from celery import Celery

from src.settings import RABBITMQ_URL, REDIS_URL

celery_app = Celery(__name__, broker=RABBITMQ_URL, backend=REDIS_URL)

if os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1":
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.broker_url = "memory://"
    celery_app.conf.result_backend = "cache+memory://"

from . import tasks  # noqa: F401, E402
