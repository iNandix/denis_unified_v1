"""WebSocket handler for phase-6 event streaming."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_ws_router() -> APIRouter:
    router = APIRouter(tags=["events"])

    @router.websocket("/v1/events")
    async def events(websocket: WebSocket):
        await websocket.accept()
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_backend = None
        pubsub = None
        try:
            import redis.asyncio as aioredis

            redis_backend = aioredis.from_url(redis_url, decode_responses=True)
            pubsub = redis_backend.pubsub()
            await pubsub.subscribe("denis:events")
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    await websocket.send_json(
                        {
                            "event": "denis_event",
                            "data": msg.get("data"),
                            "source": "redis",
                            "timestamp_utc": _utc_now(),
                        }
                    )
                else:
                    await websocket.send_json(
                        {
                            "event": "heartbeat",
                            "source": "redis",
                            "timestamp_utc": _utc_now(),
                        }
                    )
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            pass
        except Exception:
            # Fallback heartbeat mode if redis pubsub is unavailable.
            try:
                while True:
                    await websocket.send_json(
                        {
                            "event": "heartbeat",
                            "source": "fallback",
                            "timestamp_utc": _utc_now(),
                        }
                    )
                    await asyncio.sleep(2.0)
            except WebSocketDisconnect:
                pass
        finally:
            try:
                if pubsub is not None:
                    await pubsub.close()
            except Exception:
                pass
            try:
                if redis_backend is not None:
                    await redis_backend.close()
            except Exception:
                pass

    return router

