from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Protocol


class SecretBackend(Protocol):
    """Contract for secure secret backends."""

    def get_secret(self, name: str) -> Optional[str]:
        """Return a secret value or None if missing."""
        ...


@dataclass
class EnvBackend:
    """Secret backend that pulls values from environment variables.

    This backend expects environment variables prefixed with `SECRET_` by default.
    The prefix can be overridden to support multiple namespaces.
    """

    prefix: str = "SECRET_"

    def get_secret(self, name: str) -> Optional[str]:
        return os.environ.get(f"{self.prefix}{name}".upper())


@dataclass
class FileBackend:
    """Secret backend that reads from a JSON file stored on disk.

    The file should contain a flat mapping of secret names to values. This backend
    is intended for development and testing; production deployments should use a
    dedicated secrets manager.
    """

    path: Path

    def __post_init__(self) -> None:
        self._cache: Dict[str, str] = {}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                try:
                    data = json.load(handle)
                except json.JSONDecodeError:
                    data = {}
                if isinstance(data, dict):
                    self._cache = {str(k): str(v) for k, v in data.items()}

    def get_secret(self, name: str) -> Optional[str]:
        return self._cache.get(name)


class SecretsLoader:
    """Aggregates multiple backends to resolve secrets from a secure source."""

    def __init__(self, backends: Iterable[SecretBackend]) -> None:
        self.backends = list(backends)
        if not self.backends:
            raise ValueError("At least one secret backend must be provided.")

    def get(self, name: str, *, default: Optional[str] = None) -> Optional[str]:
        """Return the first matching secret from configured backends.

        Args:
            name: Logical secret name.
            default: Optional fallback value if no backend contains the secret.
        """
        for backend in self.backends:
            value = backend.get_secret(name)
            if value is not None:
                return value
        return default


def default_loader() -> SecretsLoader:
    """Return a SecretsLoader pre-configured for local development."""

    file_backend = FileBackend(path=Path(os.environ.get("SECRETS_FILE", "secrets.json")))
    env_backend = EnvBackend(prefix=os.environ.get("SECRET_PREFIX", "SECRET_"))
    return SecretsLoader(backends=(env_backend, file_backend))
