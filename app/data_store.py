from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

DATA_PATH = Path("data/personal_data.json")


@dataclass
class PersonalDataRecord:
    """Structured representation of personal data stored in the system."""

    subject_id: str
    payload: Dict[str, str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self) -> Dict[str, str]:
        serialized = asdict(self)
        serialized["created_at"] = self.created_at.isoformat()
        return serialized

    @classmethod
    def from_json(cls, data: Dict[str, str]) -> "PersonalDataRecord":
        created_at = datetime.fromisoformat(data["created_at"])
        return cls(subject_id=data["subject_id"], payload=data["payload"], created_at=created_at)


class PersonalDataStore:
    """File-backed personal data store with retention support."""

    def __init__(self, path: Path = DATA_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: Dict[str, PersonalDataRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            try:
                raw = json.load(handle)
            except json.JSONDecodeError:
                raw = {}
        if isinstance(raw, dict):
            for subject_id, payload in raw.items():
                try:
                    record = PersonalDataRecord.from_json(payload)
                    self._records[subject_id] = record
                except (KeyError, ValueError):
                    continue

    def _persist(self) -> None:
        serialized = {sid: record.to_json() for sid, record in self._records.items()}
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(serialized, handle, indent=2, ensure_ascii=False)

    def save(self, record: PersonalDataRecord) -> None:
        """Persist a personal data record."""
        self._records[record.subject_id] = record
        self._persist()

    def get(self, subject_id: str) -> Optional[PersonalDataRecord]:
        return self._records.get(subject_id)

    def all_records(self) -> Iterable[PersonalDataRecord]:
        return list(self._records.values())

    def purge_older_than(self, days: int) -> List[str]:
        """Delete records older than the provided retention window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted: List[str] = []
        for sid, record in list(self._records.items()):
            if record.created_at < cutoff:
                deleted.append(sid)
                self._records.pop(sid, None)
        if deleted:
            self._persist()
        return deleted
