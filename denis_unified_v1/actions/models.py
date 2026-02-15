from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


# -------------------------
# Enums / Literals
# -------------------------

class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class StepStatus(str, Enum):
    ok = "ok"
    failed = "failed"
    skipped = "skipped"


class StopOp(str, Enum):
    # numeric ops
    eq = "eq"
    ne = "ne"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    # boolean ops (value should be bool)
    is_true = "is_true"
    is_false = "is_false"
    # membership
    contains = "contains"
    not_contains = "not_contains"
    # existence
    exists = "exists"
    not_exists = "not_exists"


# -------------------------
# Tool calls
# -------------------------

class ToolCall(BaseModel):
    """
    A declarative tool call for the executor.
    The executor is responsible for mapping name -> actual function.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Tool identifier, e.g., run_command, list_files, grep_search")
    args: Dict[str, Any] = Field(default_factory=dict)


# -------------------------
# Stop condition mini DSL
# -------------------------

class StopCondition(BaseModel):
    """
    Mini DSL evaluated against a StepResult 'facts' dict.

    Example:
      {"key":"exit_code","op":"eq","value":0}
      {"key":"tests_run","op":"gt","value":0}
      {"key":"no_test_files_found","op":"is_true"}
    """
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., description="Fact key produced by executor, e.g. exit_code, disk_usage_pct")
    op: StopOp
    value: Optional[Any] = None

    @model_validator(mode="after")
    def _validate_value(self):
        if self.op in {StopOp.is_true, StopOp.is_false, StopOp.exists, StopOp.not_exists}:
            # value not required for these ops
            return self
        if self.value is None:
            raise ValueError(f"value is required for op={self.op}")
        return self


# -------------------------
# Step definition
# -------------------------

class ActionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    description: str

    # Whether the step is read-only (must not mutate repository/system state).
    read_only: bool = True

    tool_calls: List[ToolCall] = Field(default_factory=list)

    # Evidence keys expected to be present in StepResult.facts or evidence_paths.
    evidence_required: List[str] = Field(default_factory=list)

    # Conditions that stop the plan early (success/stop) OR stop the step (fail-fast) depending on semantics used by executor.
    # Recommended semantics:
    # - if any condition matches and is marked as "success_stop" by planner => plan can stop as success
    # - if any condition matches and is marked as "fail_stop" => plan stops as failed
    #
    # To keep v1 simple: treat stop_if as "stop plan when condition matches", and rely on reason_code.
    stop_if: List[StopCondition] = Field(default_factory=list)

    # Optional: step-level on_failure policy
    on_failure: Literal["abort", "ask", "fallback"] = "abort"


# -------------------------
# Candidate plan
# -------------------------

class ActionPlanCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    intent: str

    risk_level: RiskLevel = RiskLevel.low
    estimated_tokens: int = 0

    # Derived flags for selection and policy
    is_mutating: bool = False
    requires_internet: bool = False

    steps: List[ActionStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_mutating(self):
        # If any step is not read_only, the plan is mutating.
        mut = any(not s.read_only for s in self.steps)
        if mut and not self.is_mutating:
            self.is_mutating = True
        return self


# -------------------------
# Intent v1
# -------------------------

class Intent_v1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    confidence: float
    confidence_band: Literal["low", "medium", "high"]
    tone: Optional[str] = None
    implicit_request: bool = False
    secondary_intents: List[str] = Field(default_factory=list)
    sources: Dict[str, Any] = Field(default_factory=dict)
    reason_codes: List[str] = Field(default_factory=list)


# -------------------------
# Plan set (the multi-plan output)
# -------------------------

class ActionPlanSet(BaseModel):
    """
    Holds multiple candidate plans and the selected plan id.
    """
    model_config = ConfigDict(extra="forbid")

    kind: str = "action_plan_snapshot"
    ts_utc: str
    request_id: str
    intent: Dict[str, Any]  # From Intent_v1.model_dump()

    candidates: List[Dict[str, Any]]  # Simplified for snapshot
    selected_candidate_id: str

    selection_reason_codes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_selected(self):
        ids = {c["candidate_id"] for c in self.candidates}
        if self.selected_candidate_id not in ids:
            raise ValueError("selected_candidate_id must be one of candidates[].candidate_id")
        return self
