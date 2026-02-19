"""Compatibility adapter alias for Anthropic Chat provider."""

from denis_unified_v1.chat_cp.providers.anthropic_chat import AnthropicChatProvider

AnthropicChatAdapter = AnthropicChatProvider

__all__ = ["AnthropicChatProvider", "AnthropicChatAdapter"]
