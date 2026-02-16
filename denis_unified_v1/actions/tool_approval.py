"""
Tool Approval Engine - Graph-centric approval decision logic.

Contract: L3.METACOGNITION.HUMAN_APPROVAL_FOR_GROWTH
"""

from __future__ import annotations

import logging
from typing import Optional
from enum import Enum

from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

logger = logging.getLogger(__name__)


class ApprovalDecision(Enum):
    APPROVED = "approved"
    REQUIRES_HUMAN = "requires_human"
    BLOCKED = "blocked"


# Risk thresholds - could also be stored in graph
HIGH_RISK_TOOLS = frozenset(
    {
        "Reboot System",
        "Deploy Code",
        "Delete File",
        "Drop Database",
        "Destroy Resource",
        "Force Push",
    }
)

MEDIUM_RISK_TOOLS = frozenset(
    {
        "Execute SSH Command",
        "Restart Service",
        "Write File",
        "Edit File",
        "git commit",
        "git push",
    }
)


def check_tool_approval(
    tool_name: str,
    confidence_band: str,
    is_mutating: bool,
) -> ApprovalDecision:
    """
    Check if a tool execution requires human approval.

    Rules:
    - Read-only tools: never require approval
    - High risk (from graph): always require approval
    - Medium risk + low confidence: require approval
    - Graph-only mode: fail if no data
    """
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    # Read-only never needs approval
    if not is_mutating:
        return ApprovalDecision.APPROVED

    driver = _get_neo4j_driver()

    if flags.approval_uses_graph and driver:
        try:
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (t:Tool {name: $tool_name})
                    RETURN t.risk_level as risk_level, t.requires_approval as requires_approval
                """,
                    tool_name=tool_name,
                )

                record = result.single()
                if record:
                    risk_level = record.get("risk_level", "normal")
                    requires_approval = record.get("requires_approval", False)

                    # Explicit flag on tool
                    if requires_approval:
                        return ApprovalDecision.REQUIRES_HUMAN

                    # Risk-based decision
                    if risk_level in ("high", "critical"):
                        return ApprovalDecision.REQUIRES_HUMAN

                    if risk_level == "medium":
                        if confidence_band in ("low", "medium"):
                            return ApprovalDecision.REQUIRES_HUMAN

                    return ApprovalDecision.APPROVED
        except Exception as e:
            logger.warning(f"Graph approval check failed: {e}")

    # Fallback: use hardcoded lists
    if tool_name in HIGH_RISK_TOOLS:
        return ApprovalDecision.REQUIRES_HUMAN

    if tool_name in MEDIUM_RISK_TOOLS:
        if confidence_band in ("low", "medium"):
            return ApprovalDecision.REQUIRES_HUMAN

    # Graph-only mode
    if flags.graph_only and flags.approval_uses_graph:
        logger.error(f"GRAPH_ONLY: Cannot determine approval for {tool_name}")
        return ApprovalDecision.BLOCKED

    return ApprovalDecision.APPROVED


def check_action_approval(
    action_id: str,
    context: dict,
) -> ApprovalDecision:
    """Check approval for an action (higher-level operation)."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    driver = _get_neo4j_driver()

    if flags.approval_uses_graph and driver:
        try:
            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (a:Action {id: $action_id})
                    RETURN a.risk_level as risk_level, a.blocked_if as blocked_if
                """,
                    action_id=action_id,
                )

                record = result.single()
                if record:
                    risk_level = record.get("risk_level", "low")
                    blocked_if = record.get("blocked_if", [])

                    # Check blocking conditions
                    if blocked_if:
                        for condition in blocked_if:
                            if context.get(condition):
                                return ApprovalDecision.BLOCKED

                    if risk_level in ("high", "critical"):
                        return ApprovalDecision.REQUIRES_HUMAN

                    return ApprovalDecision.APPROVED
        except Exception as e:
            logger.warning(f"Graph action approval check failed: {e}")

    return ApprovalDecision.APPROVED
