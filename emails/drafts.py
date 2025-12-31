from __future__ import annotations

import base64
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import jinja2
import requests

logger = logging.getLogger(__name__)


class DraftStatus(str, Enum):
    """Possible statuses for a draft lifecycle."""

    CREATED = "created"
    FAILED = "failed"


@dataclass
class DraftResult:
    """Result returned by a mail provider when a draft is created."""

    provider_id: Optional[str]
    provider: str
    status: DraftStatus
    raw_response: Optional[dict] = None


@dataclass
class DraftRecord:
    """Persisted record of a draft."""

    id: int
    provider_id: Optional[str]
    provider: str
    status: DraftStatus
    subject: str
    recipients: str
    created_at: str
    metadata: Optional[dict] = None


class EmailTemplateRenderer:
    """Render email bodies with Jinja templates."""

    def __init__(self, template_dirs: Optional[List[Path]] = None) -> None:
        loader = None
        if template_dirs:
            loader = jinja2.FileSystemLoader([str(path) for path in template_dirs])
        self.environment = jinja2.Environment(
            loader=loader,
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )

    def render_from_string(self, template_source: str, context: Dict) -> str:
        template = self.environment.from_string(template_source)
        return template.render(**context)

    def render_from_file(self, template_path: Path, context: Dict) -> str:
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        if not self.environment.loader:
            loader = jinja2.FileSystemLoader(str(template_path.parent))
            self.environment.loader = loader
        template = self.environment.get_template(template_path.name)
        return template.render(**context)


class MailDraftClient:
    """Contract for providers capable of creating drafts."""

    provider: str

    def create_draft(
        self,
        *,
        subject: str,
        body_html: str,
        to: Iterable[str],
        cc: Optional[Iterable[str]] = None,
        bcc: Optional[Iterable[str]] = None,
        sender: Optional[str] = None,
    ) -> DraftResult:
        raise NotImplementedError


class GmailDraftClient(MailDraftClient):
    """Draft creation via the Gmail API."""

    def __init__(self, access_token: str, user_id: str = "me", timeout: int = 10) -> None:
        self.access_token = access_token
        self.user_id = user_id
        self.timeout = timeout
        self.provider = "gmail"
        self.session = requests.Session()

    def _build_message(
        self,
        *,
        subject: str,
        body_html: str,
        to: Iterable[str],
        cc: Optional[Iterable[str]],
        bcc: Optional[Iterable[str]],
        sender: Optional[str],
    ) -> str:
        message = EmailMessage()
        message["Subject"] = subject
        message["To"] = ", ".join(to)
        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)
        if sender:
            message["From"] = sender
        message.set_content(body_html, subtype="html")
        raw_bytes = message.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    def create_draft(
        self,
        *,
        subject: str,
        body_html: str,
        to: Iterable[str],
        cc: Optional[Iterable[str]] = None,
        bcc: Optional[Iterable[str]] = None,
        sender: Optional[str] = None,
    ) -> DraftResult:
        draft_body = {
            "message": {
                "raw": self._build_message(
                    subject=subject, body_html=body_html, to=to, cc=cc, bcc=bcc, sender=sender
                )
            }
        }
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        url = f"https://gmail.googleapis.com/gmail/v1/users/{self.user_id}/drafts"
        try:
            response = self.session.post(url, headers=headers, json=draft_body, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            logger.debug("Gmail draft created: %s", payload)
            return DraftResult(
                provider_id=payload.get("id"),
                provider=self.provider,
                status=DraftStatus.CREATED,
                raw_response=payload,
            )
        except requests.HTTPError as exc:  # pragma: no cover - network errors
            logger.error("Failed to create Gmail draft: %s", exc)
            payload = None
            try:
                payload = exc.response.json()
            except Exception:  # pragma: no cover - defensive
                payload = {"detail": str(exc)}
            return DraftResult(
                provider_id=None,
                provider=self.provider,
                status=DraftStatus.FAILED,
                raw_response=payload,
            )


class GraphDraftClient(MailDraftClient):
    """Draft creation via the Microsoft Graph API."""

    def __init__(self, access_token: str, timeout: int = 10) -> None:
        self.access_token = access_token
        self.timeout = timeout
        self.provider = "graph"
        self.session = requests.Session()

    def _format_recipients(self, recipients: Iterable[str]) -> List[dict]:
        return [{"emailAddress": {"address": address}} for address in recipients]

    def create_draft(
        self,
        *,
        subject: str,
        body_html: str,
        to: Iterable[str],
        cc: Optional[Iterable[str]] = None,
        bcc: Optional[Iterable[str]] = None,
        sender: Optional[str] = None,
    ) -> DraftResult:
        payload: Dict[str, object] = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": self._format_recipients(to),
        }
        if cc:
            payload["ccRecipients"] = self._format_recipients(cc)
        if bcc:
            payload["bccRecipients"] = self._format_recipients(bcc)
        if sender:
            payload["from"] = {"emailAddress": {"address": sender}}

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        url = "https://graph.microsoft.com/v1.0/me/messages"
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            logger.debug("Graph draft created: %s", data)
            return DraftResult(
                provider_id=data.get("id"),
                provider=self.provider,
                status=DraftStatus.CREATED,
                raw_response=data,
            )
        except requests.HTTPError as exc:  # pragma: no cover - network errors
            logger.error("Failed to create Graph draft: %s", exc)
            details = None
            try:
                details = exc.response.json()
            except Exception:  # pragma: no cover - defensive
                details = {"detail": str(exc)}
            return DraftResult(
                provider_id=None,
                provider=self.provider,
                status=DraftStatus.FAILED,
                raw_response=details,
            )


class DraftRepository:
    """Persist drafts in a SQLite database."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    recipients TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT
                )
                """
            )

    def save(
        self,
        *,
        result: DraftResult,
        subject: str,
        recipients: Iterable[str],
        metadata: Optional[Dict[str, object]] = None,
    ) -> DraftRecord:
        created_at = datetime.utcnow().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        joined_recipients = ",".join(recipients)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO drafts (provider_id, provider, status, subject, recipients, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.provider_id,
                    result.provider,
                    result.status.value,
                    subject,
                    joined_recipients,
                    created_at,
                    metadata_json,
                ),
            )
            draft_id = cursor.lastrowid
        return DraftRecord(
            id=draft_id,
            provider_id=result.provider_id,
            provider=result.provider,
            status=result.status,
            subject=subject,
            recipients=joined_recipients,
            created_at=created_at,
            metadata=metadata,
        )

    def all(self) -> List[DraftRecord]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, provider_id, provider, status, subject, recipients, created_at, metadata FROM drafts"
            ).fetchall()
        records = []
        for row in rows:
            metadata = json.loads(row[7]) if row[7] else None
            records.append(
                DraftRecord(
                    id=row[0],
                    provider_id=row[1],
                    provider=row[2],
                    status=DraftStatus(row[3]),
                    subject=row[4],
                    recipients=row[5],
                    created_at=row[6],
                    metadata=metadata,
                )
            )
        return records


class DraftService:
    """High level service to render templates and create provider drafts."""

    def __init__(
        self,
        renderer: EmailTemplateRenderer,
        repository: DraftRepository,
        clients: Dict[str, MailDraftClient],
    ) -> None:
        self.renderer = renderer
        self.repository = repository
        self.clients = clients

    def _render_template(self, template: str | Path, context: Dict) -> str:
        template_path = Path(template)
        if template_path.exists():
            return self.renderer.render_from_file(template_path, context)
        return self.renderer.render_from_string(str(template), context)

    def create_draft_from_template(
        self,
        *,
        template: str | Path,
        context: Dict,
        subject: str,
        to: Iterable[str],
        cc: Optional[Iterable[str]] = None,
        bcc: Optional[Iterable[str]] = None,
        provider: str = "gmail",
        sender: Optional[str] = None,
    ) -> DraftRecord:
        if provider not in self.clients:
            raise ValueError(f"Unknown provider '{provider}'. Available: {', '.join(self.clients)}")
        body_html = self._render_template(template, context)
        client = self.clients[provider]
        to_list = list(to)
        cc_list = list(cc) if cc else None
        bcc_list = list(bcc) if bcc else None
        result = client.create_draft(
            subject=subject, body_html=body_html, to=to_list, cc=cc_list, bcc=bcc_list, sender=sender
        )
        return self.repository.save(
            result=result, subject=subject, recipients=to_list, metadata=result.raw_response
        )


__all__ = [
    "DraftResult",
    "DraftRecord",
    "DraftRepository",
    "DraftService",
    "DraftStatus",
    "EmailTemplateRenderer",
    "GmailDraftClient",
    "GraphDraftClient",
    "MailDraftClient",
]
