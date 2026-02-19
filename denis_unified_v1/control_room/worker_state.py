"""In-memory worker state for Ops visibility (fail-open).

This is intentionally not persisted. Graph remains the SSoT for Task/Run/Approval state.
Telemetry/health endpoints can read this best-effort snapshot.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ControlRoomWorkerState:
    heartbeat_ts: str = ""
    last_tick_ts: str = ""
    last_error_ts: str = ""
    queue_depth: int | None = None
    running_count: int | None = None


_LOCK = threading.Lock()
_STATE = ControlRoomWorkerState()


def update_worker_state(
    *,
    heartbeat: bool = True,
    last_tick: bool = True,
    error: bool = False,
    queue_depth: int | None = None,
    running_count: int | None = None,
) -> None:
    ts = _utc_now_iso()
    with _LOCK:
        if heartbeat:
            _STATE.heartbeat_ts = ts
        if last_tick:
            _STATE.last_tick_ts = ts
        if error:
            _STATE.last_error_ts = ts
        if queue_depth is not None:
            _STATE.queue_depth = int(queue_depth)
        if running_count is not None:
            _STATE.running_count = int(running_count)


def snapshot_worker_state() -> dict:
    with _LOCK:
        return {
            "heartbeat_ts": _STATE.heartbeat_ts,
            "last_tick_ts": _STATE.last_tick_ts,
            "last_error_ts": _STATE.last_error_ts,
            "queue_depth": _STATE.queue_depth,
            "running_count": _STATE.running_count,
        }

