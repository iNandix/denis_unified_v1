"""WebSocket-first Event Bus v1 (fail-open).

Design:
- Persist events in SQLite (append-only) for replay after reconnect.
- Broadcast live events to subscribed WebSocket connections via in-memory queues.
- Never block `/chat` or other critical endpoints: any failure to persist/broadcast is swallowed.

Security:
- Do not persist raw prompts or secrets; emitters should provide redacted payloads only.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from denis_unified_v1.guardrails.event_payload_policy import sanitize_event_payload

_PERSONA_EMIT_ALLOWED: ContextVar[bool] = ContextVar("denis_persona_emit_allowed", default=False)


@contextmanager
def persona_emitter_context():
    """Allow emitting events to the WS event bus inside this context (WS15)."""
    tok = _PERSONA_EMIT_ALLOWED.set(True)
    try:
        yield
    finally:
        _PERSONA_EMIT_ALLOWED.reset(tok)

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_channel(event_type: str) -> str:
    t = (event_type or "").strip()
    if t.startswith("compiler.") or t.startswith("retrieval."):
        return "compiler"
    if t.startswith("voice."):
        return "voice"
    if t.startswith("control_room."):
        return "control_room"
    if t.startswith("rag."):
        return "rag"
    if t.startswith("tool."):
        return "tool"
    if t.startswith("scrape.") or t.startswith("scraping."):
        return "scrape"
    if t.startswith("neuro.") or t.startswith("persona."):
        return "neuro"
    if t == "chat.message" or t.startswith("plan."):
        return "text"
    if t.startswith("agent."):
        return "ops"
    if t.startswith("ops.") or t in {"error", "graph.mutation", "indexing.upsert", "run.step"}:
        return "ops"
    return "ops"


def _events_db_path() -> str:
    # Workspace-local by default (safe: contains redacted payload only).
    return os.getenv("DENIS_EVENTS_DB_PATH", "./var/denis_events.db")


def _ensure_parent_dir(path: str) -> None:
    try:
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
    except Exception:
        return


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS denis_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          conversation_id TEXT NOT NULL,
          event_id INTEGER NOT NULL,
          ts TEXT NOT NULL,
          trace_id TEXT,
          type TEXT NOT NULL,
          severity TEXT NOT NULL,
          event_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_denis_events_conv_event ON denis_events(conversation_id, event_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_denis_events_conv_id ON denis_events(conversation_id, id)"
    )
    conn.commit()


class EventStore:
    def __init__(self, *, db_path: str) -> None:
        self.db_path = db_path
        _ensure_parent_dir(db_path)
        conn = sqlite3.connect(self.db_path)
        try:
            _init_db(conn)
        finally:
            conn.close()

    def append(self, *, conversation_id: str, event: dict[str, Any], retention: int = 2000) -> dict[str, Any]:
        """Persist `event` and return the persisted JSON with assigned event_id."""
        # event_id monotonic per conversation_id
        conn = sqlite3.connect(self.db_path, timeout=0.2)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "SELECT COALESCE(MAX(event_id), 0) AS mx FROM denis_events WHERE conversation_id = ?",
                (conversation_id,),
            )
            mx = int((cur.fetchone() or [0])[0])
            eid = mx + 1

            ev = dict(event)
            ev["event_id"] = eid
            ev["conversation_id"] = conversation_id

            conn.execute(
                """
                INSERT INTO denis_events (conversation_id, event_id, ts, trace_id, type, severity, event_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    int(eid),
                    str(ev.get("ts") or _utc_now_iso()),
                    ev.get("trace_id"),
                    str(ev.get("type") or ""),
                    str(ev.get("severity") or "info"),
                    json.dumps(ev, ensure_ascii=True),
                ),
            )

            # Retention: keep last N per conversation.
            if retention and retention > 0:
                thr = eid - int(retention)
                if thr > 0:
                    conn.execute(
                        "DELETE FROM denis_events WHERE conversation_id = ? AND event_id <= ?",
                        (conversation_id, int(thr)),
                    )

            conn.commit()
            return ev
        finally:
            conn.close()

    def query_after(self, *, conversation_id: str, after_event_id: int) -> list[dict[str, Any]]:
        conn = sqlite3.connect(self.db_path, timeout=0.2)
        try:
            cur = conn.execute(
                """
                SELECT event_json
                FROM denis_events
                WHERE conversation_id = ? AND event_id > ?
                ORDER BY event_id ASC
                """,
                (conversation_id, int(after_event_id)),
            )
            out: list[dict[str, Any]] = []
            for (raw,) in cur.fetchall():
                try:
                    out.append(json.loads(raw))
                except Exception:
                    continue
            return out
        finally:
            conn.close()


_store_lock = threading.Lock()
_STORE: EventStore | None = None


def get_event_store() -> EventStore:
    global _STORE
    with _store_lock:
        if _STORE is None:
            _STORE = EventStore(db_path=_events_db_path())
        return _STORE


@dataclass
class _Conn:
    ws: WebSocket
    conversation_id: str
    queue: asyncio.Queue[dict[str, Any]]


class EventHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conns_by_conv: dict[str, list[_Conn]] = {}

    def register(self, *, conversation_id: str, ws: WebSocket, max_buffered: int = 200) -> _Conn:
        # Queue is drained by the WS handler (not a background task). This avoids
        # testclient/event-loop edge cases and keeps backpressure deterministic.
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_buffered)
        conn = _Conn(ws=ws, conversation_id=conversation_id, queue=q)
        with self._lock:
            self._conns_by_conv.setdefault(conversation_id, []).append(conn)
        return conn

    def unregister(self, conn: _Conn) -> None:
        with self._lock:
            conns = self._conns_by_conv.get(conn.conversation_id) or []
            self._conns_by_conv[conn.conversation_id] = [c for c in conns if c is not conn]
        # No background tasks to cancel.

    def _snapshot_conns(self, conversation_id: str) -> list[_Conn]:
        with self._lock:
            return list(self._conns_by_conv.get(conversation_id) or [])

    def publish(self, *, conversation_id: str, event: dict[str, Any]) -> None:
        for conn in self._snapshot_conns(conversation_id):
            try:
                conn.queue.put_nowait(event)
            except Exception:
                # Backpressure: queue full. Emit an ephemeral error and drop the new event.
                try:
                    corr = str((event or {}).get("correlation_id") or "backpressure")
                    turn = str((event or {}).get("turn_id") or corr)
                    err = {
                        "type": "error",
                        "schema_version": "1.0",
                        "ts": _utc_now_iso(),
                        "conversation_id": conversation_id,
                        "emitter": "denis_persona",
                        "correlation_id": corr,
                        "turn_id": turn,
                        "channel": "ops",
                        "stored": False,
                        "trace_id": (event or {}).get("trace_id"),
                        "event_id": 0,
                        "severity": "warning",
                        "ui_hint": {"render": "error", "icon": "alert", "collapsible": True},
                        "payload": {
                            "code": "backpressure_drop",
                            "msg": "Dropped event due to slow client",
                            "detail": {"max_buffered": conn.queue.maxsize},
                        },
                    }
                    conn.queue.put_nowait(err)
                except Exception:
                    pass


_HUB = EventHub()


def get_event_hub() -> EventHub:
    return _HUB


def emit_event(
    *,
    conversation_id: str,
    trace_id: str | None,
    type: str,
    severity: str = "info",
    ui_hint: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    emitter: str | None = None,
    correlation_id: str | None = None,
    turn_id: str | None = None,
    channel: str | None = None,
    stored: bool = True,
) -> dict[str, Any]:
    """Persist + publish an event. Fail-open by design."""
    # WS15: Persona is the only allowed emitter. Block direct calls.
    enforce = False
    bypass_mode = "raise"
    try:
        from api.persona.policies import persona_bypass_mode as _persona_bypass_mode
        from api.persona.policies import persona_frontdoor_enforced as _persona_frontdoor_enforced

        enforce = bool(_persona_frontdoor_enforced())
        bypass_mode = str(_persona_bypass_mode() or "raise")
    except Exception:
        enforce = False
        bypass_mode = "raise"

    if enforce and not bool(_PERSONA_EMIT_ALLOWED.get()):
        msg = "Blocked non-persona event emission (call api.persona.event_router.persona_emit)"
        if bypass_mode == "raise":
            raise RuntimeError(msg)
        # prod: log-safe + drop (no raw payload, no secrets)
        try:
            print(
                f"[persona_frontdoor] drop_event type={type} conversation_id={conversation_id or 'default'}"
            )
        except Exception:
            pass
        safe_trace = (trace_id or "").strip()
        try:
            import uuid

            safe_corr = safe_trace or uuid.uuid4().hex
            safe_turn = safe_trace or uuid.uuid4().hex
        except Exception:
            safe_corr = safe_trace or "unknown"
            safe_turn = safe_trace or "unknown"

        return {
            "event_id": 0,
            "ts": _utc_now_iso(),
            "conversation_id": conversation_id or "default",
            "emitter": "denis_persona",
            "correlation_id": safe_corr,
            "turn_id": safe_turn,
            "channel": _infer_channel(type),
            "stored": False,
            "trace_id": trace_id,
            "type": "error",
            "severity": "warning",
            "schema_version": "1.0",
            "ui_hint": {"render": "error", "icon": "alert", "collapsible": True},
            "payload": {"code": "persona_frontdoor_drop", "msg": msg},
        }

    # Fill persona envelope fields from context when available (WS15).
    if not emitter:
        emitter = "denis_persona"

    ctx = None
    try:
        from api.persona.correlation import get_persona_context_if_set

        ctx = get_persona_context_if_set()
    except Exception:
        ctx = None

    if not correlation_id:
        corr = ""
        try:
            corr = str((ctx.correlation_id if ctx else "") or "")
        except Exception:
            corr = ""
        correlation_id = corr.strip() or (trace_id or "").strip() or None

    if not turn_id:
        tid = ""
        try:
            tid = str((ctx.turn_id if ctx else "") or "")
        except Exception:
            tid = ""
        turn_id = tid.strip() or (trace_id or "").strip() or None

    if not correlation_id:
        import uuid

        correlation_id = uuid.uuid4().hex
    if not turn_id:
        import uuid

        turn_id = uuid.uuid4().hex

    # Channel/stored tagging (WS16).
    ch = (channel or "").strip() or _infer_channel(type)
    stored_flag = bool(stored)

    # Guardrails: sanitize payload before persistence/broadcast.
    try:
        sres = sanitize_event_payload(payload)
        payload_safe = sres.payload
        violations = int(sres.violations)
    except Exception:
        payload_safe = payload or {}
        violations = 0
    ev = {
        "event_id": 0,  # assigned by store
        "ts": _utc_now_iso(),
        "conversation_id": conversation_id or "default",
        "emitter": emitter,
        "correlation_id": correlation_id,
        "turn_id": turn_id,
        "channel": ch,
        "stored": stored_flag,
        "trace_id": trace_id,
        "type": type,
        "severity": severity,
        "schema_version": "1.0",
        "ui_hint": ui_hint or {"render": "event", "icon": "dot", "collapsible": True},
        "payload": payload_safe,
    }
    if stored_flag:
        try:
            stored_ev = get_event_store().append(conversation_id=conversation_id, event=ev)
        except Exception:
            stored_ev = ev
    else:
        # WS-only event (not persisted/replayable).
        stored_ev = ev

    try:
        get_event_hub().publish(conversation_id=conversation_id, event=stored_ev)
    except Exception:
        pass

    # Graph SSoT materialization (fail-open). Never blocks event pipeline.
    try:
        from denis_unified_v1.graph.materializers.event_materializer import maybe_materialize_event
        if stored_flag:
            maybe_materialize_event(stored_ev)
    except Exception:
        pass

    # Optional: emit an ops.metric for guardrails violations (non-recursive).
    try:
        if violations > 0 and type != "ops.metric":
            # Metric payload is safe (no denied keys).
            _ = emit_event(
                conversation_id=conversation_id,
                trace_id=trace_id,
                type="ops.metric",
                severity="warning",
                ui_hint={"render": "metric", "icon": "gauge", "collapsible": True},
                channel="ops",
                payload={
                    "name": "guardrails.violation",
                    "value": float(violations),
                    "unit": "count",
                    "labels": {"event_type": type},
                },
            )
    except Exception:
        pass

    return stored_ev


def reset_event_bus_for_tests() -> None:
    """Reset cached store (tests only)."""
    global _STORE
    with _store_lock:
        _STORE = None
