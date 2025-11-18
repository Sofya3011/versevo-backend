from celery import Celery
import os
from dotenv import load_dotenv
load_dotenv()

CELERY_BROKER = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery_app = Celery("versevo_worker", broker=CELERY_BROKER, backend=CELERY_BACKEND)
celery_app.conf.update(
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_track_started=True
)