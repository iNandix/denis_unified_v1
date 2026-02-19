"""WS21-G Client: OpenCode Middleware -> Compiler Service.

This module provides the client-side integration for OpenCode to call the
Compiler Service (WS21-G). It replaces the simple makina_filter with
LLM-powered compilation when available.

Configuration:
- OPENCODE_COMPILER_URL: Compiler service URL (default http://127.0.0.1:19000)
- OPENCODE_MAKINA_ONLY: If "1", always use makina_prompt from compiler
- OPENCODE_COMPILER_FALLBACK: "local_v2" (default) for fallback
- OPENCODE_COMPILER_DEBUG: "1" to enable debug logging
- OPENCODE_COMPILER_TIMEOUT_MS: Timeout for compiler calls (default 5000)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

VERSION = "1.1.0"

COMPILER_URL = os.getenv("OPENCODE_COMPILER_URL", "http://127.0.0.1:19000")
MAKINA_ONLY = os.getenv("OPENCODE_MAKINA_ONLY", "1") == "1"
COMPILER_DEBUG = os.getenv("OPENCODE_COMPILER_DEBUG", "0") == "1"
COMPILER_TIMEOUT_MS = int(os.getenv("OPENCODE_COMPILER_TIMEOUT_MS", "5000"))
FALLBACK_MODE = os.getenv("OPENCODE_COMPILER_FALLBACK", "local_v2")


@dataclass
class CompilerClientResult:
    """Result from compiler client."""

    makina_prompt: str
    router: dict[str, Any]
    trace_hash: str
    retrieval_refs: dict[str, Any]
    metadata: dict[str, Any]
    used_remote: bool = False


def _generate_ids() -> tuple[str, str, str]:
    """Generate conversation_id, turn_id, correlation_id."""
    now = datetime.now(timezone.utc).isoformat()
    conv_id = f"opencode_{now.replace(':', '-')}"
    turn_id = str(uuid.uuid4())[:8]
    corr_id = str(uuid.uuid4())[:12]
    return conv_id, turn_id, corr_id


def _redact_for_log(text: str, max_len: int = 100) -> str:
    """Redact text for logging."""
    raw = text or ""
    try:
        from denis_unified_v1.indexing.redaction_gate import redact_for_indexing

        safe, _info = redact_for_indexing(raw)
    except Exception:
        safe = raw
    if len(safe) > max_len:
        return safe[: max(0, int(max_len) - 3)] + "..."
    return safe


async def call_compiler(
    input_text: str,
    conversation_id: str = "",
    turn_id: str = "",
    correlation_id: str = "",
    anti_loop: bool = False,
) -> CompilerClientResult:
    """
    Call the Compiler Service to compile natural language to Makina Prompt.

    Args:
        input_text: Natural language input from user
        conversation_id: Conversation ID (auto-generated if empty)
        turn_id: Turn ID (auto-generated if empty)
        correlation_id: Correlation ID (auto-generated if empty)
        anti_loop: If True, force fallback to local compiler

    Returns:
        CompilerClientResult with makina_prompt and metadata

    Raises:
        RuntimeError: If compiler is unavailable and fallback fails
    """
    if not conversation_id:
        conversation_id, turn_id, correlation_id = _generate_ids()

    if COMPILER_DEBUG:
        logger.info(f"[compiler_client] Calling compiler: {_redact_for_log(input_text)}")

    headers = {
        "Content-Type": "application/json",
    }

    if anti_loop:
        headers["X-Denis-Hop"] = "1"

    payload = {
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "correlation_id": correlation_id,
        "input_text": input_text,
        "mode": "makina_only",
        "context_policy": {
            "graph": True,
            "vectorstore": True,
            "max_chunks": 12,
            "max_graph_entities": 40,
        },
        "capabilities": [
            "control_room",
            "rag",
            "pro_search",
            "scrape",
            "graph",
            "voice",
            "frontend",
        ],
        "flags": {
            "ws_first": True,
            "graph_ssot": True,
        },
    }

    timeout = httpx.Timeout(COMPILER_TIMEOUT_MS / 1000.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{COMPILER_URL}/compiler/compile",
                json=payload,
                headers=headers,
            )

            if response.status_code == 503:
                raise RuntimeError("compiler_disabled")

            response.raise_for_status()
            data = response.json()

            if COMPILER_DEBUG:
                logger.info(f"[compiler_client] Result: pick={data.get('router', {}).get('pick')}")

            return CompilerClientResult(
                makina_prompt=data.get("makina_prompt", ""),
                router=data.get("router", {}),
                retrieval=data.get("retrieval", {}),
                prompt_hash_sha256=data.get("prompt_hash_sha256", ""),
                metadata=data.get("metadata", {}),
                used_remote=True,
            )

    except httpx.TimeoutException as e:
        logger.warning(f"[compiler_client] Timeout calling compiler: {e}")
        raise RuntimeError(f"compiler_timeout: {e}") from e
    except httpx.HTTPStatusError as e:
        logger.warning(f"[compiler_client] HTTP error: {e}")
        raise RuntimeError(f"compiler_http_error: {e}") from e
    except Exception as e:
        logger.warning(f"[compiler_client] Error: {e}")
        raise RuntimeError(f"compiler_error: {e}") from e


async def compile_with_fallback(
    input_text: str,
    conversation_id: str = "",
    turn_id: str = "",
    correlation_id: str = "",
    anti_loop: bool = False,
) -> CompilerClientResult:
    """
    Compile with fallback to local_v2 (makina_filter).

    This is the main entry point that handles:
    1. Try remote compiler (if available and not anti_loop)
    2. Fall back to local makina_filter on error
    3. Return makina_prompt ready for runtime
    """
    if COMPILER_DEBUG:
        logger.info(
            f"[compiler_client] compile_with_fallback: {_redact_for_log(input_text)}, anti_loop={anti_loop}"
        )

    if anti_loop:
        logger.info("[compiler_client] Anti-loop detected, using local fallback")
        return await _use_local_fallback(input_text)

    try:
        return await call_compiler(
            input_text,
            conversation_id or "",
            turn_id or "",
            correlation_id or "",
            anti_loop,
        )
    except RuntimeError as e:
        logger.warning(f"[compiler_client] Remote compiler failed: {e}, using local fallback")
        return await _use_local_fallback(input_text)


async def _use_local_fallback(input_text: str) -> CompilerClientResult:
    """Use local compiler fallback (Makina minimal, no OpenAI)."""
    from denis_unified_v1.inference.compiler_service import CompilerInput, compile

    conv_id, turn_id, corr_id = _generate_ids()
    out = await compile(
        CompilerInput(
            conversation_id=conv_id,
            turn_id=turn_id,
            correlation_id=corr_id,
            input_text=str(input_text or ""),
        ),
        anti_loop=True,
    )

    return CompilerClientResult(
        makina_prompt=str(out.makina_prompt or ""),
        router=dict(out.router or {}),
        trace_hash=str(out.trace_hash or ""),
        retrieval_refs=dict(out.retrieval_refs or {}),
        metadata=dict(out.metadata or {}),
        used_remote=False,
    )


def compile_with_fallback_sync(
    input_text: str,
    conversation_id: str = "",
    anti_loop: bool = False,
) -> CompilerClientResult:
    """Synchronous wrapper for compile_with_fallback."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        fut = asyncio.run_coroutine_threadsafe(
            compile_with_fallback(input_text, conversation_id=conversation_id, anti_loop=anti_loop),
            loop,
        )
        return fut.result(timeout=COMPILER_TIMEOUT_MS / 1000.0 + 5)

    if loop:
        return loop.run_until_complete(
            compile_with_fallback(input_text, conversation_id=conversation_id, anti_loop=anti_loop)
        )
    return asyncio.run(
        compile_with_fallback(input_text, conversation_id=conversation_id, anti_loop=anti_loop)
    )


def get_compiler_client_config() -> dict[str, Any]:
    """Get current compiler client configuration."""
    return {
        "version": VERSION,
        "compiler_url": COMPILER_URL,
        "makina_only": MAKINA_ONLY,
        "debug": COMPILER_DEBUG,
        "timeout_ms": COMPILER_TIMEOUT_MS,
        "fallback_mode": FALLBACK_MODE,
    }
