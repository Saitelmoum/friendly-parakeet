from __future__ import annotations

import threading
import time
from typing import Dict

from kombu.utils.limits import TokenBucket

from .config import AppConfig


_SECONDS_PER_UNIT = {"s": 1, "m": 60, "h": 3600}


def _parse_rate(rate: str) -> float:
    try:
        tokens, per = rate.split("/")
        tokens = float(tokens)
        seconds = _SECONDS_PER_UNIT.get(per, 60)
        return tokens / seconds
    except (ValueError, TypeError):
        return 0.0


class SourceThrottler:
    def __init__(self, config: AppConfig):
        self._config = config
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def _bucket_for(self, source: str) -> TokenBucket:
        with self._lock:
            if source not in self._buckets:
                rate_limit = self._config.rate_limit_for(source)
                replenish_rate = _parse_rate(rate_limit)
                capacity = max(int(replenish_rate * _SECONDS_PER_UNIT.get("m", 60)), 1)
                self._buckets[source] = TokenBucket(replenish_rate, capacity)
            return self._buckets[source]

    def allow(self, source: str) -> bool:
        bucket = self._bucket_for(source)
        now = time.monotonic()
        if bucket.can_consume(1, now):
            bucket.consume(1, now)
            return True
        return False
