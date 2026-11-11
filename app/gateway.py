import os
from celery import Celery

celery_app = Celery(
    "agentic_platform",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0",
    include=["app.worker"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    task_time_limit=300,
    task_soft_time_limit=270,
    worker_max_tasks_per_child=1000,
    worker_enable_remote_control=False,
    worker_hijack_root_logger=False,
    task_track_started=True,
    result_expires=3600,
)