#!/usr/bin/env python3
"""ConversationLoop — High-level conversational interface for Denis."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


CONVERSATION_HISTORY: List[Dict[str, str]] = []


@dataclass
class ConversationTurn:
    """A single conversation turn."""

    user_text: str
    intent: str
    model: str
    response: str
    session_id: str
    repo_name: str
    tokens_used: int = 0
    cp_approved: Optional[dict] = None
    latency_ms: float = 0.0
    branch: str = ""


def chat(
    user_text: str,
    session_id: str = None,
    conversation_history: List[Dict[str, str]] = None,
) -> ConversationTurn:
    """
    Entry point for conversational interaction with Denis.
    Fail-open: always returns a ConversationTurn.
    """
    start_time = time.time()

    session_id = session_id or _read_session_id()
    repo_info = _read_repo_info()
    repo_name = repo_info.get("repo_name", "unknown")
    repo_id = repo_info.get("repo_id", "")
    branch = repo_info.get("branch", "main")

    if conversation_history is None:
        conversation_history = CONVERSATION_HISTORY

    try:
        from denis_unified_v1.inference.intent_router import route_input
        from denis_unified_v1.inference.modelcaller import call_model

        routed = route_input(user_text, session_id)

        routed.repo_id = repo_id
        routed.repo_name = repo_name
        routed.branch = branch

        if routed.blocked:
            return ConversationTurn(
                user_text=user_text,
                intent=routed.intent,
                model=routed.model,
                response=f"[Bloqueado: {routed.block_reason}]",
                session_id=session_id,
                repo_name=repo_name,
                branch=branch,
                latency_ms=(time.time() - start_time) * 1000,
            )

        system_prompt = _build_system_prompt(routed, conversation_history)

        response = call_model(routed, system_prompt, user_text)

        _write_agent_result(routed, response)

        _record_execution_to_graph(routed)

        _add_to_history(conversation_history, user_text, response.text)

        return ConversationTurn(
            user_text=user_text,
            intent=routed.intent,
            model=response.model,
            response=response.text,
            session_id=session_id,
            repo_name=repo_name,
            branch=branch,
            tokens_used=response.tokens_used,
            latency_ms=(time.time() - start_time) * 1000,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}")
        return ConversationTurn(
            user_text=user_text,
            intent="unknown",
            model="llama_local",
            response=f"[Error: {str(e)[:100]}]",
            session_id=session_id,
            repo_name=repo_name,
            branch=branch,
            latency_ms=(time.time() - start_time) * 1000,
        )


def _add_to_history(history: List[Dict[str, str]], user: str, assistant: str) -> None:
    """Add turn to conversation history."""
    history.append({"role": "user", "content": user})
    history.append({"role": "assistant", "content": assistant})
    if len(history) > 20:
        history[:] = history[-20:]


def _read_session_id() -> str:
    """Read session ID from file."""
    try:
        with open("/tmp/denis/session_id.txt") as f:
            content = f.read().strip()
            if "|" in content:
                return content.split("|")[0]
            return content
    except Exception:
        return "default"


def _read_repo_info() -> Dict[str, str]:
    """Read repo info from session file."""
    try:
        with open("/tmp/denis/session_id.txt") as f:
            content = f.read().strip()
            if "|" in content:
                parts = content.split("|")
                return {
                    "repo_id": parts[1] if len(parts) > 1 else "",
                    "repo_name": parts[2] if len(parts) > 2 else "unknown",
                    "branch": parts[3] if len(parts) > 3 else "main",
                }
    except Exception:
        pass

    try:
        from control_plane.repo_context import RepoContext

        repo = RepoContext()
        return {
            "repo_id": repo.repo_id,
            "repo_name": repo.repo_name,
            "branch": repo.branch,
        }
    except Exception:
        return {"repo_id": "", "repo_name": "unknown", "branch": "main"}


def _record_execution_to_graph(routed) -> None:
    """Record execution to graph for learning."""
    try:
        from kernel.ghost_ide.symbol_graph import (
            record_execution,
            link_symbol_to_intent,
            upsert_repo,
        )

        session_id = getattr(routed, "session_id", "default") or "default"

        record_execution(
            intent=routed.intent,
            constraints=routed.constraints or [],
            tasks=routed.implicit_tasks or [],
            session_id=session_id,
        )

        if routed.repo_id and routed.repo_name:
            upsert_repo(routed.repo_id, routed.repo_name, routed.branch or "main", "")

        if routed.context_prefilled and "modified_paths" in routed.context_prefilled:
            for path in routed.context_prefilled.get("modified_paths", [])[:5]:
                link_symbol_to_intent(path, routed.intent, session_id)

    except Exception as e:
        logger.debug(f"Graph record failed: {e}")


def _build_system_prompt(routed, history: List[Dict[str, str]] = None) -> str:
    """Build system prompt from routed request."""
    lines = [
        "You are Denis, an AI coding assistant.",
        f"Current repository: {routed.repo_name or 'unknown'}",
        f"Branch: {routed.branch or 'main'}",
        f"Intent: {routed.intent}",
    ]

    if routed.context_prefilled:
        ctx_str = str(routed.context_prefilled)[:300]
        lines.append(f"Context: {ctx_str}")

    if routed.do_not_touch_auto:
        lines.append(f"DO NOT MODIFY: {', '.join(routed.do_not_touch_auto[:3])}")

    if routed.implicit_tasks:
        lines.append(f"Tasks: {', '.join(routed.implicit_tasks[:3])}")

    if history and len(history) > 0:
        recent = history[-6:]
        history_str = "\n".join([f"{h['role']}: {h['content'][:100]}" for h in recent])
        lines.append(f"\nRecent conversation:\n{history_str}")

    lines.append(
        "\nProvide clear, helpful responses. If you need to modify code, explain what you will do."
    )

    return "\n".join(lines)


def _write_agent_result(routed, response) -> None:
    """Write agent result for daemon processing."""
    import json
    import os

    result = {
        "intent": routed.intent,
        "model": response.model,
        "mission": response.text[:500],
        "files_touched": [],
        "constraints": routed.constraints,
        "implicit_tasks": routed.implicit_tasks,
        "acceptance_criteria": routed.acceptance_criteria,
        "repo_id": routed.repo_id,
        "repo_name": routed.repo_name,
        "branch": routed.branch,
        "success": not response.error,
    }

    try:
        os.makedirs("/tmp/denis", exist_ok=True)
        with open("/tmp/denis/agent_result.json", "w") as f:
            json.dump(result, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not write agent result: {e}")


def clear_history() -> None:
    """Clear conversation history."""
    CONVERSATION_HISTORY.clear()


__all__ = ["ConversationTurn", "chat", "clear_history", "CONVERSATION_HISTORY"]
