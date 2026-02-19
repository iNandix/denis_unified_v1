"""Graph-driven router for InferenceGateway.

Phase 1: hardcoded seed maps (TaskProfiles, RoutingRules, ToolPolicies).
Phase 2 (PR5): Neo4j resolution when Track A delivers graph-based mapping.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .gateway_types import BudgetEnvelope, RoutingRule, ToolPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Seed data — hardcoded until Track A delivers graph-based mapping
# ---------------------------------------------------------------------------

SEED_ROUTING_RULES: Dict[str, RoutingRule] = {
    "intent_detection_fast": RoutingRule(
        rule_id="rr_01",
        task_profile_id="intent_detection_fast",
        candidate_models=("qwen3b_local", "qwen_coder7b_local"),
        strategy="single",
        require_internet=False,
        budget_override=BudgetEnvelope(max_output_tokens=128, timeout_ms=800),
    ),
    "chat_general": RoutingRule(
        rule_id="rr_02",
        task_profile_id="chat_general",
        candidate_models=("qwen_coder7b_local", "qwen3b_local", "groq_booster"),
        strategy="fallback",
    ),
    "codecraft_generate": RoutingRule(
        rule_id="rr_03",
        task_profile_id="codecraft_generate",
        candidate_models=("qwen_coder7b_local", "groq_booster", "openrouter_booster"),
        strategy="fallback",
        budget_override=BudgetEnvelope(max_output_tokens=2048, timeout_ms=15000),
    ),
    "premium_search": RoutingRule(
        rule_id="rr_04",
        task_profile_id="premium_search",
        candidate_models=("perplexity_sonar_pro",),
        strategy="single",
        require_internet=True,
        budget_override=BudgetEnvelope(max_output_tokens=1024, timeout_ms=10000),
    ),
    "pro_search_prepare_fast": RoutingRule(
        rule_id="rr_05",
        task_profile_id="pro_search_prepare_fast",
        candidate_models=("qwen3b_local",),
        strategy="single",
        budget_override=BudgetEnvelope(max_output_tokens=600, timeout_ms=800),
    ),
    "deep_audit": RoutingRule(
        rule_id="rr_06",
        task_profile_id="deep_audit",
        candidate_models=("qwen_coder7b_local", "groq_booster", "claude_booster"),
        strategy="fallback",
        budget_override=BudgetEnvelope(max_output_tokens=4096, timeout_ms=30000, max_cost_usd=0.05),
    ),
    "tool_runner_read_only": RoutingRule(
        rule_id="rr_07",
        task_profile_id="tool_runner_read_only",
        candidate_models=("qwen3b_local",),
        strategy="single",
        budget_override=BudgetEnvelope(max_output_tokens=256, timeout_ms=2000),
    ),
    "summarize_artifact": RoutingRule(
        rule_id="rr_08",
        task_profile_id="summarize_artifact",
        candidate_models=("qwen_coder7b_local", "qwen3b_local"),
        strategy="fallback",
        budget_override=BudgetEnvelope(max_output_tokens=1024, timeout_ms=8000),
    ),
    "chat_code": RoutingRule(
        rule_id="rr_09",
        task_profile_id="chat_code",
        candidate_models=("qwen_coder7b_local", "groq_booster"),
        strategy="fallback",
        budget_override=BudgetEnvelope(max_output_tokens=1024, timeout_ms=10000),
    ),
}

# Intent:phase → task_profile_id mapping
SEED_TASK_PROFILES: Dict[str, str] = {
    "chat_general:*": "chat_general",
    "greeting:*": "intent_detection_fast",
    "repo_summary:shallow": "pro_search_prepare_fast",
    "repo_summary:deep": "deep_audit",
    "search:premium": "premium_search",
    "code_generate:*": "codecraft_generate",
    "tool_run:*": "tool_runner_read_only",
    "summarize:*": "summarize_artifact",
    "code_review:*": "chat_code",
    "code_explain:*": "chat_code",
}

SEED_TOOL_POLICIES: Dict[str, ToolPolicy] = {
    "read_only": ToolPolicy(policy_id="read_only"),
    "mutating_gated": ToolPolicy(
        policy_id="mutating_gated",
        allow_mutate=True,
        require_user_ack=True,
    ),
}

# Expensive provider ids that fast intents must never use
_EXPENSIVE_PROVIDERS = frozenset({
    "groq_booster", "openrouter_booster", "claude_booster", "perplexity_sonar_pro",
})
_FAST_PROFILES = frozenset({
    "intent_detection_fast", "pro_search_prepare_fast", "tool_runner_read_only",
})


# ---------------------------------------------------------------------------
# GatewayRouter
# ---------------------------------------------------------------------------

class GatewayRouter:
    """Seed-based router. Resolves TaskProfile → candidates + budgets + strategy.

    In Phase 2 (PR5), this will query Neo4j for resolution when feature flag is on.
    """

    def __init__(
        self,
        internet_check: Any = None,
        engine_available_fn: Any = None,
    ) -> None:
        self._internet_check = internet_check  # callable() -> "OK"|"DOWN"
        self._engine_available = engine_available_fn  # callable(engine_id) -> bool

    def resolve_task_profile(
        self,
        intent: str,
        phase: str = "*",
        ctx: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Map intent+phase to task_profile_id using seed map."""
        # Try exact match first
        key = f"{intent}:{phase}"
        if key in SEED_TASK_PROFILES:
            return SEED_TASK_PROFILES[key]
        # Try wildcard
        wildcard_key = f"{intent}:*"
        if wildcard_key in SEED_TASK_PROFILES:
            return SEED_TASK_PROFILES[wildcard_key]
        # Default
        return "chat_general"

    def select_candidates(
        self,
        task_profile_id: str,
        ctx: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Ordered list of engine_ids for this profile, filtered by availability."""
        rule = SEED_ROUTING_RULES.get(task_profile_id)
        if rule is None:
            rule = SEED_ROUTING_RULES["chat_general"]

        candidates = list(rule.candidate_models)

        # Filter internet-required engines if offline
        if rule.require_internet and not self._is_internet_ok():
            return []

        # Filter unavailable engines
        if self._engine_available:
            candidates = [c for c in candidates if self._engine_available(c)]

        return candidates

    def apply_budgets(
        self,
        task_profile_id: str,
        ctx: Optional[Dict[str, Any]] = None,
    ) -> BudgetEnvelope:
        """Return budget envelope for the task profile."""
        rule = SEED_ROUTING_RULES.get(task_profile_id)
        if rule and rule.budget_override:
            return rule.budget_override
        return BudgetEnvelope()  # defaults

    def choose_strategy(self, task_profile_id: str) -> str:
        """Return execution strategy: single | fallback | parallel_verify."""
        rule = SEED_ROUTING_RULES.get(task_profile_id)
        if rule:
            return rule.strategy
        return "fallback"

    def get_tool_policy(self, policy_id: str) -> ToolPolicy:
        """Resolve ToolPolicy by id."""
        return SEED_TOOL_POLICIES.get(policy_id, SEED_TOOL_POLICIES["read_only"])

    def _is_internet_ok(self) -> bool:
        if self._internet_check:
            try:
                return self._internet_check() == "OK"
            except Exception:
                return False
        return False

    # ------------------------------------------------------------------
    # Safety: regression guard
    # ------------------------------------------------------------------

    @staticmethod
    def validate_fast_intent_safety(task_profile_id: str, candidates: List[str]) -> bool:
        """Fast intents must NEVER select expensive providers."""
        if task_profile_id in _FAST_PROFILES:
            for c in candidates:
                if c in _EXPENSIVE_PROVIDERS:
                    return False
        return True
