"""Tests for WindowManager."""

import pytest
import time
import threading
from denis_unified_v1.inference.window_manager import WindowManager, ProviderQuota


class TestWindowManager:
    """Test WindowManager quota controls."""

    def test_ventana_inicia_en_primer_uso(self):
        """Ventana inicia en primer uso (starts_on_first_use)."""
        wm = WindowManager(max_calls_per_window=5, window_seconds=3600)

        # Before any use, can_use should return True
        assert wm.can_use("llamacpp", "qwen2.5-0.5b") is True

        # Register first use
        assert wm.register_use("llamacpp", "qwen2.5-0.5b") is True

        # Stats should show window started
        stats = wm.get_stats("llamacpp", "qwen2.5-0.5b")
        assert stats["calls"] == 1
        assert stats["window_start"] is not None

    def test_bloquea_cuando_excede_limite(self):
        """Bloquea cuando se excede el límite."""
        wm = WindowManager(max_calls_per_window=3, window_seconds=3600)

        # Register 3 uses
        assert wm.register_use("llamacpp", "qwen2.5-0.5b") is True
        assert wm.register_use("llamacpp", "qwen2.5-0.5b") is True
        assert wm.register_use("llamacpp", "qwen2.5-0.5b") is True

        # 4th use should be blocked
        assert wm.can_use("llamacpp", "qwen2.5-0.5b") is False
        assert wm.register_use("llamacpp", "qwen2.5-0.5b") is False

    def test_ventana_expirada_resetea(self):
        """Ventana expirada resetea el contador."""
        wm = WindowManager(max_calls_per_window=3, window_seconds=1)

        # Register 3 uses
        wm.register_use("llamacpp", "qwen2.5-0.5b")
        wm.register_use("llamacpp", "qwen2.5-0.5b")
        wm.register_use("llamacpp", "qwen2.5-0.5b")

        # Should be blocked
        assert wm.can_use("llamacpp", "qwen2.5-0.5b") is False

        # Wait for window to expire
        time.sleep(1.5)

        # Should be available again
        assert wm.can_use("llamacpp", "qwen2.5-0.5b") is True

    def test_providers_separados(self):
        """Proveedores separados tienen cuotas independientes."""
        wm = WindowManager(max_calls_per_window=2, window_seconds=3600)

        # Fill up llamacpp
        wm.register_use("llamacpp", "qwen2.5-0.5b")
        wm.register_use("llamacpp", "qwen2.5-0.5b")

        # groq should still be available
        assert wm.can_use("groq", "llama-3.1-70b") is True

    def test_reset_especifico(self):
        """Reset de quota específica."""
        wm = WindowManager(max_calls_per_window=2, window_seconds=3600)

        wm.register_use("llamacpp", "qwen2.5-0.5b")
        wm.register_use("llamacpp", "qwen2.5-0.5b")

        # Reset specific
        wm.reset("llamacpp", "qwen2.5-0.5b")

        # Should be available again
        assert wm.can_use("llamacpp", "qwen2.5-0.5b") is True

    def test_reset_todo(self):
        """Reset de todas las cuotas."""
        wm = WindowManager(max_calls_per_window=2, window_seconds=3600)

        wm.register_use("llamacpp", "qwen2.5-0.5b")
        wm.register_use("groq", "llama-3.1-70b")

        # Reset all
        wm.reset()

        # All should be available
        assert wm.can_use("llamacpp", "qwen2.5-0.5b") is True
        assert wm.can_use("groq", "llama-3.1-70b") is True

    def test_thread_safety(self):
        """Thread safety del WindowManager."""
        wm = WindowManager(max_calls_per_window=100, window_seconds=3600)

        def register_many():
            for _ in range(50):
                wm.register_use("llamacpp", "qwen2.5-0.5b")

        threads = [threading.Thread(target=register_many) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly 100 calls (50 * 2)
        stats = wm.get_stats("llamacpp", "qwen2.5-0.5b")
        assert stats["calls"] == 100
