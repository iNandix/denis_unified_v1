"""Tests for PR2: GatewayRouter + shadow hook in router.py.

Checklist:
- Shadow desactivado por defecto
- Timeout/fallo no rompe requests
- Real decision identica a baseline
- DecisionTrace recibe registro SHADOW cuando flags ON
- Fast intents never select expensive models (regression)
"""

from __future__ import annotations

import os
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import asdict

from denis_unified_v1.inference.gateway_router import (
    GatewayRouter,
    SEED_ROUTING_RULES,
    SEED_TASK_PROFILES,
    SEED_TOOL_POLICIES,
    _EXPENSIVE_PROVIDERS,
    _FAST_PROFILES,
)
from denis_unified_v1.inference.gateway_types import (
    BudgetEnvelope,
    RoutingRule,
    ToolPolicy,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# GatewayRouter: resolve_task_profile
# ---------------------------------------------------------------------------

class TestResolveTaskProfile:
    def test_exact_match(self):
        router = GatewayRouter()
        assert router.resolve_task_profile("search", "premium") == "premium_search"

    def test_wildcard_match(self):
        router = GatewayRouter()
        assert router.resolve_task_profile("greeting", "any_phase") == "intent_detection_fast"
        assert router.resolve_task_profile("chat_general", "deep") == "chat_general"

    def test_unknown_falls_to_chat_general(self):
        router = GatewayRouter()
        assert router.resolve_task_profile("totally_unknown", "x") == "chat_general"

    def test_code_generate(self):
        router = GatewayRouter()
        assert router.resolve_task_profile("code_generate", "deep") == "codecraft_generate"


# ---------------------------------------------------------------------------
# GatewayRouter: select_candidates
# ---------------------------------------------------------------------------

class TestSelectCandidates:
    def test_returns_candidates_for_known_profile(self):
        router = GatewayRouter()
        candidates = router.select_candidates("chat_general")
        assert len(candidates) > 0
        assert candidates[0] == "qwen_coder7b_local"

    def test_filters_unavailable(self):
        available_set = {"qwen3b_local"}
        router = GatewayRouter(engine_available_fn=lambda eid: eid in available_set)
        candidates = router.select_candidates("chat_general")
        assert candidates == ["qwen3b_local"]

    def test_internet_required_no_internet(self):
        router = GatewayRouter(internet_check=lambda: "DOWN")
        candidates = router.select_candidates("premium_search")
        assert candidates == []

    def test_internet_required_with_internet(self):
        router = GatewayRouter(internet_check=lambda: "OK")
        candidates = router.select_candidates("premium_search")
        assert "perplexity_sonar_pro" in candidates

    def test_unknown_profile_falls_to_chat_general(self):
        router = GatewayRouter()
        candidates = router.select_candidates("nonexistent_profile")
        expected = list(SEED_ROUTING_RULES["chat_general"].candidate_models)
        assert candidates == expected


# ---------------------------------------------------------------------------
# GatewayRouter: apply_budgets
# ---------------------------------------------------------------------------

class TestApplyBudgets:
    def test_returns_override_for_known_profile(self):
        router = GatewayRouter()
        budget = router.apply_budgets("intent_detection_fast")
        assert budget.max_output_tokens == 128
        assert budget.timeout_ms == 800

    def test_returns_defaults_for_no_override(self):
        router = GatewayRouter()
        budget = router.apply_budgets("chat_general")
        assert budget == BudgetEnvelope()

    def test_deep_audit_expensive_budget(self):
        router = GatewayRouter()
        budget = router.apply_budgets("deep_audit")
        assert budget.max_output_tokens == 4096
        assert budget.max_cost_usd == 0.05


# ---------------------------------------------------------------------------
# GatewayRouter: choose_strategy
# ---------------------------------------------------------------------------

class TestChooseStrategy:
    def test_single(self):
        router = GatewayRouter()
        assert router.choose_strategy("intent_detection_fast") == "single"

    def test_fallback(self):
        router = GatewayRouter()
        assert router.choose_strategy("chat_general") == "fallback"

    def test_unknown_profile(self):
        router = GatewayRouter()
        assert router.choose_strategy("nonexistent") == "fallback"


# ---------------------------------------------------------------------------
# GatewayRouter: get_tool_policy
# ---------------------------------------------------------------------------

class TestGetToolPolicy:
    def test_read_only(self):
        router = GatewayRouter()
        policy = router.get_tool_policy("read_only")
        assert policy.allow_mutate is False

    def test_mutating_gated(self):
        router = GatewayRouter()
        policy = router.get_tool_policy("mutating_gated")
        assert policy.allow_mutate is True
        assert policy.require_user_ack is True

    def test_unknown_falls_to_read_only(self):
        router = GatewayRouter()
        policy = router.get_tool_policy("nonexistent")
        assert policy.policy_id == "read_only"


# ---------------------------------------------------------------------------
# Regression: fast intents never select expensive models
# ---------------------------------------------------------------------------

class TestFastIntentSafety:
    def test_seed_rules_are_safe(self):
        """All SEED_ROUTING_RULES for fast profiles must not include expensive providers."""
        for profile_id in _FAST_PROFILES:
            rule = SEED_ROUTING_RULES.get(profile_id)
            assert rule is not None, f"Missing rule for fast profile {profile_id}"
            for candidate in rule.candidate_models:
                assert candidate not in _EXPENSIVE_PROVIDERS, (
                    f"Fast profile {profile_id} includes expensive provider {candidate}"
                )

    def test_validate_fast_intent_safety(self):
        assert GatewayRouter.validate_fast_intent_safety(
            "intent_detection_fast", ["qwen3b_local"]
        ) is True
        assert GatewayRouter.validate_fast_intent_safety(
            "intent_detection_fast", ["qwen3b_local", "groq_booster"]
        ) is False
        # Non-fast profiles can use expensive
        assert GatewayRouter.validate_fast_intent_safety(
            "deep_audit", ["groq_booster"]
        ) is True


# ---------------------------------------------------------------------------
# Seed data consistency
# ---------------------------------------------------------------------------

class TestSeedConsistency:
    def test_all_profiles_have_rules(self):
        """Every profile referenced in SEED_TASK_PROFILES must have a routing rule."""
        for key, profile_id in SEED_TASK_PROFILES.items():
            assert profile_id in SEED_ROUTING_RULES, (
                f"Profile {profile_id} (from {key}) has no routing rule"
            )

    def test_all_tool_policies_exist(self):
        assert "read_only" in SEED_TOOL_POLICIES
        assert "mutating_gated" in SEED_TOOL_POLICIES


# ---------------------------------------------------------------------------
# Shadow hook in router.py
# ---------------------------------------------------------------------------

class TestShadowHookInRouter:
    """Test that the shadow hook in InferenceRouter is no-op by default,
    and correctly calls through when flags are on."""

    def test_shadow_disabled_by_default(self):
        """With default env (flags off), _run_shadow_hook does nothing."""
        # Ensure flags are off
        with patch.dict(os.environ, {
            "DENIS_ENABLE_INFERENCE_GATEWAY": "0",
            "DENIS_GATEWAY_SHADOW_MODE": "0",
        }):
            from denis_unified_v1.feature_flags import load_feature_flags
            load_feature_flags(force_reload=True)

            from denis_unified_v1.inference.router import InferenceRouter
            # Create minimal router (may fail on engine registry - that's OK, we mock)
            try:
                router = InferenceRouter.__new__(InferenceRouter)
                router.metrics = MagicMock()
                router._run_shadow_hook(
                    request_id="test-001",
                    legacy_provider="llamacpp",
                    legacy_model="local",
                )
                # Should NOT call metrics.emit_decision with shadow_comparison
                for call in router.metrics.emit_decision.call_args_list:
                    payload = call[0][1] if len(call[0]) > 1 else call[1].get("payload", {})
                    assert payload.get("mode") != "shadow_comparison"
            finally:
                load_feature_flags(force_reload=True)

    def test_shadow_enabled_logs_comparison(self):
        """With flags on, shadow hook logs to DecisionTrace and metrics."""
        with patch.dict(os.environ, {
            "DENIS_ENABLE_INFERENCE_GATEWAY": "1",
            "DENIS_GATEWAY_SHADOW_MODE": "1",
        }):
            from denis_unified_v1.feature_flags import load_feature_flags
            load_feature_flags(force_reload=True)

            try:
                from denis_unified_v1.inference.router import InferenceRouter

                router = InferenceRouter.__new__(InferenceRouter)
                router.metrics = MagicMock()

                with patch("denis_unified_v1.inference.router._emit_dt") as mock_dt:
                    router._run_shadow_hook(
                        request_id="test-002",
                        legacy_provider="llamacpp",
                        legacy_model="local",
                    )

                    # DecisionTrace should be called with SHADOW mode
                    if mock_dt is not None:
                        mock_dt.assert_called_once()
                        call_kwargs = mock_dt.call_args
                        assert call_kwargs[1]["mode"] == "SHADOW" or call_kwargs[0][1] == "SHADOW"

                    # Metrics should log shadow_comparison
                    router.metrics.emit_decision.assert_called()
                    payload = router.metrics.emit_decision.call_args[0][1]
                    assert payload["mode"] == "shadow_comparison"
                    assert "same_choice" in payload
                    assert "shadow_error" in payload
            finally:
                load_feature_flags(force_reload=True)

    def test_shadow_hook_error_does_not_propagate(self):
        """If shadow hook crashes, no exception escapes."""
        with patch.dict(os.environ, {
            "DENIS_ENABLE_INFERENCE_GATEWAY": "1",
            "DENIS_GATEWAY_SHADOW_MODE": "1",
        }):
            from denis_unified_v1.feature_flags import load_feature_flags
            load_feature_flags(force_reload=True)

            try:
                from denis_unified_v1.inference.router import InferenceRouter

                router = InferenceRouter.__new__(InferenceRouter)
                router.metrics = MagicMock()
                router.metrics.emit_decision.side_effect = RuntimeError("redis_down")

                with patch("denis_unified_v1.inference.router._GatewayRouter") as mock_gw:
                    mock_gw.side_effect = RuntimeError("gateway_broken")

                    # Should NOT raise
                    router._run_shadow_hook(
                        request_id="test-003",
                        legacy_provider="llamacpp",
                        legacy_model="local",
                    )
            finally:
                load_feature_flags(force_reload=True)


# ---------------------------------------------------------------------------
# Perplexity client/adapter (basic structure tests)
# ---------------------------------------------------------------------------

class TestPerplexityClient:
    def test_import(self):
        from denis_unified_v1.inference.perplexity_client import (
            PerplexityClient,
            PerplexitySearchAdapter,
        )
        client = PerplexityClient()
        adapter = PerplexitySearchAdapter(client)
        assert adapter.provider_name == "perplexity"

    def test_not_available_without_api_key(self):
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": ""}, clear=False):
            from denis_unified_v1.inference.perplexity_client import PerplexityClient
            client = PerplexityClient()
            # Manually set to empty for test
            client.api_key = ""
            assert client.is_available() is False

    def test_adapter_chat_mock_success(self):
        from denis_unified_v1.inference.perplexity_client import (
            PerplexityClient,
            PerplexitySearchAdapter,
        )
        client = MagicMock(spec=PerplexityClient)
        client.model = "sonar-pro"
        client.cost_factor = 0.80
        client.is_available.return_value = True
        client.generate = AsyncMock(return_value={
            "response": "Search result",
            "input_tokens": 100,
            "output_tokens": 50,
            "citations": ["https://example.com"],
            "raw": {},
        })
        adapter = PerplexitySearchAdapter(client)
        result = run(adapter.chat([{"role": "user", "content": "what is X?"}]))
        assert result.success is True
        assert result.provider == "perplexity"
        assert result.response == "Search result"
