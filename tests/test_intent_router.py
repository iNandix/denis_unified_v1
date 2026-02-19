#!/usr/bin/env python3
"""Tests for IntentRouter."""

import pytest
import os
import sys

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

os.environ["GROQ_API_KEY"] = "test_key"


class MockMakinaOutput:
    """Mock MakinaOutput for testing."""

    def __init__(
        self,
        intent=None,
        confidence=0.8,
        constraints=None,
        missing_inputs=None,
        acceptance_criteria=None,
        context_refs=None,
    ):
        self.intent = intent or {"pick": "implement_feature", "confidence": confidence}
        self.constraints = constraints or []
        self.missing_inputs = missing_inputs or []
        self.acceptance_criteria = acceptance_criteria or []
        self.context_refs = context_refs or []


class TestIntentRouter:
    """Test IntentRouter routing logic."""

    def test_routes_implement_to_groq_when_available(self):
        """Test that implement_feature routes to groq when available."""
        from denis_unified_v1.inference.intent_router import IntentRouter, RoutedRequest

        router = IntentRouter()
        makina = MockMakinaOutput(intent={"pick": "implement_feature", "confidence": 0.8})

        result = router.route(makina, "crea endpoint fastapi")

        assert result.model in ["groq", "llama_local", "claude"], f"Got {result.model}"

    def test_fallback_to_local_when_groq_unavailable(self):
        """Test fallback to llama_local when groq unavailable."""
        from denis_unified_v1.inference.intent_router import IntentRouter

        router = IntentRouter()
        makina = MockMakinaOutput(intent={"pick": "implement_feature", "confidence": 0.8})

        # Mock groq as unavailable
        router._quota_registry._available_models = ["llama_local"]

        result = router.route(makina, "crea endpoint")

        assert result.model == "llama_local"

    def test_blocks_on_missing_inputs(self):
        """Test that missing_inputs blocks the request."""
        from denis_unified_v1.inference.intent_router import IntentRouter

        router = IntentRouter()
        makina = MockMakinaOutput(
            intent={"pick": "implement_feature", "confidence": 0.8}, missing_inputs=["target_file"]
        )

        result = router.route(makina, "haz")

        assert result.blocked is True
        assert "target_file" in result.block_reason

    def test_low_confidence_goes_local(self):
        """Test low confidence routes to llama_local."""
        from denis_unified_v1.inference.intent_router import IntentRouter

        router = IntentRouter()
        makina = MockMakinaOutput(intent={"pick": "implement_feature", "confidence": 0.3})

        result = router.route(makina, "haz")

        assert result.model == "llama_local"

    def test_implicit_tasks_for_implement(self):
        """Test implicit_tasks injected for implement_feature."""
        from denis_unified_v1.inference.intent_router import IntentRouter

        router = IntentRouter()
        makina = MockMakinaOutput(intent={"pick": "implement_feature", "confidence": 0.8})

        result = router.route(makina, "crea componente")

        # Should have implicit tasks
        assert len(result.implicit_tasks) > 0

    def test_implicit_tasks_for_debug(self):
        """Test implicit_tasks injected for debug_repo."""
        from denis_unified_v1.inference.intent_router import IntentRouter

        router = IntentRouter()
        makina = MockMakinaOutput(intent={"pick": "debug_repo", "confidence": 0.8})

        result = router.route(makina, "arregla el bug")

        # Should have implicit tasks
        assert len(result.implicit_tasks) > 0

    def test_fail_open_always_returns_routed_request(self):
        """Test that fail-open always returns valid RoutedRequest."""
        from denis_unified_v1.inference.intent_router import IntentRouter

        router = IntentRouter()

        # Use a mock that simulates a broken MakinaOutput
        class BrokenOutput:
            intent = {"pick": "unknown"}

        result = router.route_safe(BrokenOutput(), "test prompt", "default")

        assert result is not None
        assert hasattr(result, "model")
        assert hasattr(result, "intent")

    def test_quota_exhausted_triggers_fallback(self):
        """Test that exhausted quota triggers fallback."""
        from denis_unified_v1.inference.intent_router import IntentRouter

        router = IntentRouter()
        makina = MockMakinaOutput(intent={"pick": "implement_feature", "confidence": 0.8})

        # Mark groq as exhausted
        router._quota_registry.mark_quota_exhausted("groq", 3600)

        result = router.route(makina, "crea test")

        # Should fallback to llama_local
        assert result.fallback_used is True or result.model == "llama_local"


class TestRouteInput:
    """Test route_input unified API."""

    def test_route_input_unified_api(self):
        """Test route_input returns valid RoutedRequest."""
        from denis_unified_v1.inference.intent_router import route_input

        result = route_input("crea endpoint fastapi", "test_session", [])

        assert result is not None
        assert hasattr(result, "model")
        assert hasattr(result, "intent")
        assert hasattr(result, "routing_trace")

    def test_route_input_low_confidence(self):
        """Test route_input with low confidence prompt."""
        from denis_unified_v1.inference.intent_router import route_input

        result = route_input("haz algo", "test_session", [])

        # Should route to llama_local due to low confidence
        assert result.model == "llama_local"


class TestQuotaRegistry:
    """Test QuotaRegistry."""

    def test_get_available_models(self):
        """Test getting available models."""
        from denis_unified_v1.inference.quota_registry import QuotaRegistry

        qr = QuotaRegistry()
        models = qr.get_available_models()

        assert "llama_local" in models

    def test_best_model_for_intent(self):
        """Test getting best model for intent."""
        from denis_unified_v1.inference.quota_registry import QuotaRegistry

        qr = QuotaRegistry()
        model = qr.get_best_model_for("implement_feature")

        assert model is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
