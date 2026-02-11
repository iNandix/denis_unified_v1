"""Read-only dashboard helpers/routes for metagraph phase."""

from __future__ import annotations

import json
import os
from typing import Any

from denis_unified_v1.metagraph.observer import load_metrics_redis


def load_patterns_redis(redis_url: str | None = None) -> dict[str, Any] | None:
    url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        raw = client.get("metagraph:patterns:latest")
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def persist_patterns_redis(payload: dict[str, Any], ttl_seconds: int = 3600) -> dict[str, Any]:
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        raw = json.dumps(payload, sort_keys=True)
        client.setex("metagraph:patterns:latest", ttl_seconds, raw)
        return {"status": "ok", "redis_url": url, "ttl_seconds": ttl_seconds}
    except Exception as exc:
        return {"status": "error", "redis_url": url, "error": str(exc)}


def build_router():
    """Build a read-only FastAPI router if fastapi is available."""
    try:
        from fastapi import APIRouter
    except Exception:
        return None

    router = APIRouter(prefix="/metagraph", tags=["metagraph"])

    @router.get("/metrics")
    def get_metrics() -> dict[str, Any]:
        payload = load_metrics_redis()
        return payload or {"status": "empty"}

    @router.get("/patterns")
    def get_patterns() -> dict[str, Any]:
        payload = load_patterns_redis()
        return payload or {"status": "empty"}

    return router

