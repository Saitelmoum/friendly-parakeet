from __future__ import annotations

import os

from celery import Celery

from .config import AppConfig
from .logging_config import configure_logging
from .metrics import start_metrics_server


configure_logging()
config = AppConfig.from_env()

celery_app = Celery(
    "friendly_parakeet",
    broker=config.broker_url,
    backend=config.result_backend,
)

celery_app.conf.update(
    task_default_queue="friendly-parakeet",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_time_limit=config.task_time_limit,
    task_soft_time_limit=config.task_soft_time_limit,
)

if config.metrics_port:
    start_metrics_server(config.metrics_port)


__all__ = ["celery_app", "config"]
