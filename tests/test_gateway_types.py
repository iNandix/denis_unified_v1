"""Tests for inference/gateway_types.py — PR1 core types."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError, asdict

from denis_unified_v1.inference.gateway_types import (
    BudgetEnvelope,
    InferenceResult,
    ProviderCallResult,
    RoutingRule,
    SelectedModel,
    TaskProfileRequest,
    ToolPolicy,
    WindowState,
)


# ---------------------------------------------------------------------------
# BudgetEnvelope
# ---------------------------------------------------------------------------

class TestBudgetEnvelope:
    def test_defaults(self):
        b = BudgetEnvelope()
        assert b.max_input_tokens == 4096
        assert b.max_output_tokens == 512
        assert b.timeout_ms == 5000
        assert b.max_cost_usd == 0.01
        assert b.max_concurrency == 1

    def test_frozen(self):
        b = BudgetEnvelope()
        with pytest.raises(FrozenInstanceError):
            b.max_output_tokens = 1024  # type: ignore[misc]

    def test_custom(self):
        b = BudgetEnvelope(max_output_tokens=2048, timeout_ms=15000, max_cost_usd=0.05)
        assert b.max_output_tokens == 2048
        assert b.timeout_ms == 15000

    def test_asdict_roundtrip(self):
        b = BudgetEnvelope(max_output_tokens=128, timeout_ms=800)
        d = asdict(b)
        assert d["max_output_tokens"] == 128
        b2 = BudgetEnvelope(**d)
        assert b == b2


# ---------------------------------------------------------------------------
# ToolPolicy
# ---------------------------------------------------------------------------

class TestToolPolicy:
    def test_read_only_default(self):
        tp = ToolPolicy()
        assert tp.policy_id == "read_only"
        assert tp.allow_read is True
        assert tp.allow_mutate is False
        assert tp.require_user_ack is False
        assert tp.blocked_tools == frozenset()

    def test_mutating_gated(self):
        tp = ToolPolicy(
            policy_id="mutating_gated",
            allow_mutate=True,
            require_user_ack=True,
        )
        assert tp.allow_mutate is True
        assert tp.require_user_ack is True

    def test_frozen(self):
        tp = ToolPolicy()
        with pytest.raises(FrozenInstanceError):
            tp.allow_mutate = True  # type: ignore[misc]

    def test_blocked_tools(self):
        tp = ToolPolicy(blocked_tools=frozenset({"rm_rf", "drop_db"}))
        assert "rm_rf" in tp.blocked_tools
        assert "safe_tool" not in tp.blocked_tools


# ---------------------------------------------------------------------------
# WindowState (mutable)
# ---------------------------------------------------------------------------

class TestWindowState:
    def test_defaults(self):
        ws = WindowState(window_id="w1", scope="tenant:test")
        assert ws.tokens_used == 0
        assert ws.tokens_limit == 500_000
        assert ws.started_at is None
        assert ws.exhausted is False

    def test_mutable(self):
        ws = WindowState(window_id="w1", scope="tenant:test")
        ws.tokens_used = 100
        ws.exhausted = True
        assert ws.tokens_used == 100
        assert ws.exhausted is True

    def test_exhausted_logic(self):
        ws = WindowState(
            window_id="w1", scope="bot:x",
            tokens_used=500_001, tokens_limit=500_000,
        )
        ws.exhausted = ws.tokens_used > ws.tokens_limit
        assert ws.exhausted is True


# ---------------------------------------------------------------------------
# TaskProfileRequest
# ---------------------------------------------------------------------------

class TestTaskProfileRequest:
    def test_minimal(self):
        req = TaskProfileRequest(task_profile_id="chat_general")
        assert req.task_profile_id == "chat_general"
        assert req.tool_policy_id == "read_only"
        assert isinstance(req.budgets, BudgetEnvelope)
        assert req.labels == {}

    def test_full(self):
        req = TaskProfileRequest(
            task_profile_id="premium_search",
            budgets=BudgetEnvelope(max_output_tokens=1024, timeout_ms=10000),
            tool_policy_id="read_only",
            context_pack_ref="artifact:abc123",
            labels={"intent": "search", "phase": "premium"},
        )
        assert req.budgets.max_output_tokens == 1024
        assert req.labels["intent"] == "search"

    def test_frozen(self):
        req = TaskProfileRequest(task_profile_id="x")
        with pytest.raises(FrozenInstanceError):
            req.task_profile_id = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProviderCallResult
# ---------------------------------------------------------------------------

class TestProviderCallResult:
    def test_success(self):
        r = ProviderCallResult(
            provider="llamacpp", model="local",
            response="Hello", input_tokens=10, output_tokens=5,
            latency_ms=42.0, cost_usd_estimated=0.0001,
        )
        assert r.success is True
        assert r.error is None
        assert r.response == "Hello"

    def test_error(self):
        r = ProviderCallResult(
            provider="groq", model="llama-3.1-70b",
            error="groq_http_429", success=False,
        )
        assert r.success is False
        assert r.error == "groq_http_429"
        assert r.response == ""


# ---------------------------------------------------------------------------
# InferenceResult
# ---------------------------------------------------------------------------

class TestInferenceResult:
    def test_single_no_fallback(self):
        call = ProviderCallResult(provider="llamacpp", model="local", response="ok")
        result = InferenceResult(
            call=call,
            task_profile_id="chat_general",
            budget_envelope=BudgetEnvelope(),
            tool_policy=ToolPolicy(),
        )
        assert result.fallback_used is False
        assert result.strategy == "single"
        assert result.fallback_chain == []

    def test_fallback(self):
        call = ProviderCallResult(provider="groq", model="llama-3.1-70b", response="ok")
        result = InferenceResult(
            call=call,
            task_profile_id="codecraft_generate",
            budget_envelope=BudgetEnvelope(),
            tool_policy=ToolPolicy(),
            fallback_used=True,
            fallback_chain=["qwen_coder7b_local", "groq_booster"],
            strategy="fallback",
        )
        assert result.fallback_used is True
        assert len(result.fallback_chain) == 2


# ---------------------------------------------------------------------------
# RoutingRule
# ---------------------------------------------------------------------------

class TestRoutingRule:
    def test_basic(self):
        rule = RoutingRule(
            rule_id="rr_01",
            task_profile_id="intent_detection_fast",
            candidate_models=("qwen3b_local", "qwen_coder7b_local"),
            strategy="single",
        )
        assert rule.candidate_models[0] == "qwen3b_local"
        assert rule.require_internet is False

    def test_frozen(self):
        rule = RoutingRule(rule_id="rr_01", task_profile_id="x")
        with pytest.raises(FrozenInstanceError):
            rule.strategy = "fallback"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SelectedModel
# ---------------------------------------------------------------------------

class TestSelectedModel:
    def test_basic(self):
        sm = SelectedModel(
            engine_id="qwen3b_local",
            model="qwen2.5-3b",
            provider="llamacpp",
            reason="local_first",
        )
        assert sm.confidence == 0.5
        assert isinstance(sm.budget, BudgetEnvelope)
        assert isinstance(sm.tool_policy, ToolPolicy)
