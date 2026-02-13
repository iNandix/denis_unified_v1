"""Procedural memory storage for learned macros."""

from __future__ import annotations

from typing import Any

from denis_unified_v1.memory.backends import RedisBackend, utc_now


class ProceduralMemory:
    def __init__(self, redis_backend: RedisBackend) -> None:
        self.redis = redis_backend

    def save_macro(
        self,
        *,
        macro_name: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "macro_name": macro_name,
            "definition": definition,
            "updated_utc": utc_now(),
        }
        self.redis.hset_json("memory:procedural:macros", macro_name, payload)
        return {"status": "ok", "macro_name": macro_name}

    def get_macro(self, macro_name: str) -> dict[str, Any] | None:
        return self.redis.hget_json("memory:procedural:macros", macro_name)

    def list_macros(self) -> dict[str, dict[str, Any]]:
        return self.redis.hgetall_json("memory:procedural:macros")
