"""Celery application + beat schedule for the offline-cache retry loop."""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "azuregos",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Periodically drain the cache of tickets that failed to reach ADO.
    beat_schedule={
        "retry-pending-tickets": {
            "task": "app.workers.tasks.retry_pending_tickets",
            "schedule": float(settings.ado_retry_interval_seconds),
        }
    },
)

# Ensure tasks are registered when the worker imports the app.
celery_app.autodiscover_tasks(["app.workers"])

from app.workers import tasks  # noqa: E402,F401  (register tasks)
