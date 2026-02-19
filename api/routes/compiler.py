"""Compiler API Route - WS21-G.

POST /compiler/compile
POST /compiler/compile/stream (streaming)
GET /compiler/status

Implementation notes:
- HTTP calls the internal compiler router (no separate worker yet).
- Router emits compiler.* and retrieval.* events to WS bus for timeline/materializer.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.persona.correlation import persona_request_context
from denis_unified_v1.inference.compiler_service import VERSION
from denis_unified_v1.compiler.router import compile_via_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compiler", tags=["compiler"])

COMPILER_ENABLED = os.getenv("OPENCODE_COMPILER_ENABLED", "1") == "1"
COMPILER_DEBUG = os.getenv("OPENCODE_COMPILER_DEBUG", "0") == "1"


@router.get("/status")
async def compiler_status() -> JSONResponse:
    """Get compiler service status."""
    return JSONResponse(
        {
            "status": "ok" if COMPILER_ENABLED else "disabled",
            "version": VERSION,
            "debug": COMPILER_DEBUG,
            "model": os.getenv("OPENCODE_COMPILER_MODEL", "gpt-4o-mini"),
        }
    )


@router.post("/compile")
async def compiler_compile(
    request: Request,
    body: dict[str, Any],
    x_denis_hop: str | None = Header(None, alias="X-Denis-Hop"),
) -> JSONResponse:
    """
    Compile natural language to Makina Prompt.

    Body:
    {
        "conversation_id": string,
        "turn_id": string,
        "correlation_id": string,
        "input_text": string,
        "mode": "makina_only",
        "context_policy": {...},
        "capabilities": [...],
        "flags": {...}
    }
    """
    if not COMPILER_ENABLED:
        return JSONResponse(
            {"error": "compiler_disabled"},
            status_code=503,
        )

    conversation_id = str(body.get("conversation_id") or "").strip() or "default"
    turn_id = str(body.get("turn_id") or "").strip()
    trace_id = str(body.get("correlation_id") or "").strip() or turn_id
    input_text = str(body.get("input_text") or "").strip()
    if not input_text:
        return JSONResponse({"error": "invalid_input", "message": "input_text required"}, status_code=400)

    # Anti-loop: any hop header forces hop_count >= 2 in the router.
    hop_count = 2 if bool(x_denis_hop) else int(body.get("hop_count") or 0)
    if hop_count < 0:
        hop_count = 0

    try:
        with persona_request_context(
            conversation_id=conversation_id,
            trace_id=trace_id,
            correlation_id=trace_id,
            turn_id=turn_id or trace_id,
        ):
            out = await compile_via_router(
                conversation_id=conversation_id,
                trace_id=trace_id,
                run_id=str(body.get("run_id") or ""),
                actor_id=str(body.get("actor_id") or "") or None,
                text=input_text,
                workspace=body.get("workspace") if isinstance(body.get("workspace"), dict) else None,
                consciousness=body.get("consciousness") if isinstance(body.get("consciousness"), dict) else None,
                hop_count=hop_count,
                policy=body.get("context_policy") if isinstance(body.get("context_policy"), dict) else None,
            )

        response = {
            "makina_prompt": out.get("makina_prompt", ""),
            "router": out.get("router", {}),
            "retrieval_refs": out.get("retrieval_refs", {}),
            "metadata": out.get("metadata", {}),
        }

        if COMPILER_DEBUG:
            logger.info(
                "Compiler output meta: pick=%s confidence=%s makina_len=%s degraded=%s",
                str((response.get("router") or {}).get("pick")),
                str((response.get("router") or {}).get("confidence")),
                str(len(response.get("makina_prompt") or "")),
                str(bool((response.get("metadata") or {}).get("degraded"))),
            )

        return JSONResponse(response)

    except Exception as e:
        logger.error(f"Compilation failed: {e}")
        return JSONResponse(
            {"error": "compilation_failed", "message": str(e)},
            status_code=500,
        )


@router.post("/compile/stream")
async def compiler_compile_stream(
    request: Request,
    body: dict[str, Any],
    x_denis_hop: str | None = Header(None, alias="X-Denis-Hop"),
) -> StreamingResponse:
    """
    Compile natural language to Makina Prompt (streaming).

    Emits SSE with:
    - retrieval.start, retrieval.result
    - compiler.start, compiler.chunk, compiler.result
    """
    if not COMPILER_ENABLED:
        return StreamingResponse(
            iter([f"data: error: compiler_disabled\n\n"]),
            media_type="text/event-stream",
        )

    async def event_generator():
        try:
            conversation_id = str(body.get("conversation_id") or "").strip() or "default"
            turn_id = str(body.get("turn_id") or "").strip()
            trace_id = str(body.get("correlation_id") or "").strip() or turn_id
            input_text = str(body.get("input_text") or "").strip()
            if not input_text:
                raise ValueError("input_text required")
        except Exception as e:
            yield f"data: error: invalid_input: {str(e)}\n\n"
            return

        hop_count = 2 if bool(x_denis_hop) else int(body.get("hop_count") or 0)
        if hop_count < 0:
            hop_count = 0

        yield f'data: {{"event": "compiler.start", "input_len": {len(input_text)}}}\n\n'

        with persona_request_context(
            conversation_id=conversation_id,
            trace_id=trace_id,
            correlation_id=trace_id,
            turn_id=turn_id or trace_id,
        ):
            out = await compile_via_router(
                conversation_id=conversation_id,
                trace_id=trace_id,
                run_id=str(body.get("run_id") or ""),
                actor_id=str(body.get("actor_id") or "") or None,
                text=input_text,
                workspace=body.get("workspace") if isinstance(body.get("workspace"), dict) else None,
                consciousness=body.get("consciousness") if isinstance(body.get("consciousness"), dict) else None,
                hop_count=hop_count,
                policy=body.get("context_policy") if isinstance(body.get("context_policy"), dict) else None,
            )

        response = {
            "makina_prompt": out.get("makina_prompt", ""),
            "router": out.get("router", {}),
            "retrieval_refs": out.get("retrieval_refs", {}),
            "metadata": out.get("metadata", {}),
        }

        yield f'data: {{"event": "compiler.result", "pick": "{(response.get("router") or {}).get("pick")}", "confidence": {(response.get("router") or {}).get("confidence", 0)}}}\n\n'
        yield f"data: {json.dumps(response)}\n\n"
        yield "data: [DONE]\n\n"

    import json

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.post("/fallback")
async def compiler_fallback(
    body: dict[str, Any],
) -> JSONResponse:
    """Force fallback compilation (local_v2)."""
    conversation_id = str(body.get("conversation_id") or "").strip() or "default"
    turn_id = str(body.get("turn_id") or "").strip()
    trace_id = str(body.get("correlation_id") or "").strip() or turn_id
    input_text = str(body.get("input_text") or "").strip()
    if not input_text:
        return JSONResponse({"error": "invalid_input", "message": "input_text required"}, status_code=400)

    with persona_request_context(
        conversation_id=conversation_id,
        trace_id=trace_id,
        correlation_id=trace_id,
        turn_id=turn_id or trace_id,
    ):
        out = await compile_via_router(
            conversation_id=conversation_id,
            trace_id=trace_id,
            run_id=str(body.get("run_id") or ""),
            actor_id=str(body.get("actor_id") or "") or None,
            text=input_text,
            workspace=body.get("workspace") if isinstance(body.get("workspace"), dict) else None,
            consciousness=body.get("consciousness") if isinstance(body.get("consciousness"), dict) else None,
            hop_count=2,  # force anti-loop/fallback path
            policy=body.get("context_policy") if isinstance(body.get("context_policy"), dict) else None,
        )

    return JSONResponse(
        {
            "makina_prompt": out.get("makina_prompt", ""),
            "router": out.get("router", {}),
            "retrieval_refs": out.get("retrieval_refs", {}),
            "metadata": out.get("metadata", {}),
        }
    )


def get_compiler_router() -> APIRouter:
    """Return the compiler router."""
    return router
