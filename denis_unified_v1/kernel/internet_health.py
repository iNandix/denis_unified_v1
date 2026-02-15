"""Internet health checker with TTL caching and env override for testing.

Environment variables:
  - DENIS_INTERNET_STATUS: OK|DOWN|UNKNOWN (forces status)
  - DENIS_ALLOW_BOOSTERS: 0|1 (whether to allow internet boosters)

Default behavior: UNKNOWN is treated as DOWN (safer for offline).
"""

import os
import time
import socket
import threading
from typing import Literal

InternetStatus = Literal["OK", "DOWN", "UNKNOWN"]


class InternetHealth:
    """Check internet connectivity with TTL caching.

    For testing/CI, set DENIS_INTERNET_STATUS=OK or DENIS_INTERNET_STATUS=DOWN.
    Unknown status is treated as DOWN for safety (offline-first).
    """

    def __init__(self, ttl_s: int = 30):
        self._status: InternetStatus = "UNKNOWN"
        self._last_check_ts: float = 0
        self._ttl = ttl_s
        self._lock = threading.Lock()

    def check(self) -> InternetStatus:
        """Return internet status (cached for ttl_seconds).

        Priority:
        1. DENIS_INTERNET_STATUS env var (OK|DOWN|UNKNOWN)
        2. Actual check (DNS to 8.8.8.8)
        3. Default: UNKNOWN -> treated as DOWN
        """
        # Env override takes priority
        env_status = os.getenv("DENIS_INTERNET_STATUS", "").upper()
        if env_status in ("OK", "DOWN", "UNKNOWN"):
            return InternetStatus(env_status)

        # Use cache if fresh
        now = time.time()
        if now - self._last_check_ts < self._ttl:
            status = self._status if self._status != "UNKNOWN" else "DOWN"
            return InternetStatus(status)

        # Check internet
        with self._lock:
            try:
                socket.gethostbyname("8.8.8.8")
                self._status = "OK"
            except OSError:
                self._status = "DOWN"
            self._last_check_ts = now

        # Treat UNKNOWN as DOWN for safety
        status = self._status if self._status != "UNKNOWN" else "DOWN"
        return InternetStatus(status)

    def is_internet_ok(self) -> bool:
        """Convenience method: True if internet is confirmed OK."""
        return self.check() == "OK"

    def allow_boosters(self) -> bool:
        """Check if boosters should be allowed.

        DENIS_ALLOW_BOOSTERS=0 explicitly disables boosters.
        Default: True if internet is OK.
        """
        env_override = os.getenv("DENIS_ALLOW_BOOSTERS", "").strip()
        if env_override == "0":
            return False
        if env_override == "1":
            return True
        # Default: allow boosters only if internet is OK
        return self.is_internet_ok()

    def invalidate(self) -> None:
        """Clear cache (for testing)."""
        self._status = "UNKNOWN"
        self._last_check_ts = 0


_internet_health: InternetHealth | None = None


def get_internet_health() -> InternetHealth:
    """Get singleton InternetHealth instance."""
    global _internet_health
    if _internet_health is None:
        _internet_health = InternetHealth()
    return _internet_health
