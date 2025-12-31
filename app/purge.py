from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.audit import AuditRegistry
from app.data_store import PersonalDataStore


@dataclass
class DataRetentionPolicy:
    days: int


class DataPurgeService:
    """Service for removing personal data based on retention policy."""

    def __init__(self, store: PersonalDataStore, audit: AuditRegistry, policy: DataRetentionPolicy) -> None:
        if policy.days < 0:
            raise ValueError("Retention days cannot be negative.")
        self.store = store
        self.audit = audit
        self.policy = policy

    def purge_expired(self, actor: str) -> List[str]:
        deleted_subjects = self.store.purge_older_than(self.policy.days)
        for subject_id in deleted_subjects:
            self.audit.log_access(resource=f"personal_data:{subject_id}", actor=actor, metadata={"action": "purge"})
        return deleted_subjects
