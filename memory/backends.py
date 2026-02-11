"""Backend helpers for unified memory layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from typing import Any

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InMemoryKV:
    store: dict[str, str] = field(default_factory=dict)
    hashes: dict[str, dict[str, str]] = field(default_factory=dict)

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.store[key] = value

    def hset(self, key: str, field_name: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field_name] = value

    def hget(self, key: str, field_name: str) -> str | None:
        return self.hashes.get(key, {}).get(field_name)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))


class RedisBackend:
    def __init__(self) -> None:
        self.url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Any = None
        self._fallback = InMemoryKV()

    def _client_or_none(self):
        if redis is None:
            return None
        if self._client is None:
            try:
                self._client = redis.Redis.from_url(self.url, decode_responses=True)
                self._client.ping()
            except Exception:
                self._client = None
        return self._client

    def get(self, key: str) -> str | None:
        client = self._client_or_none()
        if client is None:
            return self._fallback.get(key)
        try:
            return client.get(key)
        except Exception:
            return self._fallback.get(key)

    def setex_json(self, key: str, ttl_sec: int, value: dict[str, Any]) -> None:
        encoded = json.dumps(value, sort_keys=True)
        client = self._client_or_none()
        if client is None:
            self._fallback.setex(key, ttl_sec, encoded)
            return
        try:
            client.setex(key, ttl_sec, encoded)
        except Exception:
            self._fallback.setex(key, ttl_sec, encoded)

    def hset_json(self, key: str, field_name: str, value: dict[str, Any]) -> None:
        encoded = json.dumps(value, sort_keys=True)
        client = self._client_or_none()
        if client is None:
            self._fallback.hset(key, field_name, encoded)
            return
        try:
            client.hset(key, field_name, encoded)
        except Exception:
            self._fallback.hset(key, field_name, encoded)

    def hget_json(self, key: str, field_name: str) -> dict[str, Any] | None:
        client = self._client_or_none()
        raw: str | None = None
        if client is None:
            raw = self._fallback.hget(key, field_name)
        else:
            try:
                raw = client.hget(key, field_name)
            except Exception:
                raw = self._fallback.hget(key, field_name)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def hgetall_json(self, key: str) -> dict[str, dict[str, Any]]:
        client = self._client_or_none()
        raw_map: dict[str, str]
        if client is None:
            raw_map = self._fallback.hgetall(key)
        else:
            try:
                raw_map = dict(client.hgetall(key))
            except Exception:
                raw_map = self._fallback.hgetall(key)
        out: dict[str, dict[str, Any]] = {}
        for field_name, raw in raw_map.items():
            try:
                out[field_name] = json.loads(raw)
            except Exception:
                continue
        return out


class Neo4jBackend:
    def __init__(self) -> None:
        try:
            from denis_unified_v1.cortex.neo4j_config_resolver import ensure_neo4j_env_auto

            ensure_neo4j_env_auto()
        except Exception:
            pass
        self.uri = os.getenv("NEO4J_URI", "bolt://10.10.10.1:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS")
        self._driver: Any = None

    def _driver_or_none(self):
        if self._driver is not None:
            return self._driver
        if not self.password:
            return None
        try:
            from neo4j import GraphDatabase  # type: ignore

            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            return self._driver
        except Exception:
            return None

    def write_cypher(self, query: str, **params: Any) -> bool:
        driver = self._driver_or_none()
        if driver is None:
            return False
        try:
            with driver.session() as session:
                session.run(query, **params)
            return True
        except Exception:
            return False

    def query_count(self, query: str, **params: Any) -> int:
        driver = self._driver_or_none()
        if driver is None:
            return 0
        try:
            with driver.session() as session:
                rec = session.run(query, **params).single()
                if not rec:
                    return 0
                return int(rec.get("count", 0))
        except Exception:
            return 0
