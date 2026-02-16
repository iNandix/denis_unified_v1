"""Celery tasks for Denis unified workers.

Each task is idempotent by request_id (Redis SET NX, TTL 300s).
"""

from __future__ import annotations

import logging
import os
import time

from celery import Celery

logger = logging.getLogger(__name__)

app = Celery("denis")
app.config_from_object("denis_unified_v1.infra.celeryconfig")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
IDEMPOTENCY_TTL = 300  # 5 minutes


def _idempotency_check(task_key: str) -> bool:
    """Check and set idempotency key. Returns True if already processed."""
    try:
        import redis
        r = redis.from_url(REDIS_URL)
        # SET NX returns True if key was set (new), None if exists
        was_set = r.set(f"idem:{task_key}", "1", nx=True, ex=IDEMPOTENCY_TTL)
        return was_set is None  # True = already exists = skip
    except Exception:
        return False  # fail-open: process anyway


@app.task(bind=True, max_retries=3, default_retry_delay=2)
def synthesize_tts(self, request_id: str, text: str, voice: str = None):
    """TTS synthesis task (runs on nodo1, calls nodo2)."""
    idem_key = f"tts:{request_id}"
    if _idempotency_check(idem_key):
        logger.info(f"TTS already processed: {request_id}")
        return {"status": "deduplicated", "request_id": request_id}

    import asyncio
    from denis_unified_v1.delivery.piper_stream import PiperStreamProvider

    provider = PiperStreamProvider(
        base_url=os.getenv("PIPER_BASE_URL", "http://10.10.10.2:8005"),
    )

    async def _run():
        chunks = []
        async for chunk in provider.synthesize_stream(
            text=text, request_id=request_id
        ):
            chunks.append(chunk)
        return chunks

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
        return {
            "status": "ok",
            "request_id": request_id,
            "chunks": len(result),
        }
    except Exception as exc:
        logger.error(f"TTS task error: {exc}")
        raise self.retry(exc=exc)
    finally:
        loop.close()


@app.task(bind=True, max_retries=2, default_retry_delay=1)
def project_to_graph(self, request_id: str, event_type: str, data: dict):
    """Project event to Neo4j graph."""
    idem_key = f"graph:{request_id}:{event_type}"
    if _idempotency_check(idem_key):
        return {"status": "deduplicated"}

    try:
        from denis_unified_v1.delivery.graph_projection import get_voice_projection
        projection = get_voice_projection()

        if event_type == "request":
            projection.project_request(
                request_id=request_id,
                voice_enabled=data.get("voice_enabled", False),
                user_id=data.get("user_id", "default"),
            )
        elif event_type == "outcome":
            projection.project_outcome(
                request_id=request_id,
                metrics=data,
            )
        elif event_type == "tts_step":
            projection.project_tts_step(
                request_id=request_id,
                segment_id=data.get("segment_id", ""),
                text=data.get("text", ""),
                ttfc_ms=data.get("ttfc_ms", 0),
                bytes_sent=data.get("bytes_sent", 0),
                cancelled=data.get("cancelled", False),
            )

        return {"status": "ok", "event_type": event_type}
    except Exception as exc:
        logger.error(f"Graph projection error: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=2, default_retry_delay=1)
def play_ha_media(self, request_id: str, pcm_b64: str, segment_id: str = ""):
    """Play audio segment on Home Assistant media_player."""
    idem_key = f"ha:{request_id}:{segment_id}"
    if _idempotency_check(idem_key):
        return {"status": "deduplicated"}

    import asyncio
    import base64

    async def _run():
        from denis_unified_v1.delivery.hass_bridge import get_hass_bridge
        bridge = get_hass_bridge()
        if not bridge.enabled:
            return {"status": "disabled"}

        pcm_bytes = base64.b64decode(pcm_b64)
        ok = await bridge.play_segment(pcm_bytes, request_id, segment_id)
        return {"status": "ok" if ok else "failed"}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()


@app.task
def execute_tool_ro(request_id: str, tool_name: str, params: dict):
    """Execute read-only tool."""
    idem_key = f"tool_ro:{request_id}:{tool_name}"
    if _idempotency_check(idem_key):
        return {"status": "deduplicated"}

    # Placeholder: wire to actual tool executor
    logger.info(f"Tool RO: {tool_name} for {request_id}")
    return {"status": "ok", "tool": tool_name}


@app.task
def execute_tool_mut(request_id: str, tool_name: str, params: dict):
    """Execute mutating tool (requires high confidence)."""
    idem_key = f"tool_mut:{request_id}:{tool_name}"
    if _idempotency_check(idem_key):
        return {"status": "deduplicated"}

    logger.info(f"Tool MUT: {tool_name} for {request_id}")
    return {"status": "ok", "tool": tool_name}


@app.task
def flush_deferred_graph():
    """Periodic task: flush deferred graph events."""
    try:
        from denis_unified_v1.memory.graph_writer import get_graph_writer
        writer = get_graph_writer()
        flushed = writer.flush_deferred_events()
        return {"status": "ok", "flushed": flushed}
    except Exception as e:
        logger.error(f"Flush deferred error: {e}")
        return {"status": "error", "error": str(e)}
