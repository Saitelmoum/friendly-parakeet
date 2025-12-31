from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import Counter, Histogram, start_http_server

_tasks_started = Counter(
    "friendly_parakeet_tasks_started_total",
    "Total tasks started",
    ["task", "source"],
)
_tasks_completed = Counter(
    "friendly_parakeet_tasks_completed_total",
    "Total tasks completed",
    ["task", "source"],
)
_tasks_failed = Counter(
    "friendly_parakeet_tasks_failed_total",
    "Total tasks failed",
    ["task", "source"],
)
_task_duration = Histogram(
    "friendly_parakeet_task_duration_seconds",
    "Task execution duration",
    ["task", "source"],
)


@contextmanager
def record_task(task: str, source: str):
    _tasks_started.labels(task=task, source=source).inc()
    start_time = time.perf_counter()
    try:
        yield
    except Exception:
        _tasks_failed.labels(task=task, source=source).inc()
        raise
    else:
        _tasks_completed.labels(task=task, source=source).inc()
    finally:
        _task_duration.labels(task=task, source=source).observe(
            time.perf_counter() - start_time
        )


def start_metrics_server(port: int) -> None:
    start_http_server(port)
