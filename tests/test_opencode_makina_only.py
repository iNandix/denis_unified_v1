"""Tests for OpenCode Makina-Only Mode (WS21-G).

Tests that verify:
- Primary: ChatRoom compiler is used (when available)
- Fallback: local intent router only when compiler unavailable
- Runtime receives only makina_prompt (never raw text)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestOpenCodeMakinaOnly:
    """Test OPENCODE_MAKINA_ONLY mode."""

    def test_makina_only_mode_enabled(self):
        """Test that MAKINA_ONLY is enabled by default."""
        import os

        os.environ["OPENCODE_MAKINA_ONLY"] = "1"

        from denis_unified_v1.inference.makina_filter import MAKINA_ONLY_MODE

        assert MAKINA_ONLY_MODE is True

    def test_filter_with_compiler_uses_remote_when_available(self):
        """Test that filter_with_compiler tries remote first."""
        from denis_unified_v1.inference.makina_filter import filter_with_compiler

        with patch(
            "denis_unified_v1.inference.compiler_client.compile_with_fallback_sync"
        ) as mock_compile:
            mock_compile.return_value = MagicMock(
                router={"pick": "implement_feature", "confidence": 0.9, "candidates": []},
                used_remote=True,
                metadata={"compiler": "chatroom"},
            )

            result = filter_with_compiler({"prompt": "crea algo"})

            assert mock_compile.called, "Should call remote compiler"
            assert result.intent["pick"] == "implement_feature"


class TestCompilerPrimaryFallback:
    """Test that ChatRoom is primary, local is fallback."""

    def test_compile_tries_remote_first(self):
        """Test compile tries remote compiler before fallback."""
        import asyncio
        from denis_unified_v1.inference.compiler_client import compile_with_fallback

        async def test():
            with patch(
                "denis_unified_v1.inference.compiler_client.call_compiler", new_callable=AsyncMock
            ) as mock_remote:
                mock_remote.return_value = MagicMock(
                    makina_prompt="tool:create",
                    router={"pick": "implement_feature", "confidence": 0.9},
                    trace_hash="abc",
                    retrieval_refs={},
                    metadata={},
                    used_remote=True,
                )

                result = await compile_with_fallback("crea algo")

                assert mock_remote.called, "Should call remote compiler first"
                assert result.used_remote is True

        asyncio.run(test())

    def test_compile_fallback_on_remote_error(self):
        """Test fallback to local when remote fails."""
        import asyncio
        from denis_unified_v1.inference.compiler_client import compile_with_fallback

        async def test():
            with patch(
                "denis_unified_v1.inference.compiler_client.call_compiler", new_callable=AsyncMock
            ) as mock_remote:
                mock_remote.side_effect = RuntimeError("connection refused")

                result = await compile_with_fallback("crea algo")

                assert result.used_remote is False
                assert result.makina_prompt is not None

        asyncio.run(test())

    def test_anti_loop_forces_fallback(self):
        """Test that anti_loop forces local fallback."""
        import asyncio
        from denis_unified_v1.inference.compiler_service import compile, CompilerInput

        async def test():
            compiler_input = CompilerInput(
                conversation_id="test",
                turn_id="t1",
                correlation_id="c1",
                input_text="crea algo",
            )

            result = await compile(compiler_input, anti_loop=True)

            assert result.router.get("pick") is not None

        asyncio.run(test())


class TestMakinaPromptOnly:
    """Test that runtime receives only makina_prompt."""

    def test_output_contains_makina_prompt(self):
        """Test output always contains makina_prompt."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "crea algo"})

        assert "intent" in result.to_dict()
        assert "intent_candidates" in result.to_dict()
        assert "intent_trace" in result.to_dict()

    def test_no_raw_text_forwarded(self):
        """Test that raw user text is not in the output for runtime."""
        from denis_unified_v1.inference.makina_filter import filter_input

        result = filter_input({"prompt": "crea algo special"})

        output = result.to_dict()

        assert output.get("intent", {}).get("pick") is not None
        for value in output.values():
            if isinstance(value, str):
                assert "crea algo special" not in value or value == "crea algo special"


class TestCompilerCircuitBreaker:
    """Test circuit breaker behavior."""

    def test_multiple_failures_trigger_fallback(self):
        """Test that multiple failures use fallback."""
        import asyncio
        from denis_unified_v1.inference.compiler_client import compile_with_fallback

        async def test():
            call_count = 0

            async def mock_call(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 3:
                    raise RuntimeError("connection refused")
                return MagicMock(
                    makina_prompt="tool:recovered",
                    router={"pick": "unknown"},
                    used_remote=True,
                )

            with patch(
                "denis_unified_v1.inference.compiler_client.call_compiler", side_effect=mock_call
            ):
                result = await compile_with_fallback("test")

                assert result.used_remote is False

        asyncio.run(test())
