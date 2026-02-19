"""Provider protocol for chat control plane."""

from __future__ import annotations

from typing import Protocol

from denis_unified_v1.chat_cp.contracts import ChatRequest, ChatResponse


class ChatProvider(Protocol):
    provider: str

    def is_configured(self) -> bool: ...

    async def chat(self, request: ChatRequest) -> ChatResponse: ...
