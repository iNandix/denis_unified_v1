from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AsyncConfig:
    enabled: bool
    broker_url: str
    result_backend: str


def get_async_config() -> AsyncConfig:
    enabled = (os.getenv("ASYNC_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
    broker_url = (os.getenv("ASYNC_REDIS_URL") or os.getenv("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()
    backend = (os.getenv("ASYNC_RESULT_BACKEND") or broker_url).strip()
    return AsyncConfig(enabled=enabled, broker_url=broker_url, result_backend=backend)

