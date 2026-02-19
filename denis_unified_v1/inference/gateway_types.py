"""Core types for the InferenceGateway.

Defines the contract between Track A (IntentSystem) and Track B (InferenceGateway).
All frozen dataclasses for immutability; mutable ones only where state tracking is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Budget & Policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BudgetEnvelope:
    """Per-request budget constraints."""
    max_input_tokens: int = 4096
    max_output_tokens: int = 512
    timeout_ms: int = 5000
    max_cost_usd: float = 0.01
    max_concurrency: int = 1


@dataclass(frozen=True)
class ToolPolicy:
    """What a request is allowed to do."""
    policy_id: str = "read_only"
    allow_read: bool = True
    allow_mutate: bool = False
    require_user_ack: bool = False
    blocked_tools: FrozenSet[str] = frozenset()


# ---------------------------------------------------------------------------
# Window state (mutable — tracks rolling usage)
# ---------------------------------------------------------------------------

@dataclass
class WindowState:
    """Rolling window quota state for a scope (tenant/bot/session)."""
    window_id: str
    scope: str
    window_seconds: int = 18000  # 5h
    tokens_used: int = 0
    tokens_limit: int = 500_000
    requests_used: int = 0
    requests_limit: int = 1000
    started_at: Optional[float] = None  # epoch; None = not started yet
    exhausted: bool = False


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskProfileRequest:
    """The contract between IntentSystem (Track A) and InferenceGateway (Track B).

    Track A produces this; Track B consumes it.
    While Track A is being migrated, seeds provide hardcoded mappings.
    """
    task_profile_id: str
    budgets: BudgetEnvelope = field(default_factory=BudgetEnvelope)
    tool_policy_id: str = "read_only"
    context_pack_ref: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider call result (mutable — filled during execution)
# ---------------------------------------------------------------------------

@dataclass
class ProviderCallResult:
    """Result from a single provider call."""
    provider: str
    model: str
    response: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd_estimated: float = 0.0
    raw: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    success: bool = True


# ---------------------------------------------------------------------------
# Inference result (the final output)
# ---------------------------------------------------------------------------

@dataclass
class InferenceResult:
    """Complete result from the InferenceGateway."""
    call: ProviderCallResult
    task_profile_id: str
    budget_envelope: BudgetEnvelope
    tool_policy: ToolPolicy
    window_state: Optional[WindowState] = None
    fallback_used: bool = False
    fallback_chain: List[str] = field(default_factory=list)
    strategy: str = "single"  # single | fallback | parallel_verify
    trace_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Routing types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoutingRule:
    """Maps a TaskProfile to candidate models and execution strategy."""
    rule_id: str
    task_profile_id: str
    candidate_models: Tuple[str, ...] = ()  # ordered by preference
    strategy: str = "single"  # single | fallback | parallel_verify
    budget_override: Optional[BudgetEnvelope] = None
    require_internet: bool = False


@dataclass
class SelectedModel:
    """The router's final decision."""
    engine_id: str
    model: str
    provider: str
    reason: str
    confidence: float = 0.5
    budget: BudgetEnvelope = field(default_factory=BudgetEnvelope)
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)
    window_state: Optional[WindowState] = None
