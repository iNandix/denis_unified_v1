"""Schemas v1 for Tool Catalog - ML-friendly, versioned."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


CapabilityType = Literal[
    "action_tool", "workflow", "macro", "local_responder", "booster"
]
CapabilitySafety = Literal["read_only", "mutating", "mixed"]
CapabilityAvailability = Literal["local", "internet", "hybrid"]
ExistsVsCreate = Literal["exists", "compose", "create", "clarify"]
ModeEnum = Literal["clarify", "actions_plan", "direct_local", "direct_boosted"]


class ToolCapabilityV1(BaseModel):
    """How Denis describes a capability (tool/action/workflow/local responder)."""

    model_config = {"extra": "forbid"}

    schema_version: Literal["tool_capability_v1"] = "tool_capability_v1"

    name: str
    type: CapabilityType

    description: str
    intents: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    safety: CapabilitySafety = "read_only"
    availability: CapabilityAvailability = "local"

    requires_internet: bool = False
    requires_boosters: bool = False

    typical_evidence: List[str] = Field(default_factory=list)
    params_hint: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class MatchV1(BaseModel):
    """Single tool match from catalog lookup."""

    model_config = {"extra": "forbid"}

    name: str
    score: float
    reason_codes: List[str] = Field(default_factory=list)
    matched_intent: Optional[str] = None
    matched_tags: List[str] = Field(default_factory=list)


class LookupResultV1(BaseModel):
    """Result of catalog lookup - ML-ready."""

    model_config = {"extra": "forbid"}

    schema_version: Literal["tool_lookup_result_v1"] = "tool_lookup_result_v1"

    request_id: str
    intent: str
    entities: Dict[str, Any] = Field(default_factory=dict)

    matched_tools: List[MatchV1] = Field(default_factory=list)
    missing_capabilities: List[str] = Field(default_factory=list)

    recommended_mode: ModeEnum
    exists_vs_create: ExistsVsCreate

    reason_codes: List[str] = Field(default_factory=list)

    features: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)
