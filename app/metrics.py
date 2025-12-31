"""Prometheus metrics and helpers for the email job pipeline."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import threading
from typing import Dict, Mapping

from prometheus_client import Counter, Gauge


# Counters for the main pipeline events.
jobs_found_total = Counter(
    "email_jobs_found_total",
    "Number of jobs discovered for processing",
    ["source"],
)
email_drafts_created_total = Counter(
    "email_drafts_created_total",
    "Number of email drafts created",
    ["campaign"],
)
send_validated_total = Counter(
    "email_send_validated_total",
    "Number of send validations approved",
    ["campaign"],
)
processing_errors_total = Counter(
    "processing_errors_total",
    "Number of errors encountered while handling jobs",
    ["stage", "reason"],
)
retry_attempts_total = Counter(
    "processing_retry_attempts_total",
    "Number of retry attempts performed",
    ["stage"],
)

# Derived gauges to expose ratios useful for alerting.
processing_error_rate = Gauge(
    "processing_error_rate",
    "Share of events that ended in an error",
    ["window"],
)
retry_ratio = Gauge(
    "processing_retry_ratio",
    "Share of events that required a retry",
    ["window"],
)


@dataclass
class MetricsSnapshot:
    """A human-friendly view of counters and ratios."""

    jobs_found: Dict[str, int]
    email_drafts: Dict[str, int]
    send_validated: Dict[str, int]
    errors: Dict[str, Dict[str, int]]
    retries: Dict[str, int]
    error_rate: float
    retry_rate: float


class MetricsRecorder:
    """Thread-safe helper for updating counts and derived ratios."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._totals: Dict[str, int] = defaultdict(int)
        self._errors_by_stage_reason: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._jobs_by_source: Dict[str, int] = defaultdict(int)
        self._drafts_by_campaign: Dict[str, int] = defaultdict(int)
        self._sends_by_campaign: Dict[str, int] = defaultdict(int)
        self._retries_by_stage: Dict[str, int] = defaultdict(int)

    def _bump(self, key: str, labels: Mapping[str, str] | None = None) -> None:
        labels = labels or {}
        with self._lock:
            self._totals[key] += 1
            if key == "error":
                stage = labels.get("stage", "unknown")
                reason = labels.get("reason", "unspecified")
                self._errors_by_stage_reason[stage][reason] += 1
            elif key == "job_found":
                source = labels.get("source", "unspecified")
                self._jobs_by_source[source] += 1
            elif key == "email_draft":
                campaign = labels.get("campaign", "uncategorized")
                self._drafts_by_campaign[campaign] += 1
            elif key == "send_validated":
                campaign = labels.get("campaign", "uncategorized")
                self._sends_by_campaign[campaign] += 1
            elif key == "retry":
                stage = labels.get("stage", "unknown")
                self._retries_by_stage[stage] += 1
            self._update_ratios_locked()

    def record_job_found(self, source: str = "unspecified") -> None:
        jobs_found_total.labels(source=source).inc()
        self._bump("job_found", {"source": source})

    def record_email_draft(self, campaign: str = "uncategorized") -> None:
        email_drafts_created_total.labels(campaign=campaign).inc()
        self._bump("email_draft", {"campaign": campaign})

    def record_send_validated(self, campaign: str = "uncategorized") -> None:
        send_validated_total.labels(campaign=campaign).inc()
        self._bump("send_validated", {"campaign": campaign})

    def record_error(self, stage: str = "unknown", reason: str = "unspecified") -> None:
        processing_errors_total.labels(stage=stage, reason=reason).inc()
        self._bump("error", {"stage": stage, "reason": reason})

    def record_retry(self, stage: str = "unknown") -> None:
        retry_attempts_total.labels(stage=stage).inc()
        self._bump("retry", {"stage": stage})

    def _update_ratios_locked(self) -> None:
        processed = (
            self._totals["job_found"]
            + self._totals["email_draft"]
            + self._totals["send_validated"]
            + self._totals["error"]
        )
        denominator = max(processed, 1)
        error_rate_value = self._totals["error"] / denominator
        retry_rate_value = self._totals["retry"] / denominator
        processing_error_rate.labels(window="lifetime").set(error_rate_value)
        retry_ratio.labels(window="lifetime").set(retry_rate_value)

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            processed = (
                self._totals["job_found"]
                + self._totals["email_draft"]
                + self._totals["send_validated"]
                + self._totals["error"]
            )
            denominator = max(processed, 1)
            return MetricsSnapshot(
                jobs_found=dict(self._jobs_by_source),
                email_drafts=dict(self._drafts_by_campaign),
                send_validated=dict(self._sends_by_campaign),
                errors={k: dict(v) for k, v in self._errors_by_stage_reason.items()},
                retries=dict(self._retries_by_stage),
                error_rate=self._totals["error"] / denominator,
                retry_rate=self._totals["retry"] / denominator,
            )


recorder = MetricsRecorder()
