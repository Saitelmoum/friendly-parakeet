from __future__ import annotations

from typing import Optional

from app.audit import AuditRegistry
from app.data_store import PersonalDataRecord, PersonalDataStore


class PersonalDataService:
    """Service to access personal data with audit tracking."""

    def __init__(self, store: PersonalDataStore, audit: AuditRegistry) -> None:
        self.store = store
        self.audit = audit

    def fetch(self, subject_id: str, *, actor: str) -> Optional[PersonalDataRecord]:
        record = self.store.get(subject_id)
        if record:
            self.audit.log_access(resource=f"personal_data:{subject_id}", actor=actor, metadata={"action": "read"})
        return record
