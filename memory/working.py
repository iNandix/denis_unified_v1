"""Working memory for active conversation context with TTL."""

from __future__ import annotations

from typing import Any

from denis_unified_v1.memory.backends import RedisBackend, utc_now


class WorkingMemory:
    def __init__(self, redis_backend: RedisBackend, ttl_sec: int = 1800) -> None:
        self.redis = redis_backend
        self.ttl_sec = ttl_sec

    def set_context(
        self,
        *,
        session_id: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "session_id": session_id,
            "context": context,
            "updated_utc": utc_now(),
        }
        self.redis.setex_json(f"memory:working:session:{session_id}", self.ttl_sec, payload)
        return {"status": "ok", "session_id": session_id, "ttl_sec": self.ttl_sec}

    def get_context(self, session_id: str) -> dict[str, Any] | None:
        raw = self.redis.get(f"memory:working:session:{session_id}")
        if not raw:
            return None
        try:
            import json

            return json.loads(raw)
        except Exception:
            return None
