"""Small FastAPI application exposing Prometheus metrics and webhook alerts."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import metrics


class JobFoundPayload(BaseModel):
    source: str = Field("unspecified", description="Where the job was discovered")


class EmailDraftPayload(BaseModel):
    campaign: str = Field(
        "uncategorized", description="Campaign or template that produced the draft"
    )


class SendValidatedPayload(BaseModel):
    campaign: str = Field(
        "uncategorized", description="Campaign that completed send validation"
    )


class ErrorPayload(BaseModel):
    stage: str = Field("unknown", description="Pipeline stage where the error occurred")
    reason: str = Field("unspecified", description="Human-friendly error reason")


class RetryPayload(BaseModel):
    stage: str = Field("unknown", description="Stage that required a retry")


class AlertThresholds(BaseModel):
    error_rate: float = Field(0.1, description="Alert when error rate exceeds this value")
    retry_rate: float = Field(0.2, description="Alert when retry ratio exceeds this value")
    cooldown_seconds: int = Field(
        300, description="Minimum time between two alerts of the same type"
    )


class AlertManager:
    """Minimal webhook alerting based on metric ratios."""

    def __init__(self, webhook_url: Optional[str], thresholds: AlertThresholds) -> None:
        self.webhook_url = webhook_url
        self.thresholds = thresholds
        self._last_alerted: Dict[str, float] = {}

    async def maybe_alert(self, snapshot: metrics.MetricsSnapshot) -> None:
        if not self.webhook_url:
            return

        alerts: List[Dict[str, Any]] = []
        now = time.time()

        if snapshot.error_rate >= self.thresholds.error_rate:
            alerts.append(
                {
                    "title": "Taux d'erreur élevé",
                    "body": f"Taux d'erreur: {snapshot.error_rate:.2%}",
                    "severity": "high",
                }
            )

        if snapshot.retry_rate >= self.thresholds.retry_rate:
            alerts.append(
                {
                    "title": "Taux de retry élevé",
                    "body": f"Taux de retry: {snapshot.retry_rate:.2%}",
                    "severity": "warning",
                }
            )

        if not alerts:
            return

        async with httpx.AsyncClient() as client:
            for alert in alerts:
                if not self._should_alert(alert["title"], now):
                    continue
                payload = {
                    "text": f"[{alert['severity'].upper()}] {alert['title']} - {alert['body']}",
                    "severity": alert["severity"],
                }
                try:
                    await client.post(self.webhook_url, json=payload, timeout=10)
                except httpx.HTTPError:
                    # Failing to deliver an alert must not crash the API.
                    continue
                self._last_alerted[alert["title"]] = now

    def _should_alert(self, key: str, now: float) -> bool:
        last = self._last_alerted.get(key)
        if last is None:
            return True
        return (now - last) >= self.thresholds.cooldown_seconds


def get_alert_manager() -> AlertManager:
    thresholds = AlertThresholds(
        error_rate=float(os.getenv("ERROR_RATE_THRESHOLD", "0.1")),
        retry_rate=float(os.getenv("RETRY_RATE_THRESHOLD", "0.2")),
        cooldown_seconds=int(os.getenv("ALERT_COOLDOWN_SECONDS", "300")),
    )
    webhook_url = os.getenv("ALERT_WEBHOOK_URL")
    return AlertManager(webhook_url=webhook_url, thresholds=thresholds)


app = FastAPI(title="friendly-parakeet metrics")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics/snapshot")
def metrics_snapshot() -> JSONResponse:
    snapshot = metrics.recorder.snapshot()
    return JSONResponse(content=jsonable_encoder(snapshot))


@app.post("/events/job-found")
async def job_found(
    payload: JobFoundPayload, alert_manager: AlertManager = Depends(get_alert_manager)
) -> JSONResponse:
    metrics.recorder.record_job_found(source=payload.source)
    await alert_manager.maybe_alert(metrics.recorder.snapshot())
    return JSONResponse({"status": "recorded", "event": "job_found"})


@app.post("/events/email-draft")
async def email_draft(
    payload: EmailDraftPayload, alert_manager: AlertManager = Depends(get_alert_manager)
) -> JSONResponse:
    metrics.recorder.record_email_draft(campaign=payload.campaign)
    await alert_manager.maybe_alert(metrics.recorder.snapshot())
    return JSONResponse({"status": "recorded", "event": "email_draft"})


@app.post("/events/send-validated")
async def send_validated(
    payload: SendValidatedPayload,
    alert_manager: AlertManager = Depends(get_alert_manager),
) -> JSONResponse:
    metrics.recorder.record_send_validated(campaign=payload.campaign)
    await alert_manager.maybe_alert(metrics.recorder.snapshot())
    return JSONResponse({"status": "recorded", "event": "send_validated"})


@app.post("/events/error")
async def processing_error(
    payload: ErrorPayload, alert_manager: AlertManager = Depends(get_alert_manager)
) -> JSONResponse:
    metrics.recorder.record_error(stage=payload.stage, reason=payload.reason)
    await alert_manager.maybe_alert(metrics.recorder.snapshot())
    return JSONResponse({"status": "recorded", "event": "error"})


@app.post("/events/retry")
async def processing_retry(
    payload: RetryPayload, alert_manager: AlertManager = Depends(get_alert_manager)
) -> JSONResponse:
    metrics.recorder.record_retry(stage=payload.stage)
    await alert_manager.maybe_alert(metrics.recorder.snapshot())
    return JSONResponse({"status": "recorded", "event": "retry"})


@app.get("/metrics")
def prometheus_metrics() -> PlainTextResponse:
    data = generate_latest()
    return PlainTextResponse(data, media_type=CONTENT_TYPE_LATEST)
