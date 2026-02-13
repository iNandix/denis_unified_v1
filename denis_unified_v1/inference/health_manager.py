"""Health Manager for engine providers."""

import time
from typing import Dict, Optional


class HealthManager:
    def __init__(self):
        self._cache: Dict[str, tuple[bool, float]] = {}
        self._cache_ttl = 2.0

    def get_cached(self, engine_id: str) -> Optional[bool]:
        if engine_id in self._cache:
            healthy, cached_time = self._cache[engine_id]
            if time.time() - cached_time < self._cache_ttl:
                return healthy
        return None

    def set_cached(self, engine_id: str, healthy: bool):
        self._cache[engine_id] = (healthy, time.time())

    def invalidate(self, engine_id: str):
        if engine_id in self._cache:
            del self._cache[engine_id]

    def invalidate_all(self):
        self._cache.clear()


def get_health_manager() -> HealthManager:
    return HealthManager()
