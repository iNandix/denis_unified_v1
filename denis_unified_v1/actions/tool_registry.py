"""
Tool Registry - Graph-centric tool discovery and execution.

Provides tool lookup, execution, and result persistence all via Neo4j graph.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
from dataclasses import dataclass

from denis_unified_v1.actions.graph_intent_resolver import _get_neo4j_driver

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Tool definition from graph."""

    name: str
    tool_id: str
    category: str
    status: str
    risk_level: str
    endpoint: Optional[str] = None
    method: Optional[str] = None
    timeout_s: int = 30
    retries: int = 0


def get_tool_definition(tool_name: str) -> Optional[ToolDefinition]:
    """Get tool definition from graph."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    if not flags.tool_executor_uses_graph:
        return None

    driver = _get_neo4j_driver()
    if not driver:
        return None

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (t:Tool {name: $name})
                RETURN t.name as name, 
                       t.tool_id as tool_id, 
                       t.category as category,
                       t.status as status,
                       t.risk_level as risk_level,
                       t.endpoint as endpoint,
                       t.method as method,
                       t.timeout_s as timeout_s,
                       t.retries as retries
            """,
                name=tool_name,
            )

            record = result.single()
            if record:
                return ToolDefinition(
                    name=record["name"],
                    tool_id=record["tool_id"] or "",
                    category=record["category"] or "",
                    status=record["status"] or "unknown",
                    risk_level=record["risk_level"] or "normal",
                    endpoint=record.get("endpoint"),
                    method=record.get("method"),
                    timeout_s=record.get("timeout_s", 30),
                    retries=record.get("retries", 0),
                )
    except Exception as e:
        logger.warning(f"Failed to get tool definition from graph: {e}")

    return None


def list_active_tools() -> list[ToolDefinition]:
    """List all active tools from graph."""
    from denis_unified_v1.feature_flags import load_feature_flags

    flags = load_feature_flags()

    if not flags.tool_executor_uses_graph:
        return []

    driver = _get_neo4j_driver()
    if not driver:
        return []

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Tool)
                WHERE t.status = 'active'
                RETURN t.name as name,
                       t.tool_id as tool_id,
                       t.category as category,
                       t.status as status,
                       t.risk_level as risk_level
                ORDER BY t.name
            """)

            return [
                ToolDefinition(
                    name=record["name"],
                    tool_id=record["tool_id"] or "",
                    category=record["category"] or "",
                    status=record["status"],
                    risk_level=record["risk_level"] or "normal",
                )
                for record in result
            ]
    except Exception as e:
        logger.warning(f"Failed to list tools from graph: {e}")
        return []


def execute_tool(
    tool_name: str,
    args: dict,
    context: dict,
) -> dict[str, Any]:
    """
    Execute tool via graph registry.

    Steps:
    1. Lookup tool in graph
    2. Check approval/risk
    3. Execute with timeout
    4. Persist result to graph
    """
    from denis_unified_v1.actions.tool_approval import (
        check_tool_approval,
        ApprovalDecision,
    )

    # Get tool definition
    tool_def = get_tool_definition(tool_name)
    if not tool_def:
        return {"success": False, "error": f"Tool {tool_name} not found in graph"}

    # Check approval
    confidence_band = context.get("confidence_band", "medium")
    is_mutating = tool_def.risk_level not in ("safe", "read")

    approval = check_tool_approval(tool_name, confidence_band, is_mutating)
    if approval == ApprovalDecision.REQUIRES_HUMAN:
        return {
            "success": False,
            "error": "Requires human approval",
            "requires_approval": True,
        }
    if approval == ApprovalDecision.BLOCKED:
        return {"success": False, "error": "Tool execution blocked", "blocked": True}

    # Execute (placeholder - real execution would use tool's endpoint)
    start_ts = time.time()
    result = {
        "success": True,
        "tool": tool_name,
        "args": args,
        "execution_time_ms": 0,
    }

    # Persist execution result to graph
    try:
        driver = _get_neo4j_driver()
        if driver:
            with driver.session() as session:
                session.run(
                    """
                    MATCH (t:Tool {name: $tool_name})
                    CREATE (e:ToolExecution {
                        tool: $tool_name,
                        args: $args,
                        success: $success,
                        execution_time_ms: $exec_time,
                        executed_at: datetime(),
                        request_id: $request_id
                    })
                """,
                    tool_name=tool_name,
                    args=str(args),
                    success=result["success"],
                    exec_time=result["execution_time_ms"],
                    request_id=context.get("request_id", "unknown"),
                )
    except Exception as e:
        logger.warning(f"Failed to persist tool execution: {e}")

    return result


def get_tools_by_category(category: str) -> list[ToolDefinition]:
    """Get tools filtered by category."""
    all_tools = list_active_tools()
    return [t for t in all_tools if t.category == category]
