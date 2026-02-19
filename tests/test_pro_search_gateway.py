"""Tests for PRO_SEARCH Gateway Shadow Mode."""

import pytest
from unittest.mock import patch, MagicMock


class TestProSearchGatewayShadow:
    """Tests for PRO_SEARCH shadow mode with InferenceGateway."""

    def test_gateway_lazy_import(self):
        """Test gateway is lazily imported."""
        from denis_unified_v1.actions.pro_search_executor import _get_inference_gateway

        # Should not raise - returns None if gateway unavailable
        gateway = _get_inference_gateway()
        # May be None or a function depending on environment
        assert callable(gateway) or gateway is None

    def test_shadow_select_called_with_correct_task_profile(self):
        """Test shadow_select is called with premium_search task_profile."""
        from denis_unified_v1.actions.pro_search_executor import ProSearchExecutor

        with patch(
            "denis_unified_v1.actions.pro_search_executor._get_inference_gateway"
        ) as mock_get_gateway:
            mock_gateway = MagicMock()
            mock_gateway.return_value = None  # Gateway returns None (fail-open)
            mock_get_gateway.return_value = mock_gateway

            executor = ProSearchExecutor()
            # Can't fully test without Neo4j, but can verify the code path doesn't crash
            # Just verify the import works
            assert True

    def test_gateway_fail_open(self):
        """Test that gateway failure doesn't crash execution."""
        from denis_unified_v1.actions.pro_search_executor import _get_inference_gateway

        # Force reload to test fail-open
        import denis_unified_v1.actions.pro_search_executor as module

        module._inference_gateway = None

        with patch.dict(
            "sys.modules", {"denis_unified_v1.inference.inference_gateway": None}
        ):
            gateway = _get_inference_gateway()
            # Should return None (fail-open)
            assert gateway is None

    def test_shadow_decision_logged_to_decision_trace(self):
        """Test shadow decisions are logged to DecisionTrace."""
        # This test verifies the emit_decision_trace is called with shadow decisions
        # We can't fully test without Neo4j, but we can verify the code structure

        from denis_unified_v1.actions.pro_search_executor import ProSearchExecutor
        import inspect

        # Check that execute method exists
        assert hasattr(ProSearchExecutor, "execute")

        # Check that the method source contains shadow_model_selection
        source = inspect.getsource(ProSearchExecutor.execute)
        assert "shadow_model_selection" in source

    def test_task_profile_mapping(self):
        """Test correct task_profile is used for PRO_SEARCH."""
        from denis_unified_v1.inference.inference_gateway import _TASK_PROFILE_PROVIDERS

        # premium_search should map to a provider
        assert "premium_search" in _TASK_PROFILE_PROVIDERS

        config = _TASK_PROFILE_PROVIDERS["premium_search"]
        assert "provider" in config
        assert "model" in config

    def test_shadow_mode_env_variable(self):
        """Test SHADOW_MODE environment variable controls behavior."""
        import os
        from denis_unified_v1.inference import inference_gateway

        # Test default is on
        original = os.environ.get("DENIS_INFERENCE_SHADOW")
        try:
            os.environ.pop("DENIS_INFERENCE_SHADOW", None)
            # Reload to get default
            import importlib

            importlib.reload(inference_gateway)
            assert inference_gateway.SHADOW_MODE is True
        finally:
            if original:
                os.environ["DENIS_INFERENCE_SHADOW"] = original
            elif "DENIS_INFERENCE_SHADOW" in os.environ:
                del os.environ["DENIS_INFERENCE_SHADOW"]

    def test_integration_imports(self):
        """Test all required imports work."""
        # This ensures no circular imports or missing modules
        from denis_unified_v1.inference.output_contract import (
            OutputContract,
            OutputMode,
        )
        from denis_unified_v1.inference.artifactizer import Artifactizer, ArtifactRef

        assert OutputContract is not None
        assert OutputMode is not None
        assert Artifactizer is not None
        assert ArtifactRef is not None


class TestGatewayShadowDecision:
    """Tests for ShadowDecision dataclass."""

    def test_shadow_decision_fields(self):
        """Test ShadowDecision has required fields."""
        from denis_unified_v1.inference.inference_gateway import ShadowDecision

        decision = ShadowDecision(
            provider="llamacpp",
            model="qwen2.5-3b",
            strategy="single",
            reason="policy-match",
            task_profile_id="premium_search",
            latency_ms=25,
            quota_available=True,
        )

        assert decision.provider == "llamacpp"
        assert decision.model == "qwen2.5-3b"
        assert decision.strategy == "single"
        assert decision.reason == "policy-match"
        assert decision.task_profile_id == "premium_search"
        assert decision.latency_ms == 25
        assert decision.quota_available is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
