"""Thread-safe-ish entity registry with TTL checks for cortex layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import threading
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RegistryEntry:
    entity_id: str
    source: str
    category: str
    created_at: datetime
    expires_at: datetime
    metadata: dict[str, Any]


class EntityRegistry:
    def __init__(self, default_ttl_seconds: int = 300) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, RegistryEntry] = {}

    def upsert(
        self,
        entity_id: str,
        source: str,
        category: str,
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> RegistryEntry:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        now = _utc_now()
        entry = RegistryEntry(
            entity_id=entity_id,
            source=source,
            category=category,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            metadata=metadata or {},
        )
        with self._lock:
            self._entries[entity_id] = entry
        return entry

    def get(self, entity_id: str) -> RegistryEntry | None:
        with self._lock:
            entry = self._entries.get(entity_id)
            if entry is None:
                return None
            if entry.expires_at <= _utc_now():
                del self._entries[entity_id]
                return None
            return entry

    def list_active(self) -> list[RegistryEntry]:
        now = _utc_now()
        active: list[RegistryEntry] = []
        with self._lock:
            expired = [k for k, v in self._entries.items() if v.expires_at <= now]
            for key in expired:
                del self._entries[key]
            active.extend(self._entries.values())
        return active

