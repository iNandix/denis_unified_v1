"""Unified chat control-plane client."""

from __future__ import annotations

import os
import threading

from denis_unified_v1.chat_cp.router import ChatRouter, RoutingPolicy
from denis_unified_v1.chat_cp.contracts import ChatRequest, ChatResponse

_ROUTER: ChatRouter | None = None
_LOCK = threading.Lock()


def get_policy_from_graph(task_profile_id: str) -> RoutingPolicy | None:
    """Graph hook placeholder for policy resolution.

    Current behavior: returns None so default policy is used.
    """
    _ = task_profile_id
    return None


def _get_router() -> ChatRouter:
    global _ROUTER
    if _ROUTER is not None:
        return _ROUTER
    with _LOCK:
        if _ROUTER is None:
            _ROUTER = ChatRouter()
    return _ROUTER


async def chat(request: ChatRequest, *, shadow_mode: bool = False) -> ChatResponse:
    policy = get_policy_from_graph(request.task_profile_id)
    router = _get_router()
    strict = os.getenv("DENIS_CHAT_CP_STRICT", "0") == "1"
    return await router.route(
        request,
        fail_open=not strict,
        shadow_mode=shadow_mode,
        policy_override=policy,
        strict_mode=strict,
    )
