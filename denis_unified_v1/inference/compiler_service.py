"""WS21-G: OpenCode LLM Compiler Service (Event-driven).

This module provides event-driven compilation via the WS event bus.
It publishes compiler.request events and awaits compiler.result.

Architecture:
- Primary: Publish compiler.request -> ChatRoom worker -> compiler.result
- Fallback: local_v2 (makina_filter heuristics) when ChatRoom unavailable
- Anti-loop: X-Denis-Hop header triggers fallback

Output:
- makina_prompt: Machine language ready for runtime
- router: intent_pick + confidence + candidates + retrieval refs
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

VERSION = "1.2.0"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENCODE_COMPILER_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MAX_TOKENS = int(os.getenv("OPENCODE_COMPILER_MAX_TOKENS", "2000"))

COMPILER_SYSTEM_PROMPT = """Eres el Compilador OpenCode → Makina.

Tu trabajo es transformar lenguaje natural del usuario en un "Makina Prompt" estructurado.

## Formato de Salida (JSON exacto):

```json
{
  "makina_prompt": "...",
  "router": {
    "pick": "intent_name",
    "confidence": 0.85,
    "candidates": [{"name": "intent1", "score": 0.85}, {"name": "intent2", "score": 0.3}]
  }
}
```

## Reglas:

1. **makina_prompt**: Debe ser lenguaje Makina (machine language) que el runtime puede ejecutar directamente.
   - NO incluir texto humano + anexo

2. **router**: Clasificación de intención
   - pick: intent principal
   - confidence: 0.0-1.0
   - candidates: máximo 5 candidatos

3. **Intents válidos**:
   - implement_feature, debug_repo, refactor_migration, run_tests_ci
   - explain_concept, write_docs, design_architecture
   - toolchain_task, ops_health_check, incident_triage, plan_rollout
   - greeting, unknown

4. **Si no puedes determinar el intent**:
   - pick = "unknown"
   - confidence = 0.0
"""


@dataclass
class CompilerInput:
    """Input to the compiler service."""

    conversation_id: str
    turn_id: str
    correlation_id: str
    input_text: str
    mode: str = "makina_only"
    context_policy: dict[str, Any] = field(
        default_factory=lambda: {
            "graph": True,
            "vectorstore": True,
            "max_chunks": 12,
            "max_graph_entities": 40,
        }
    )
    capabilities: list[str] = field(
        default_factory=lambda: [
            "control_room",
            "rag",
            "pro_search",
            "scrape",
            "graph",
            "voice",
            "frontend",
        ]
    )
    flags: dict[str, Any] = field(
        default_factory=lambda: {
            "ws_first": True,
            "graph_ssot": True,
        }
    )


@dataclass
class CompilerOutput:
    """Output from the compiler service."""

    makina_prompt: str
    router: dict[str, Any]
    trace_hash: str
    retrieval_refs: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "makina_prompt": self.makina_prompt,
            "router": self.router,
            "trace_hash": self.trace_hash,
            "retrieval_refs": self.retrieval_refs,
            "metadata": self.metadata,
        }


def _sha256(data: str) -> str:
    return hashlib.sha256((data or "").encode("utf-8", errors="ignore")).hexdigest()


def _sha256_short(data: str) -> str:
    return _sha256(data)[:16]


def _emit_compiler_event(
    event_type: str,
    payload: dict[str, Any],
    conversation_id: str = "",
    trace_id: str = "",
) -> None:
    """Emit WS event for observability."""
    try:
        from api.persona.event_router import persona_emit

        persona_emit(
            conversation_id=conversation_id or "compiler",
            trace_id=trace_id,
            type=event_type,
            severity="info",
            payload=payload,
            stored=True,
        )
    except ImportError:
        logger.debug(f"Compiler event: {event_type}")
    except Exception as e:
        logger.warning(f"Failed to emit compiler event: {e}")


async def _call_openai(
    system_prompt: str,
    user_prompt: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call OpenAI Chat API for compilation."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    import httpx

    messages = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        for msg in conversation_history[-5:]:
            messages.append(msg)

    messages.append({"role": "user", "content": user_prompt})

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        return {
            "content": content.strip(),
            "usage": data.get("usage", {}),
            "model": data.get("model", OPENAI_MODEL),
        }


def _parse_compiler_response(raw: str) -> dict[str, Any]:
    """Parse the LLM response into structured output."""
    import re

    text = raw.strip()

    if "```json" in text:
        text = re.split(r"```json|```", text)[1]
    elif "```" in text:
        text = re.split(r"```", text)[1]

    text = text.strip()

    try:
        parsed = json.loads(text)
        return {
            "makina_prompt": parsed.get("makina_prompt", "UNKNOWN_ERROR"),
            "router": parsed.get(
                "router",
                {"pick": "unknown", "confidence": 0.0, "candidates": []},
            ),
        }
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse: {text[:100]}")
        return {
            "makina_prompt": raw,
            "router": {"pick": "unknown", "confidence": 0.0, "candidates": []},
        }


async def compile_with_chatroom(
    compiler_input: CompilerInput,
    conversation_history: list[dict[str, Any]] | None = None,
) -> CompilerOutput:
    """Primary compilation path: Event-driven via ChatRoom."""
    _emit_compiler_event(
        "compiler.start",
        {
            "conversation_id": compiler_input.conversation_id,
            "turn_id": compiler_input.turn_id,
            "input_len": len(compiler_input.input_text),
            "input_sha256": _sha256_short(compiler_input.input_text),
            "mode": compiler_input.mode,
        },
        conversation_id=compiler_input.conversation_id,
        trace_id=compiler_input.correlation_id,
    )

    start_time = time.time()

    try:
        from denis_unified_v1.compiler.context_pack_builder import build_context_pack

        context_pack = await build_context_pack(
            compiler_input.input_text,
            max_graph_entities=compiler_input.context_policy.get("max_graph_entities", 40),
            max_chunks=compiler_input.context_policy.get("max_chunks", 12),
            enable_graph=compiler_input.context_policy.get("graph", True),
            enable_vectorstore=compiler_input.context_policy.get("vectorstore", True),
        )

        _emit_compiler_event(
            "retrieval.result",
            {
                "graph_entities": len(context_pack.graph_entities),
                "vectorstore_chunks": len(context_pack.vectorstore_chunks),
                "graph_hash": context_pack.graph_hash,
                "chunks_hash": context_pack.chunks_hash,
                "combined_hash": context_pack.combined_hash,
            },
            conversation_id=compiler_input.conversation_id,
            trace_id=compiler_input.correlation_id,
        )

        user_prompt = f"""## Input del usuario:
{compiler_input.input_text}

{context_pack.to_compiler_input()}
"""

        raw_response = await _call_openai(
            COMPILER_SYSTEM_PROMPT,
            user_prompt,
            conversation_history,
        )

        parsed = _parse_compiler_response(raw_response["content"])

        trace_hash = _sha256_short(compiler_input.input_text + context_pack.combined_hash)

        latency_ms = int((time.time() - start_time) * 1000)

        output = CompilerOutput(
            makina_prompt=parsed["makina_prompt"],
            router=parsed["router"],
            trace_hash=trace_hash,
            retrieval_refs={
                "graph_hash": context_pack.graph_hash,
                "chunks_hash": context_pack.chunks_hash,
                "graph_entity_count": len(context_pack.graph_entities),
                "chunk_count": len(context_pack.vectorstore_chunks),
            },
            metadata={
                "version": VERSION,
                "latency_ms": latency_ms,
                "model": raw_response.get("model", OPENAI_MODEL),
                "usage": raw_response.get("usage", {}),
                "compiler": "chatroom",
            },
        )

        _emit_compiler_event(
            "compiler.result",
            {
                "pick": output.router.get("pick"),
                "confidence": output.router.get("confidence"),
                "trace_hash": trace_hash,
                "latency_ms": latency_ms,
            },
            conversation_id=compiler_input.conversation_id,
            trace_id=compiler_input.correlation_id,
        )

        return output

    except Exception as e:
        logger.error(f"ChatRoom compilation failed: {e}")
        _emit_compiler_event(
            "compiler.error",
            {"error": str(e)[:200], "fallback": "local_v2"},
            conversation_id=compiler_input.conversation_id,
            trace_id=compiler_input.correlation_id,
        )
        raise RuntimeError(f"ChatRoom compilation failed: {e}") from e


async def compile_with_fallback(
    compiler_input: CompilerInput,
) -> CompilerOutput:
    """Fallback compilation: local_v2 (makina_filter)."""
    _emit_compiler_event(
        "compiler.fallback_start",
        {
            "conversation_id": compiler_input.conversation_id,
            "turn_id": compiler_input.turn_id,
            "reason": "chatroom_unavailable",
        },
        conversation_id=compiler_input.conversation_id,
        trace_id=compiler_input.correlation_id,
    )

    from denis_unified_v1.inference.makina_filter import filter_input

    result = filter_input(
        {
            "prompt": compiler_input.input_text,
            "context_refs": [],
        }
    )

    output = CompilerOutput(
        makina_prompt=result.to_dict().get("intent", {}).get("pick", "unknown"),
        router={
            "pick": result.intent["pick"],
            "confidence": result.intent["confidence"],
            "candidates": result.intent_candidates,
        },
        trace_hash=_sha256_short(compiler_input.input_text + "fallback"),
        retrieval_refs={"mode": "fallback_local_v2"},
        metadata={
            "version": VERSION,
            "compiler": "makina_filter_v2",
            "degraded": True,
        },
    )

    _emit_compiler_event(
        "compiler.fallback_result",
        {
            "pick": output.router.get("pick"),
            "confidence": output.router.get("confidence"),
        },
        conversation_id=compiler_input.conversation_id,
        trace_id=compiler_input.correlation_id,
    )

    return output


async def compile(
    compiler_input: CompilerInput,
    conversation_history: list[dict[str, Any]] | None = None,
    anti_loop: bool = False,
) -> CompilerOutput:
    """Main compilation entry point."""
    if anti_loop:
        logger.info("Anti-loop detected, using fallback")
        return await compile_with_fallback(compiler_input)

    try:
        return await compile_with_chatroom(compiler_input, conversation_history)
    except RuntimeError as e:
        if "ChatRoom" in str(e) or "OpenAI" in str(e):
            logger.warning(f"ChatRoom failed, falling back: {e}")
            return await compile_with_fallback(compiler_input)
        raise


def compile_sync(
    compiler_input: CompilerInput,
    conversation_history: list[dict[str, Any]] | None = None,
    anti_loop: bool = False,
) -> CompilerOutput:
    """Synchronous wrapper for compile()."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(
                compile(compiler_input, conversation_history, anti_loop), loop
            ).result(timeout=30)
        return loop.run_until_complete(compile(compiler_input, conversation_history, anti_loop))
    except RuntimeError:
        return asyncio.run(compile(compiler_input, conversation_history, anti_loop))
