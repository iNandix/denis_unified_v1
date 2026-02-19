"""
WindowManager - Control de cuotas por provider/model.

Política: ventana empieza en primer uso (starts_on_first_use).
Mantiene contadores y expira ventanas старше window_duration.
"""

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import logging

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SECONDS = int(os.getenv("DENIS_WINDOW_SECONDS", "3600"))
DEFAULT_MAX_CALLS = int(os.getenv("DENIS_MAX_CALLS_PER_WINDOW", "1000"))


@dataclass
class ProviderQuota:
    """Cuota para un provider/model específico."""

    provider: str
    model: str
    calls: int = 0
    window_start: Optional[float] = None
    max_calls: int = DEFAULT_MAX_CALLS
    window_seconds: int = DEFAULT_WINDOW_SECONDS


class WindowManager:
    """
    Window-based quota manager.

    Thread-safe, starts window on first use.
    """

    def __init__(
        self,
        max_calls_per_window: int = DEFAULT_MAX_CALLS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ):
        self._quotas: dict[str, ProviderQuota] = {}
        self._lock = threading.RLock()
        self._max_calls = max_calls_per_window
        self._window_seconds = window_seconds

    def _make_key(self, provider: str, model: str) -> str:
        return f"{provider}:{model}"

    def _get_or_create_quota(self, provider: str, model: str) -> ProviderQuota:
        """Get or create quota for provider/model."""
        key = self._make_key(provider, model)
        with self._lock:
            if key not in self._quotas:
                self._quotas[key] = ProviderQuota(
                    provider=provider,
                    model=model,
                    max_calls=self._max_calls,
                    window_seconds=self._window_seconds,
                )
            return self._quotas[key]

    def _is_window_expired(self, quota: ProviderQuota) -> bool:
        """Check if the window has expired."""
        if quota.window_start is None:
            return True
        return (time.time() - quota.window_start) > quota.window_seconds

    def can_use(self, provider: str, model: str) -> bool:
        """
        Check if provider/model can be used within quota.

        Returns True if under limit, False if quota exceeded.
        """
        quota = self._get_or_create_quota(provider, model)

        # Start window on first use
        if quota.window_start is None:
            return True

        # Check if window expired - reset if so
        if self._is_window_expired(quota):
            quota.calls = 0
            quota.window_start = None
            return True

        # Check limit
        return quota.calls < quota.max_calls

    def register_use(self, provider: str, model: str) -> bool:
        """
        Register a use of provider/model.

        Returns True if registered successfully, False if quota exceeded.
        """
        quota = self._get_or_create_quota(provider, model)

        with self._lock:
            # Start window on first use
            if quota.window_start is None:
                quota.window_start = time.time()
                quota.calls = 1
                logger.debug(f"Window started for {provider}/{model}")
                return True

            # Check if window expired
            if self._is_window_expired(quota):
                quota.calls = 1
                quota.window_start = time.time()
                logger.debug(f"Window reset for {provider}/{model}")
                return True

            # Check and increment
            if quota.calls >= quota.max_calls:
                logger.warning(
                    f"Quota exceeded for {provider}/{model}: {quota.calls}/{quota.max_calls}"
                )
                return False

            quota.calls += 1
            logger.debug(
                f"Registered use for {provider}/{model}: {quota.calls}/{quota.max_calls}"
            )
            return True

    def get_stats(self, provider: str, model: str) -> dict:
        """Get current stats for provider/model."""
        quota = self._get_or_create_quota(provider, model)
        with self._lock:
            return {
                "provider": provider,
                "model": model,
                "calls": quota.calls,
                "max_calls": quota.max_calls,
                "window_start": quota.window_start,
                "window_seconds": quota.window_seconds,
                "available": self.can_use(provider, model),
            }

    def reset(self, provider: Optional[str] = None, model: Optional[str] = None):
        """Reset quota for specific provider/model or all."""
        with self._lock:
            if provider is None and model is None:
                self._quotas.clear()
                logger.info("All quotas reset")
            elif provider is not None and model is not None:
                key = self._make_key(provider, model)
                if key in self._quotas:
                    del self._quotas[key]
                    logger.info(f"Quota reset for {provider}/{model}")


# Global instance
_window_manager: Optional[WindowManager] = None


def get_window_manager() -> WindowManager:
    """Get global WindowManager instance."""
    global _window_manager
    if _window_manager is None:
        _window_manager = WindowManager()
    return _window_manager
