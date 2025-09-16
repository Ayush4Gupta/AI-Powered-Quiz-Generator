# worker.py
from app.background.tasks import celery_app  # pragma: no cover

# Configure worker for better reliability
celery_app.conf.update(
    task_track_started=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    result_expires=3600,  # Results expire after 1 hour
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_prefetch_multiplier=1,  # Don't prefetch tasks
    worker_send_task_events=True,  # Enable task events
    task_send_sent_event=True  # Enable task sent events
)
