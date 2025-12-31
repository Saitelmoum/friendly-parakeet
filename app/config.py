from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional


DEFAULT_RATE_LIMIT = "30/m"


@dataclass
class AppConfig:
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    default_rate_limit: str = DEFAULT_RATE_LIMIT
    source_rate_limits: Dict[str, str] = field(default_factory=dict)
    metrics_port: Optional[int] = 9100
    task_time_limit: int = 300
    task_soft_time_limit: int = 240

    @classmethod
    def from_env(cls) -> "AppConfig":
        source_limits_env = os.getenv("SOURCE_RATE_LIMITS", "{}")
        try:
            source_limits = json.loads(source_limits_env)
        except json.JSONDecodeError:
            source_limits = {}

        metrics_port = os.getenv("METRICS_PORT")
        return cls(
            broker_url=os.getenv("CELERY_BROKER_URL", cls.broker_url),
            result_backend=os.getenv("CELERY_RESULT_BACKEND", cls.result_backend),
            default_rate_limit=os.getenv("DEFAULT_RATE_LIMIT", DEFAULT_RATE_LIMIT),
            source_rate_limits=source_limits,
            metrics_port=int(metrics_port) if metrics_port else None,
            task_time_limit=int(os.getenv("TASK_TIME_LIMIT", cls.task_time_limit)),
            task_soft_time_limit=int(
                os.getenv("TASK_SOFT_TIME_LIMIT", cls.task_soft_time_limit)
            ),
        )

    def rate_limit_for(self, source: str) -> str:
        return self.source_rate_limits.get(source, self.default_rate_limit)
