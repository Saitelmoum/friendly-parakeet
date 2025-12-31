from __future__ import annotations

import logging
import sys
from typing import Any, Dict

import structlog


def configure_logging() -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


def bind_task_context(task_name: str, task_id: str, source: str) -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task=task_name, task_id=task_id, source=source)


def log_event(event: str, **kwargs: Dict[str, Any]) -> None:
    logger = structlog.get_logger()
    logger.info(event, **kwargs)
