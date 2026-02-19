"""Compatibility adapter alias for OpenAI Chat provider."""

from denis_unified_v1.chat_cp.providers.openai_chat import OpenAIChatProvider

OpenAIChatAdapter = OpenAIChatProvider

__all__ = ["OpenAIChatProvider", "OpenAIChatAdapter"]
