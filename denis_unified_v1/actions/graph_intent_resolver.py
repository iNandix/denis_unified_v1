"""
GraphIntentResolver - Grafocentric plan generation from Neo4j.

Replaces hardcoded intent→plan mappings with live Neo4j queries:
  Intent -[:ACTIVATES]-> Tool -[:EXECUTES]-> Action
  Intent -[:PREFERS_ENGINE]-> Engine
  NeuroLayer -[:PROCESSES]-> Intent

Falls back to legacy planner if Neo4j is unavailable.
Connection is lazy with a 2s timeout — never blocks tests or startup.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

from denis_unified_v1.actions.models import (
    ActionPlanCandidate,
    ActionStep,
    Intent_v1,
    RiskLevel,
    StopCondition,
    StopOp,
    ToolCall,
)

logger = logging.getLogger(__name__)

# Tool→risk classification
_MUTATING_TOOLS = frozenset(
    {
        "file_write",
        "edit_file",
        "bash_execute",
        "execute_bash",
        "python_exec",
        "python_execute",
        "docker_exec",
        "ssh_exec",
        "git",
        "git_exec",
        "ha_control",
        "Deploy Code",
        "Reboot System",
        "Restart Service",
    }
)

_READ_ONLY_TOOLS = frozenset(
    {
        "file_read",
        "read_file",
        "grep_search",
        "code_search",
        "glob_files",
        "list_directory",
        "rag_query",
        "neo4j_query",
        "web_fetch",
        "search",
        "ha_query",
        "smx_response",
        "smx_fast_check",
        "smx_intent",
        "smx_tokenize",
        "embed_text",
        "stt_transcribe",
        "voice_transcribe",
        "tts_synthesize",
        "voice_synthesize",
    }
)


# ---------------------------------------------------------------------------
# Lazy singleton driver — never created at import time, 2s connect timeout
# ---------------------------------------------------------------------------
_driver = None
_driver_lock = threading.Lock()


def _get_neo4j_driver():
    """Get or create a shared Neo4j driver (lazy, 2s timeout)."""
    global _driver
    if _driver is not None:
        return _driver

    with _driver_lock:
        # Double-check after acquiring lock
        if _driver is not None:
            return _driver
        try:
            from neo4j import GraphDatabase

            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS")
            if not password:
                if os.getenv("DENIS_DEV") == "1":
                    password = "neo4j"
                else:
                    logger.warning(
                        "NEO4J_PASSWORD/NEO4J_PASS missing; graph disabled (fallback legacy)."
                    )
                    return None
            _driver = GraphDatabase.driver(
                uri,
                auth=(user, password),
                connection_timeout=2,
                max_connection_pool_size=5,
            )
            return _driver
        except Exception as e:
            logger.warning("Neo4j driver creation failed: %s", e)
            return None


def _is_tool_read_only(tool_name: str) -> bool:
    if tool_name in _MUTATING_TOOLS:
        return False
    if tool_name in _READ_ONLY_TOOLS:
        return True
    return True  # Default: assume read-only for safety


def _tool_risk_level(tool_name: str) -> RiskLevel:
    high_risk = {
        "bash_execute",
        "execute_bash",
        "python_exec",
        "python_execute",
        "docker_exec",
        "ssh_exec",
        "Reboot System",
        "Deploy Code",
    }
    medium_risk = {
        "file_write",
        "edit_file",
        "git",
        "git_exec",
        "ha_control",
        "Restart Service",
    }
    if tool_name in high_risk:
        return RiskLevel.high
    if tool_name in medium_risk:
        return RiskLevel.medium
    return RiskLevel.low


def resolve_from_graph(intent_name: str) -> Optional[dict[str, Any]]:
    """
    Query Neo4j for the full intent→tool→action chain.

    Returns dict with keys: intent, intent_desc, tools, actions,
    preferred_engine, neuro_layers.  Or None if Neo4j unavailable / empty.
    """
    driver = _get_neo4j_driver()
    if not driver:
        return None

    try:
        db = os.getenv("NEO4J_DATABASE", None)
        session_kwargs = {"database": db} if db else {}
        with driver.session(**session_kwargs) as session:
            result = session.run(
                """
                MATCH (i:Intent {name: $intent_name})-[act:ACTIVATES]->(t:Tool)
                OPTIONAL MATCH (t)-[:EXECUTES]->(a:Action)
                OPTIONAL MATCH (i)-[pe:PREFERS_ENGINE]->(e:Engine)
                OPTIONAL MATCH (nl:NeuroLayer)-[:PROCESSES]->(i)
                RETURN i.name        AS intent,
                       i.description AS intent_desc,
                       collect(DISTINCT {
                           name: t.name,
                           priority: act.priority,
                           confidence_min: act.confidence_min
                       }) AS tools,
                       collect(DISTINCT {
                           id: a.id,
                           risk_level: a.risk_level,
                           category: a.category
                       }) AS actions,
                       collect(DISTINCT {
                           engine_name: e.name,
                           endpoint: e.endpoint,
                           model: e.model,
                           status: e.status,
                           reason: pe.reason
                       }) AS engines,
                       collect(DISTINCT {
                           code: nl.code,
                           name: nl.name,
                           layer: nl.layer
                       }) AS neuro_layers
            """,
                intent_name=intent_name,
            )

            record = result.single()
            if not record or not record["tools"]:
                return None

            # Filter out null entries from OPTIONAL MATCHes
            tools = [t for t in record["tools"] if t["name"] is not None]
            actions = [a for a in record["actions"] if a["id"] is not None]
            engines = [e for e in record["engines"] if e["engine_name"] is not None]
            neuro_layers = [
                nl for nl in record["neuro_layers"] if nl["code"] is not None
            ]

            # Deduplicate tools by name, keep lowest priority (= highest importance)
            seen_tools: dict[str, dict] = {}
            for t in tools:
                name = t["name"]
                if name not in seen_tools or t.get("priority", 99) < seen_tools[
                    name
                ].get("priority", 99):
                    seen_tools[name] = t
            tools = sorted(
                seen_tools.values(), key=lambda x: (x.get("priority", 99), x["name"])
            )

            # Pick preferred engine (first active one, then any)
            preferred_engine = None
            for e in engines:
                if e.get("status") == "active":
                    preferred_engine = e
                    break
            if not preferred_engine and engines:
                preferred_engine = engines[0]

            return {
                "intent": record["intent"],
                "intent_desc": record["intent_desc"],
                "tools": tools,
                "actions": actions,
                "preferred_engine": preferred_engine,
                "neuro_layers": neuro_layers,
            }
    except Exception as e:
        logger.warning("Neo4j graph query failed for '%s': %s", intent_name, e)
        return None
    # NOTE: driver is a shared singleton — do NOT close it here.


def generate_candidate_plans_from_graph(
    intent_v1: Intent_v1,
) -> list[ActionPlanCandidate]:
    """
    Generate candidate plans by querying Neo4j graph.

    Always generates 2 candidates:
    - Plan A: Read-only (safe, low risk)
    - Plan B: Full execution (may include mutating steps)

    Returns empty list (not legacy fallback) when graph is empty.
    The caller (planner.py) is responsible for the legacy fallback.
    """
    graph_data = resolve_from_graph(intent_v1.intent)

    if not graph_data or not graph_data["tools"]:
        return []  # Let the caller decide fallback

    tools = graph_data["tools"]
    intent_name = graph_data["intent"]

    # Separate read-only and mutating tools
    ro_tools = [t for t in tools if _is_tool_read_only(t["name"])]
    mut_tools = [t for t in tools if not _is_tool_read_only(t["name"])]

    # Plan A: Read-only (always generated)
    plan_a_steps = []
    for i, tool in enumerate(ro_tools[:3]):  # Max 3 steps for read-only
        plan_a_steps.append(
            ActionStep(
                step_id=f"{intent_name}_ro_step_{i}",
                description=f"Read-only: {tool['name']}",
                read_only=True,
                tool_calls=[ToolCall(name=tool["name"], args={})],
                evidence_required=[f"{tool['name']}_result"],
                stop_if=[],
            )
        )

    if not plan_a_steps:
        # If no read-only tools, create a minimal observation step
        plan_a_steps.append(
            ActionStep(
                step_id=f"{intent_name}_observe",
                description="Gather context before action",
                read_only=True,
                tool_calls=[ToolCall(name="smx_response", args={})],
                evidence_required=["context_gathered"],
                stop_if=[],
            )
        )

    plan_a = ActionPlanCandidate(
        candidate_id=f"{intent_name}_graph_read_only",
        intent=intent_name,
        risk_level=RiskLevel.low,
        estimated_tokens=sum(80 for _ in plan_a_steps),
        is_mutating=False,
        steps=plan_a_steps,
    )

    # Plan B: Full execution (read-only first, then mutating)
    plan_b_steps = list(plan_a_steps)  # Start with read-only steps
    max_risk = RiskLevel.low

    for i, tool in enumerate(mut_tools[:2]):  # Max 2 mutating steps
        risk = _tool_risk_level(tool["name"])
        if risk.value > max_risk.value:
            max_risk = risk
        plan_b_steps.append(
            ActionStep(
                step_id=f"{intent_name}_mut_step_{i}",
                description=f"Execute: {tool['name']}",
                read_only=False,
                tool_calls=[ToolCall(name=tool["name"], args={})],
                evidence_required=[f"{tool['name']}_executed"],
                stop_if=[],
            )
        )

    plan_b = ActionPlanCandidate(
        candidate_id=f"{intent_name}_graph_full_exec",
        intent=intent_name,
        risk_level=max_risk if mut_tools else RiskLevel.low,
        estimated_tokens=sum(120 for _ in plan_b_steps),
        is_mutating=bool(mut_tools),
        steps=plan_b_steps,
    )

    logger.info(
        "GraphIntentResolver: %s → %d read-only, %d mutating → 2 plans",
        intent_name,
        len(ro_tools),
        len(mut_tools),
    )

    return [plan_a, plan_b]


# ---------------------------------------------------------------------------
# Clean shutdown - close driver on process exit
# ---------------------------------------------------------------------------
import atexit


def _close_driver():
    global _driver
    try:
        if _driver is not None:
            _driver.close()
    except Exception:
        pass
    finally:
        _driver = None


atexit.register(_close_driver)
