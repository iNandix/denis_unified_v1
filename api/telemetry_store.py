"""Minimal in-memory telemetry store (fail-open).

Goals:
- Support `/telemetry` without external dependencies.
- Avoid logging or persisting raw prompts (only hashes + trace/request ids).
- Keep stable JSON output shapes.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import Counter, deque
from datetime import datetime, timezone
import time
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    raw = (text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


class TelemetryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_utc = _utc_now()
        self.last_request_utc = ""
        self.requests_total = 0
        self.requests_by_path: Counter[str] = Counter()
        self.requests_by_status: Counter[str] = Counter()
        self.latency_ms_last: dict[str, int] = {}

        self.chat_total = 0
        self.chat_blocked_hop_total = 0
        self.chat_decisions: deque[dict[str, Any]] = deque(maxlen=50)

        # Async/materializer visibility (P0)
        self.worker_seen = False
        self.last_materialize_utc = ""
        self.blocked_mutations_count = 0
        self.queue_depth: int | None = None

    def record_request(self, *, path: str, status_code: int, latency_ms: int) -> None:
        with self._lock:
            self.last_request_utc = _utc_now()
            self.requests_total += 1
            self.requests_by_path[str(path or "")] += 1
            self.requests_by_status[str(int(status_code))] += 1
            self.latency_ms_last[str(path or "")] = int(latency_ms)

    def record_chat_decision(self, decision: dict[str, Any]) -> None:
        with self._lock:
            self.chat_total += 1
            if decision.get("blocked") is True:
                self.chat_blocked_hop_total += 1
            d = dict(decision or {})
            d.setdefault("ts_utc", _utc_now())
            self.chat_decisions.appendleft(d)

    def record_materialize(self, *, ok: bool, mutation_blocked: bool = False) -> None:
        with self._lock:
            self.last_materialize_utc = _utc_now()
            if mutation_blocked:
                self.blocked_mutations_count += 1

    def set_worker_seen(self, seen: bool) -> None:
        with self._lock:
            self.worker_seen = bool(seen)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            async_enabled = (os.getenv("ASYNC_ENABLED") or "").strip().lower() in {
                "1",
                "true",
                "yes",
            }

            # P1-ish stale semantics:
            # - If async is enabled and we have never seen a worker complete work => stale.
            # - If last materialize is old => stale.
            stale = False
            if async_enabled:
                stale = not bool(self.worker_seen)
                if self.last_materialize_utc:
                    # Best-effort parse (keep fail-open).
                    try:
                        ts = datetime.fromisoformat(self.last_materialize_utc.replace("Z", "+00:00"))
                        age_s = max(0.0, time.time() - ts.timestamp())
                        if age_s > float(os.getenv("DENIS_ASYNC_STALE_AFTER_S", "60")):
                            stale = True
                    except Exception:
                        stale = True

            queue_depth = self.queue_depth
            return {
                "timestamp": _utc_now(),
                "started_utc": self.started_utc,
                "requests": {
                    "total": int(self.requests_total),
                    "by_path": dict(self.requests_by_path),
                    "by_status": dict(self.requests_by_status),
                    "last_request_utc": self.last_request_utc,
                    "latency_ms_last": dict(self.latency_ms_last),
                },
                "chat": {
                    "total": int(self.chat_total),
                    "blocked_hop_total": int(self.chat_blocked_hop_total),
                    "last_decisions": list(self.chat_decisions),
                },
                "async": {
                    "async_enabled": bool(async_enabled),
                    "worker_seen": bool(self.worker_seen),
                    "materializer_stale": bool(stale),
                    "last_materialize_ts": self.last_materialize_utc,
                    "blocked_mutations_count": int(self.blocked_mutations_count),
                    "queue_depth": queue_depth,
                },
            }

    def to_prometheus(self) -> str:
        snap = self.snapshot()
        lines: list[str] = []

        lines.append("# HELP denis_requests_total Total requests")
        lines.append("# TYPE denis_requests_total counter")
        lines.append(f"denis_requests_total {snap['requests']['total']}")

        lines.append("# HELP denis_chat_total Total chat completions (including blocked)")
        lines.append("# TYPE denis_chat_total counter")
        lines.append(f"denis_chat_total {snap['chat']['total']}")

        lines.append("# HELP denis_chat_blocked_hop_total Total chat blocked by X-Denis-Hop")
        lines.append("# TYPE denis_chat_blocked_hop_total counter")
        lines.append(f"denis_chat_blocked_hop_total {snap['chat']['blocked_hop_total']}")

        for path, count in (snap["requests"]["by_path"] or {}).items():
            safe_path = str(path).replace('"', "_")
            lines.append("# HELP denis_requests_by_path Requests by path")
            lines.append("# TYPE denis_requests_by_path counter")
            lines.append(f'denis_requests_by_path{{path="{safe_path}"}} {int(count)}')

        return "\n".join(lines) + "\n"


_STORE: TelemetryStore | None = None


def get_telemetry_store() -> TelemetryStore:
    global _STORE
    if _STORE is None:
        _STORE = TelemetryStore()
    return _STORE
