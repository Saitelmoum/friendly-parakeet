from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.access import PersonalDataService
from app.audit import AuditRegistry
from app.data_store import PersonalDataRecord, PersonalDataStore
from app.email_service import EmailMessage, EmailService
from app.purge import DataPurgeService, DataRetentionPolicy
from config.secrets import EnvBackend, SecretsLoader


def test_secrets_loader_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_API_KEY", "super-secret")
    loader = SecretsLoader(backends=[EnvBackend()])
    assert loader.get("API_KEY") == "super-secret"
    assert loader.get("MISSING", default="fallback") == "fallback"


def test_audit_registry_records_access_and_email(tmp_path):
    log_path = tmp_path / "audit.log"
    audit = AuditRegistry(log_path=log_path)
    store = PersonalDataStore(path=tmp_path / "data.json")
    service = PersonalDataService(store=store, audit=audit)
    store.save(PersonalDataRecord(subject_id="123", payload={"email": "user@example.com"}))

    service.fetch("123", actor="alice")

    email_service = EmailService(audit=audit, secrets=SecretsLoader(backends=[EnvBackend()]))
    email_service.send(EmailMessage(recipient="user@example.com", subject="Hello", body="Welcome"), actor="alice")

    contents = log_path.read_text(encoding="utf-8")
    assert '"category": "access"' in contents
    assert '"category": "email"' in contents


def test_data_purge_removes_old_records_and_audits(tmp_path):
    log_path = tmp_path / "audit.log"
    audit = AuditRegistry(log_path=log_path)
    store = PersonalDataStore(path=tmp_path / "data.json")

    old_record = PersonalDataRecord(
        subject_id="old",
        payload={"email": "old@example.com"},
        created_at=datetime.now(timezone.utc) - timedelta(days=60),
    )
    recent_record = PersonalDataRecord(
        subject_id="recent",
        payload={"email": "recent@example.com"},
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    store.save(old_record)
    store.save(recent_record)

    purge_service = DataPurgeService(store=store, audit=audit, policy=DataRetentionPolicy(days=30))
    deleted = purge_service.purge_expired(actor="system")

    assert deleted == ["old"]
    assert store.get("old") is None
    assert store.get("recent") is not None
    contents = log_path.read_text(encoding="utf-8")
    assert '"action": "read"' in contents
