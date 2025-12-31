from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

AUDIT_LOG_PATH = Path("logs/audit.log")


def _ensure_log_directory(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class AuditEvent:
    """Structured audit payload for traceability."""

    category: str
    action: str
    subject: str
    actor: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self) -> str:
        serializable = asdict(self)
        serializable["occurred_at"] = self.occurred_at.isoformat()
        return json.dumps(serializable, ensure_ascii=False)


class AuditRegistry:
    """Centralized audit registry for sensitive events."""

    def __init__(self, log_path: Path = AUDIT_LOG_PATH) -> None:
        _ensure_log_directory(log_path)
        self.log_path = log_path
        self._lock = threading.Lock()
        logger_name = f"audit.{self.log_path}"
        self._logger = logging.getLogger(logger_name)
        if not self._logger.handlers:
            handler = logging.FileHandler(self.log_path, encoding="utf-8")
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)

    def log_access(self, resource: str, *, actor: str, metadata: Dict[str, Any] | None = None) -> AuditEvent:
        """Record an access to a protected resource."""
        event = AuditEvent(
            category="access",
            action="read",
            subject=resource,
            actor=actor,
            metadata=metadata or {},
        )
        self._write(event)
        return event

    def log_email(self, recipient: str, *, subject: str, actor: str, metadata: Dict[str, Any] | None = None) -> AuditEvent:
        """Record an outbound email event."""
        event = AuditEvent(
            category="email",
            action="send",
            subject=subject,
            actor=actor,
            metadata={"recipient": recipient, **(metadata or {})},
        )
        self._write(event)
        return event

    def _write(self, event: AuditEvent) -> None:
        serialized = event.to_json()
        with self._lock:
            self._logger.info(serialized)
