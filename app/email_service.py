from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.audit import AuditRegistry
from config.secrets import SecretsLoader, default_loader


@dataclass
class EmailMessage:
    recipient: str
    subject: str
    body: str


class EmailService:
    """Email sender that emits audit events for every outbound message."""

    def __init__(self, *, audit: AuditRegistry, secrets: Optional[SecretsLoader] = None) -> None:
        self.audit = audit
        self.secrets = secrets or default_loader()

    def send(self, message: EmailMessage, *, actor: str) -> None:
        # In a real implementation, credentials would be pulled securely before sending.
        _ = self.secrets.get("SMTP_PASSWORD")
        self.audit.log_email(recipient=message.recipient, subject=message.subject, actor=actor)
        # Placeholder for actual email dispatch logic.
