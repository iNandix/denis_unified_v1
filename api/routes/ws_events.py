"""WebSocket endpoint for Event Bus v1 (Chat-as-IDE)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.event_bus import get_event_hub, get_event_store

router = APIRouter()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.websocket("/v1/ws")
async def ws_events(websocket: WebSocket, conversation_id: str | None = None):
    # No auth (LAN/dev). Fail-open: if anything breaks, close socket without impacting HTTP endpoints.
    await websocket.accept()
    await websocket.send_json(
        {"type": "hello", "server_time": _utc_now_iso(), "schema_version": "1.0"}
    )

    subscribed = False
    conn = None
    conv_id = (conversation_id or "").strip() or "default"
    try:
        while True:
            msg = await websocket.receive_json()
            mtype = (msg or {}).get("type")
            if mtype == "pong":
                continue
            if mtype != "subscribe":
                continue

            conv_id = (msg.get("conversation_id") or conv_id or "default").strip() or "default"
            try:
                last_event_id = int(msg.get("last_event_id") or 0)
            except Exception:
                last_event_id = 0

            # Register for live events
            conn = get_event_hub().register(conversation_id=conv_id, ws=websocket)
            subscribed = True

            # Replay persisted events
            try:
                events = get_event_store().query_after(
                    conversation_id=conv_id, after_event_id=last_event_id
                )
                for ev in events:
                    try:
                        conn.queue.put_nowait(ev)
                    except Exception:
                        break
            except Exception:
                pass

            # Main loop: drain outgoing queue while still accepting inbound messages.
            next_ping = time.monotonic() + 20.0
            while True:
                timeout = max(0.0, next_ping - time.monotonic())
                recv_task = asyncio.create_task(websocket.receive_json())
                send_task = asyncio.create_task(conn.queue.get())
                done, pending = await asyncio.wait(
                    {recv_task, send_task},
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()

                if not done:
                    # Heartbeat tick
                    next_ping = time.monotonic() + 20.0
                    try:
                        await asyncio.wait_for(
                            websocket.send_json({"type": "ping", "ts": _utc_now_iso()}),
                            timeout=0.8,
                        )
                    except Exception:
                        return
                    continue

                if send_task in done:
                    ev = send_task.result()
                    try:
                        await asyncio.wait_for(websocket.send_json(ev), timeout=0.8)
                    except Exception:
                        return
                    continue

                if recv_task in done:
                    incoming = recv_task.result()
                    itype = (incoming or {}).get("type")
                    if itype == "pong":
                        continue
                    if itype == "subscribe":
                        # Re-subscribe switches conversation or resets replay.
                        break
    except WebSocketDisconnect:
        return
    except Exception:
        return
    finally:
        if subscribed and conn is not None:
            try:
                get_event_hub().unregister(conn)
            except Exception:
                pass
