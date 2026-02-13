"""Read-only query interface for incremental Denis API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from metagraph.dashboard import load_patterns_redis
from metagraph.observer import load_metrics_redis


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_query_router() -> APIRouter:
    router = APIRouter(prefix="/v1/query", tags=["query"])

    @router.get("/metagraph/metrics")
    def metagraph_metrics() -> dict[str, Any]:
        data = load_metrics_redis()
        return data or {"status": "empty", "timestamp_utc": _utc_now()}

    @router.get("/metagraph/patterns")
    def metagraph_patterns() -> dict[str, Any]:
        data = load_patterns_redis()
        return data or {"status": "empty", "timestamp_utc": _utc_now()}

    return router

