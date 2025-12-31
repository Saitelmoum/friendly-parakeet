from __future__ import annotations

import random
import time
from typing import Any, Dict

from celery import Task

from .celery_app import celery_app, config
from .logging_config import bind_task_context, log_event
from .metrics import record_task
from .throttling import SourceThrottler


RETRY_BACKOFF_BASE_SECONDS = 2
MAX_RETRIES = 5


class InstrumentedTask(Task):
    abstract = True
    throttler = SourceThrottler(config)

    def exponential_backoff(self, retries: int) -> int:
        return RETRY_BACKOFF_BASE_SECONDS * (2 ** retries)

    def verify_throttle(self, source: str) -> None:
        if not self.throttler.allow(source):
            delay = self.exponential_backoff(self.request.retries)
            log_event("throttled", task=self.name, source=source, retry_in=delay)
            raise self.retry(countdown=delay, max_retries=MAX_RETRIES)

    def __call__(self, *args: Any, **kwargs: Any):
        source = kwargs.get("source", "default")
        bind_task_context(self.name, getattr(self.request, "id", "unknown"), source)
        with record_task(task=self.name, source=source):
            return super().__call__(*args, **kwargs)

    def on_failure(self, exc: Exception, task_id: str, args, kwargs, einfo):
        source = kwargs.get("source", "default")
        log_event("task_failure", task=self.name, task_id=task_id, source=source, error=str(exc))
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id: str, args, kwargs):
        source = kwargs.get("source", "default")
        log_event("task_success", task=self.name, task_id=task_id, source=source)
        super().on_success(retval, task_id, args, kwargs)


@celery_app.task(bind=True, base=InstrumentedTask, name="collect_jobs", max_retries=MAX_RETRIES)
def collect_jobs(self: InstrumentedTask, source: str, parameters: Dict[str, Any] | None = None) -> Dict[str, Any]:
    self.verify_throttle(source)
    log_event("collect_jobs_started", source=source, parameters=parameters)
    time.sleep(1)
    jobs = [{"id": random.randint(1000, 9999), "source": source}]
    log_event("collect_jobs_completed", source=source, count=len(jobs))
    return {"jobs": jobs}


@celery_app.task(bind=True, base=InstrumentedTask, name="enrich_contacts", max_retries=MAX_RETRIES)
def enrich_contacts(self: InstrumentedTask, source: str, contacts: Dict[str, Any]) -> Dict[str, Any]:
    self.verify_throttle(source)
    log_event("enrich_contacts_started", source=source, contacts=len(contacts))
    if not contacts:
        raise self.retry(countdown=self.exponential_backoff(self.request.retries))
    enriched = {**contacts, "enriched": True}
    log_event("enrich_contacts_completed", source=source)
    return enriched


@celery_app.task(bind=True, base=InstrumentedTask, name="generate_application", max_retries=MAX_RETRIES)
def generate_application(self: InstrumentedTask, source: str, job: Dict[str, Any], applicant: Dict[str, Any]) -> Dict[str, Any]:
    self.verify_throttle(source)
    log_event("generate_application_started", source=source, job_id=job.get("id"))
    application = {"job": job, "applicant": applicant, "content": "Generated application text"}
    log_event("generate_application_completed", source=source, job_id=job.get("id"))
    return application


@celery_app.task(bind=True, base=InstrumentedTask, name="draft_email", max_retries=MAX_RETRIES)
def draft_email(self: InstrumentedTask, source: str, application: Dict[str, Any]) -> Dict[str, Any]:
    self.verify_throttle(source)
    log_event("draft_email_started", source=source, job_id=application.get("job", {}).get("id"))
    email = {"to": application.get("job", {}).get("contact", "unknown"), "body": "Draft email content"}
    log_event("draft_email_completed", source=source)
    return email


@celery_app.task(bind=True, base=InstrumentedTask, name="send_email", max_retries=MAX_RETRIES)
def send_email(self: InstrumentedTask, source: str, email: Dict[str, Any]) -> str:
    self.verify_throttle(source)
    log_event("send_email_started", source=source, recipient=email.get("to"))
    if not email.get("to"):
        raise self.retry(countdown=self.exponential_backoff(self.request.retries))
    log_event("send_email_completed", source=source)
    return "sent"
