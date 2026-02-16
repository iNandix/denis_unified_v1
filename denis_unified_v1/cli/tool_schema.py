"""Schema for Denis Code CLI tool calls."""

import json
import re
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from denis_unified_v1.cognition.legacy_tools_v2 import get_tool_registry_v2


class ToolCall(BaseModel):
    tool: str = Field(..., description="Tool name (e.g., read_file, run_command)")
    args: Dict[str, Any] = Field(..., description="Tool arguments")
    rationale: str = Field(..., description="Why this tool is needed")
    risk_level: str = Field(..., description="Risk level: low, medium, high")
    tool_call_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for audit")


class DenisResponse(BaseModel):
    assistant_message: str = Field(..., description="Message to show to user")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tools to execute")
    done: bool = Field(False, description="Whether the task is complete")


def extract_json(text: str) -> Optional[str]:
    """Extract JSON from text robustly."""
    # Try full text
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text

    # Find JSON block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)

    return None


def validate_response(text: str) -> DenisResponse:
    """Parse and validate Denis response robustly."""
    json_str = extract_json(text)
    if not json_str:
        raise ValueError("No JSON found in response")

    try:
        data = json.loads(json_str)
        resp = DenisResponse(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Invalid JSON/schema: {e}")

    # Extra validations
    registry = get_tool_registry_v2()
    for tc in resp.tool_calls:
        if tc.tool not in registry:
            raise ValueError(f"Unknown tool: {tc.tool}")
        # Check risk_level matches meta (mock for now)
        meta = getattr(registry[tc.tool], "meta", None)
        if meta and getattr(meta, "risk", "") != tc.risk_level:
            # Correct it
            tc.risk_level = getattr(meta, "risk", "high")

    return resp


def check_tool_approval_from_graph(tool_call: ToolCall) -> Dict[str, Any]:
    """Check approval from tool meta (graph-based)."""
    registry = get_tool_registry_v2()
    meta = getattr(registry.get(tool_call.tool), "meta", None)
    if not meta:
        return {"approved": False, "requires_confirmation": True, "reason": "no meta"}

    requires = getattr(meta, "requires_approval", True)  # Default True if missing
    if not requires:
        return {"approved": True, "requires_confirmation": False}

    # Requires approval: ask confirmation
    return {"approved": False, "requires_confirmation": True, "reason": f"tool requires approval (risk: {meta.risk})"}
