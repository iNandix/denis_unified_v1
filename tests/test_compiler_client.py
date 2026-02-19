"""Tests for Compiler Client (WS21-G client)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestCompilerClientImports:
    """Test compiler client can be imported."""

    def test_import_compiler_client(self):
        """Test import of compiler client module."""
        from denis_unified_v1.inference.compiler_client import (
            VERSION,
            call_compiler,
            compile_with_fallback,
            get_compiler_client_config,
        )

        assert VERSION.startswith("1.")
        assert callable(call_compiler)
        assert callable(compile_with_fallback)


class TestCompilerClientConfig:
    """Test compiler client configuration."""

    def test_get_config(self):
        """Test getting compiler client config."""
        from denis_unified_v1.inference.compiler_client import get_compiler_client_config

        config = get_compiler_client_config()

        assert "version" in config
        assert "compiler_url" in config
        assert "makina_only" in config
        assert config["makina_only"] is True


class TestCompilerClientFallback:
    """Test fallback functionality."""

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        """Test fallback when remote compiler fails."""
        from denis_unified_v1.inference.compiler_client import compile_with_fallback

        with patch(
            "denis_unified_v1.inference.compiler_client.call_compiler", new_callable=AsyncMock
        ) as mock_call:
            mock_call.side_effect = RuntimeError("connection refused")

            result = await compile_with_fallback("crea un test")

            assert result.makina_prompt is not None
            assert result.used_remote is False


class TestMakinaOnlyFilter:
    """Test makina_filter with compiler integration."""

    def test_filter_with_compiler_import(self):
        """Test filter_with_compiler can be imported."""
        from denis_unified_v1.inference.makina_filter import filter_with_compiler

        assert callable(filter_with_compiler)

    def test_filter_with_compiler_returns_makina_output(self):
        """Test filter_with_compiler returns MakinaOutput."""
        from denis_unified_v1.inference.makina_filter import filter_with_compiler

        with patch(
            "denis_unified_v1.inference.compiler_client.compile_with_fallback_sync"
        ) as mock_compile:
            mock_compile.return_value = MagicMock(
                router={"pick": "implement_feature", "confidence": 0.9, "candidates": []},
                used_remote=True,
                metadata={"compiler": "test"},
            )

            result = filter_with_compiler({"prompt": "crea algo"})

            assert result.intent["pick"] == "implement_feature"
