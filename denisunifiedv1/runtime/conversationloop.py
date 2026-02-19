from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_SESSION_ID_PATH = "/tmp/denis/sessionid.txt"
_AGENT_RESULT_PATH = "/tmp/denis/agentresult.json"

_CONVERSATION_ONLY = {"greeting", "explainconcept", "unknown"}


@dataclass
class ConversationTurn:
    user_text: str
    intent: str
    model: str
    response: str
    session_id: str
    repo_name: str
    tokens_used: int
    latency_ms: float = 0.0
    used_fallback: bool = False
    cp_approved: Optional[dict] = field(default=None)


def _read_session_fields() -> tuple:
    try:
        raw = open(_SESSION_ID_PATH).read().strip()
        parts = (raw + "||||").split("|")
        return parts[0] or "default", parts[1], parts[2] or "unknown", parts[3] or "main"
    except Exception:
        return "default", "", "unknown", "main"


def _get_session_context() -> dict:
    sid, _, _, _ = _read_session_fields()
    try:
        from kernel.ghostide.contextharvester import ContextHarvester

        ctx = ContextHarvester(session_id=sid, watch_paths=[]).get_session_context()
        return {
            "session_id": sid,
            "modified_paths": ctx.get("files_harvested", []),
            "do_not_touch_auto": ctx.get("do_not_touch_auto", []),
            "context_prefilled": {},
        }
    except Exception as exc:
        logger.debug("getSessionContext failed (fail-open): %s", exc)
        return {
            "session_id": sid,
            "modified_paths": [],
            "do_not_touch_auto": [],
            "context_prefilled": {},
        }


def _write_agent_result(routed, response, repo_fields: tuple) -> None:
    sid, repo_id, repo_name, branch = repo_fields
    try:
        os.makedirs("/tmp/denis", exist_ok=True)

        intent_val = getattr(routed, "intent", {})
        if isinstance(intent_val, dict):
            intent_str = intent_val.get("pick", "unknown")
            confidence = float(intent_val.get("confidence", 0.0))
        else:
            intent_str = str(intent_val)
            confidence = 0.0

        payload = {
            "intent": intent_str,
            "confidence": confidence,
            "constraints": list(getattr(routed, "constraints", []) or []),
            "files_touched": list((getattr(routed, "context_prefilled", {}) or {}).keys()),
            "mission_completed": response.text[:200],
            "success": not bool(response.error),
            "session_id": sid,
            "repo_id": repo_id,
            "repo_name": repo_name,
            "branch": branch,
            "model": response.model,
            "tokens_used": response.tokens_used,
        }
        with open(_AGENT_RESULT_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Failed to write agentresult.json: %s", exc)


def chat(
    user_text: str,
    session_id: str = None,
    max_tokens: int = 512,
) -> ConversationTurn:
    t0 = time.time()
    repo_fields = _read_session_fields()
    sid, repo_id, repo_name, branch = repo_fields
    if session_id:
        sid = session_id

    try:
        from denisunifiedv1.inference.intentrouter import route_input

        routed = route_input(user_text, session_id=sid)
    except Exception as exc:
        logger.error("routeInput failed: %s", exc)
        return ConversationTurn(
            user_text=user_text,
            intent="unknown",
            model="none",
            response="[error interno en el router — revisa logs]",
            session_id=sid,
            repo_name=repo_name,
            tokens_used=0,
            latency_ms=(time.time() - t0) * 1000,
        )

    intent_val = getattr(routed, "intent", {})
    intent = intent_val.get("pick", "unknown") if isinstance(intent_val, dict) else str(intent_val)

    try:
        from denisunifiedv1.inference.makinafilter import pre_execute_hook

        should_proceed, _, block_reason = pre_execute_hook(user_text, [])
        if not should_proceed:
            return ConversationTurn(
                user_text=user_text,
                intent=intent,
                model="none",
                response=f"[bloqueado: {block_reason}]",
                session_id=sid,
                repo_name=repo_name,
                tokens_used=0,
                latency_ms=(time.time() - t0) * 1000,
            )
    except Exception as exc:
        logger.debug("preExecuteHook unavailable (skip): %s", exc)

    try:
        from denisunifiedv1.personality.sessionpromptbuilder import build_system_prompt

        ctx = _get_session_context()
        ctx["repo_name"] = repo_name
        ctx["branch"] = branch
        system_prompt = build_system_prompt(ctx)
    except Exception as exc:
        logger.warning("buildSystemPrompt failed, using minimal: %s", exc)
        system_prompt = (
            "Eres Denis. Habla en español, directo y humano. "
            "No inventes rutas ni archivos. Usa tools cuando falte contexto."
        )

    try:
        from denisunifiedv1.inference.modelcaller import call_model

        response = call_model(routed, system_prompt, user_text, max_tokens=max_tokens)
    except Exception as exc:
        logger.error("call_model failed: %s", exc)
        from denisunifiedv1.inference.modelcaller import ModelResponse

        response = ModelResponse(
            text="[error llamando al modelo]",
            model="none",
            tokens_used=0,
            latency_ms=0.0,
            error=str(exc),
        )

    if intent not in _CONVERSATION_ONLY:
        _write_agent_result(routed, response, repo_fields)

    return ConversationTurn(
        user_text=user_text,
        intent=intent,
        model=response.model,
        response=response.text,
        session_id=sid,
        repo_name=repo_name,
        tokens_used=response.tokens_used,
        latency_ms=(time.time() - t0) * 1000,
        used_fallback=response.used_fallback,
    )
