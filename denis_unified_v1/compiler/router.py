"""WS21-G: Compiler Router (makina pipeline, bus-first).

Este router compila texto NL → Makina program, emitiendo eventos para
timeline y materializador de grafo.

Hard rules:
- WS-first: emit compiler.* y retrieval.* events
- Fail-open: si ChatRoom falla → makina_filter local
- Anti-loop: hop_count >= 2 fuerza fallback
- Makina-only downstream: retorna makina DSL, nunca "actions"
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from .context_pack_builder import build_context_pack
from .graph_materializer import materialize_compiler_run
from .makina_filter import MakinaFilter, create_fallback_result
from .schemas import CompilerRequest, RetrievalRequest, RetrievalResult

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _sha256_short(text: str) -> str:
    return _sha256(text)[:16]


def _emit(
    *,
    conversation_id: str,
    trace_id: str | None,
    type: str,
    severity: str = "info",
    payload: dict[str, Any] | None = None,
    ui_hint: dict[str, Any] | None = None,
    stored: bool = True,
) -> None:
    try:
        from api.persona.event_router import persona_emit

        persona_emit(
            conversation_id=conversation_id or "default",
            trace_id=trace_id,
            type=type,
            severity=severity,
            payload=payload or {},
            ui_hint=ui_hint,
            stored=stored,
        )
    except Exception:
        return


def _fallback_local_makina(
    request: CompilerRequest, context: str = "", text: str | None = None
) -> tuple[str, dict[str, Any]]:
    """Local makina_filter fallback: returns (makina_json, meta).

    Acepta CompilerRequest completo o texto directo para compatibilidad.
    """
    filter_instance = MakinaFilter()

    if text:
        request = CompilerRequest(
            trace_id=request.trace_id,
            run_id=request.run_id,
            actor_id=request.actor_id,
            text=text,
            workspace=request.workspace,
            consciousness=request.consciousness,
            hop_count=request.hop_count,
        )

    result = filter_instance.compile(request, context)

    makina_str = result.makina
    if isinstance(result.makina, str):
        makina_str = result.makina
    elif hasattr(result.makina, "model_dump_json"):
        makina_str = result.makina.model_dump_json()

    return makina_str, {
        "pick": "makina_program",
        "confidence": result.confidence,
        "compiler": result.compiler,
        "degraded": result.degraded,
    }


async def _chatroom_compile_to_makina(*, text: str, context_pack_text: str) -> dict[str, Any]:
    """ChatRoom adapter (via Denis ChatRouter): returns dict with {plan, makina_prompt, router}."""
    from denis_unified_v1.inference.compiler_service import (
        COMPILER_SYSTEM_PROMPT,
        _parse_compiler_response,
    )
    from denis_unified_v1.chat_cp.router import ChatRouter
    from denis_unified_v1.chat_cp.contracts import ChatMessage, ChatRequest

    system = (
        COMPILER_SYSTEM_PROMPT
        + "\n\nDevuelve tambien un campo adicional 'plan' (string) con un plan breve (max 8 lineas) para timeline."
    )
    user_prompt = f"""## Input del usuario:
{text}

{context_pack_text}

Instrucciones:
- Responde en JSON.
- Incluye: makina_prompt, router, plan.
"""

    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user_prompt),
    ]

    chat_request = ChatRequest(
        messages=messages,
        model="gpt-4o-mini",
    )

    router = ChatRouter()
    chat_response = await router.route(chat_request)

    raw_content = chat_response.text or ""
    parsed = _parse_compiler_response(raw_content)

    plan = ""
    try:
        txt = raw_content.strip()
        if "```json" in txt:
            txt = txt.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in txt:
            txt = txt.split("```", 1)[1].split("```", 1)[0].strip()
        j = json.loads(txt)
        plan = str(j.get("plan") or "")
    except Exception:
        plan = ""

    return {
        "makina_prompt": str(parsed.get("makina_prompt") or ""),
        "router": dict(parsed.get("router") or {}),
        "plan": plan,
        "model": chat_response.model or "unknown",
        "usage": chat_response.usage or {},
        "provider": chat_response.provider or "unknown",
    }


async def compile_via_router(
    *,
    conversation_id: str,
    trace_id: str,
    run_id: str,
    actor_id: str | None,
    text: str,
    workspace: dict[str, Any] | None,
    consciousness: dict[str, Any] | None,
    hop_count: int = 0,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile NL input to Makina, emitting WS events for observability."""
    t0 = time.time()
    conv = (conversation_id or "").strip() or "default"
    tid = (trace_id or "").strip() or ""
    rid = (run_id or "").strip() or ""
    txt = str(text or "").strip()
    hop = int(hop_count or 0)

    # compiler.start
    _emit(
        conversation_id=conv,
        trace_id=tid,
        type="compiler.start",
        payload={
            "trace_id": tid,
            "run_id": rid,
            "actor_id": (actor_id or "").strip() or None,
            "input_text_sha256": _sha256(txt),
            "input_text_len": len(txt),
            "mode": "makina_only",
            "compiler": "chatroom",
            "hop": hop,
        },
        ui_hint={"render": "compiler", "icon": "cpu", "collapsible": True},
    )

    materialize_compiler_run(
        trace_id=tid,
        run_id=rid,
        actor_id=actor_id,
        event_type="compiler.start",
        payload={"trace_id": tid, "run_id": rid, "hop": hop},
    )

    # Anti-loop: force fallback
    if hop >= 2:
        request = CompilerRequest(
            trace_id=tid,
            run_id=rid,
            actor_id=actor_id,
            text=txt,
            workspace=workspace,
            consciousness=consciousness,
            hop_count=hop,
        )
        makina, rmeta = _fallback_local_makina(request, text=txt)
        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="compiler.plan",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "plan_redacted": "fallback (anti-loop)",
                "confidence": 0.0,
                "assumptions": [],
                "risks": ["anti_loop"],
            },
            ui_hint={"render": "compiler_plan", "icon": "route", "collapsible": True},
        )
        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="compiler.result",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "pick": rmeta.get("pick"),
                "confidence": rmeta.get("confidence", 0.0),
                "candidates_top3": rmeta.get("candidates_top3", []),
                "prompt_hash_sha256": _sha256(makina),
                "prompt_len": len(makina),
                "model": None,
                "trace_hash": _sha256(f"{tid}:{rid}:{_sha256_short(makina)}"),
                "degraded": True,
                "compiler": "fallback_local",
                "retrieval_refs_hash": "",
            },
            ui_hint={"render": "compiler", "icon": "check", "collapsible": True},
        )

        materialize_compiler_run(
            trace_id=tid,
            run_id=rid,
            actor_id=actor_id,
            event_type="compiler.result",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "compiler": "fallback_local",
                "degraded": True,
                "confidence": rmeta.get("confidence", 0.0),
                "prompt_hash_sha256": _sha256(makina),
            },
        )

        return {
            "makina_prompt": makina,
            "router": {
                "pick": rmeta.get("pick"),
                "confidence": rmeta.get("confidence", 0.0),
                "candidates": [],
            },
            "metadata": {"compiler": "fallback_local", "degraded": True},
            "retrieval_refs": {},
        }

    # retrieval.start
    pol = policy or {"graph": True, "vectorstore": True, "max_chunks": 12, "max_graph_entities": 40}
    query = txt  # MVP: query derived from NL only (workspace can be added later)
    _emit(
        conversation_id=conv,
        trace_id=tid,
        type="retrieval.start",
        payload={
            "trace_id": tid,
            "run_id": rid,
            "query_sha256": _sha256(query),
            "query_len": len(query),
            "policy": {
                "graph": bool(pol.get("graph", True)),
                "vectorstore": bool(pol.get("vectorstore", True)),
                "max_chunks": int(pol.get("max_chunks", 12)),
                "max_graph_entities": int(pol.get("max_graph_entities", 40)),
            },
        },
        ui_hint={"render": "retrieval", "icon": "search", "collapsible": True},
    )

    errors: list[str] = []
    context_pack = None
    try:
        context_pack = await build_context_pack(
            query,
            max_graph_entities=int(pol.get("max_graph_entities", 40)),
            max_chunks=int(pol.get("max_chunks", 12)),
            enable_graph=bool(pol.get("graph", True)),
            enable_vectorstore=bool(pol.get("vectorstore", True)),
        )
    except Exception as exc:
        errors.append(f"retrieval_failed:{type(exc).__name__}")
        context_pack = None

    # retrieval.result (hashes/counts only)
    if context_pack is None:
        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="retrieval.result",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "graph_count": 0,
                "chunk_ids_count": 0,
                "refs_hash": "",
                "warning": {"errors": errors} if errors else None,
            },
            ui_hint={"render": "retrieval", "icon": "list", "collapsible": True},
        )
        context_pack_text = "(No context available)"
        retrieval_refs_hash = ""
    else:
        refs_hash = _sha256(
            json.dumps(
                {
                    "graph_hash": context_pack.graph_hash,
                    "chunks_hash": context_pack.chunks_hash,
                    "combined_hash": context_pack.combined_hash,
                },
                sort_keys=True,
            )
        )
        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="retrieval.result",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "graph_count": int(len(context_pack.graph_entities or [])),
                "chunk_ids_count": int(len(context_pack.vectorstore_chunks or [])),
                "refs_hash": refs_hash,
                "warning": {"errors": errors} if errors else None,
            },
            ui_hint={"render": "retrieval", "icon": "list", "collapsible": True},
        )
        context_pack_text = context_pack.to_compiler_input()
        retrieval_refs_hash = refs_hash

    # ChatRoom primary
    try:
        if not (os.getenv("OPENAI_API_KEY") or "").strip():
            raise RuntimeError("OPENAI_API_KEY_not_configured")

        compiled = await _chatroom_compile_to_makina(text=txt, context_pack_text=context_pack_text)
        plan = str(compiled.get("plan") or "").strip()
        # Emit compiler.plan (best-effort, keep short)
        plan_redacted = plan.strip().replace("\r\n", "\n")
        if len(plan_redacted) > 800:
            plan_redacted = plan_redacted[:800] + "..."
        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="compiler.plan",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "plan_redacted": plan_redacted,
                "confidence": float((compiled.get("router") or {}).get("confidence") or 0.0),
                "assumptions": [],
                "risks": [],
            },
            ui_hint={"render": "compiler_plan", "icon": "route", "collapsible": True},
        )

        makina = str(compiled.get("makina_prompt") or "").strip()
        router_meta = dict(compiled.get("router") or {})
        pick = str(router_meta.get("pick") or "unknown")
        confidence = float(router_meta.get("confidence") or 0.0)
        candidates = (
            router_meta.get("candidates") if isinstance(router_meta.get("candidates"), list) else []
        )

        latency_ms = int((time.time() - t0) * 1000)
        trace_hash = _sha256(f"{tid}:{rid}:{_sha256_short(makina)}:{retrieval_refs_hash}")
        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="compiler.result",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "pick": pick,
                "confidence": confidence,
                "candidates_top3": (candidates[:3] if candidates else []),
                "prompt_hash_sha256": _sha256(makina),
                "prompt_len": len(makina),
                "model": compiled.get("model"),
                "trace_hash": trace_hash,
                "degraded": False,
                "compiler": "chatroom",
                "retrieval_refs_hash": retrieval_refs_hash,
                "latency_ms": latency_ms,
            },
            ui_hint={"render": "compiler", "icon": "check", "collapsible": True},
        )
        return {
            "makina_prompt": makina,
            "router": {
                "pick": pick,
                "confidence": confidence,
                "candidates": candidates[:5] if isinstance(candidates, list) else [],
            },
            "retrieval_refs": {
                "refs_hash": retrieval_refs_hash,
                "graph_hash": getattr(context_pack, "graph_hash", "") if context_pack else "",
                "chunks_hash": getattr(context_pack, "chunks_hash", "") if context_pack else "",
            },
            "metadata": {
                "compiler": "chatroom",
                "latency_ms": latency_ms,
                "model": compiled.get("model"),
                "usage": compiled.get("usage") or {},
                "degraded": False,
            },
        }
    except Exception as exc:
        # Fail-open fallback
        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="compiler.error",
            severity="warning",
            payload={
                "code": "chatroom_failed",
                "msg": str(exc)[:200],
                "detail": {"fallback": "local_v2"},
                "trace_id": tid,
                "run_id": rid,
            },
            ui_hint={"render": "error", "icon": "alert", "collapsible": True},
        )

        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="compiler.plan",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "plan_redacted": "fallback (chatroom unavailable)",
                "confidence": 0.0,
                "assumptions": [],
                "risks": ["chatroom_unavailable"],
            },
            ui_hint={"render": "compiler_plan", "icon": "route", "collapsible": True},
        )

        request = CompilerRequest(
            trace_id=tid,
            run_id=rid,
            actor_id=actor_id,
            text=txt,
            workspace=workspace,
            consciousness=consciousness,
            hop_count=hop,
        )
        makina, rmeta = _fallback_local_makina(request, text=txt)
        latency_ms = int((time.time() - t0) * 1000)
        trace_hash = _sha256(f"{tid}:{rid}:{_sha256_short(makina)}:{retrieval_refs_hash}:fallback")
        _emit(
            conversation_id=conv,
            trace_id=tid,
            type="compiler.result",
            payload={
                "trace_id": tid,
                "run_id": rid,
                "pick": rmeta.get("pick"),
                "confidence": rmeta.get("confidence", 0.0),
                "candidates_top3": rmeta.get("candidates_top3", []),
                "prompt_hash_sha256": _sha256(makina),
                "prompt_len": len(makina),
                "model": None,
                "trace_hash": trace_hash,
                "degraded": True,
                "compiler": "fallback_local",
                "retrieval_refs_hash": retrieval_refs_hash,
                "latency_ms": latency_ms,
            },
            ui_hint={"render": "compiler", "icon": "check", "collapsible": True},
        )
        return {
            "makina_prompt": makina,
            "router": {
                "pick": rmeta.get("pick"),
                "confidence": rmeta.get("confidence", 0.0),
                "candidates": [],
            },
            "retrieval_refs": {"refs_hash": retrieval_refs_hash},
            "metadata": {"compiler": "fallback_local", "degraded": True, "latency_ms": latency_ms},
        }
